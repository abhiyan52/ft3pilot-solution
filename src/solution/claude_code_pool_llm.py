"""ADK model adapter for a Solution subscription pool token.

A Claude plan credential is for Claude Code. So this adapter does not call the
Messages API itself: it runs the Claude Code CLI once for each ADK model turn,
pointed at the Studio Claude pool with the Solution token.

ADK owns the agent loop and runs every tool. Claude Code has no built-in tools.
The runtime refuses attachments before it starts Claude Code. It answers each turn
as structured JSON: either the tool calls it wants ADK to run, or the final
answer. ADK then runs the tools and asks for the next turn, as with any model.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, PrivateAttr

_UNSUPPORTED_SCHEMA_KEYS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "default", "examples",
})

#: Formats Anthropic accepts on a string. Anything else is dropped rather than
#: sent, because an unrecognised format is a 400 and a dropped one is prose.
_SUPPORTED_STRING_FORMATS = frozenset({
    "date-time", "time", "date", "duration", "email", "hostname", "uri",
    "ipv4", "ipv6", "uuid",
})


def _unfence(text: str) -> str:
    """Remove a Markdown fence around a complete JSON answer."""
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return text
    inner = stripped[3:-3]
    # ```json / ```JSON and friends: drop the language tag on the opening line.
    newline = inner.find("\n")
    if newline != -1 and inner[:newline].strip().isalpha():
        inner = inner[newline + 1:]
    return inner.strip()


def _sanitise_schema(node: Any) -> Any:
    """Remove unsupported schema constraints. Close each object."""
    if isinstance(node, list):
        return [_sanitise_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    clean: dict[str, Any] = {}
    for key, value in node.items():
        if key in _UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key == "format" and value not in _SUPPORTED_STRING_FORMATS:
            continue
        clean[key] = _sanitise_schema(value)

    if clean.get("type") == "object" or "properties" in clean:
        clean["additionalProperties"] = False
    return clean


def _json_schema(response_schema: Any) -> dict[str, Any] | None:
    """The response schema as a plain JSON Schema, whatever ADK handed us."""
    if response_schema is None:
        return None
    if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
        return _sanitise_schema(response_schema.model_json_schema())
    if isinstance(response_schema, types.Schema):
        return _sanitise_schema(response_schema.json_schema.model_dump(exclude_none=True))
    if isinstance(response_schema, dict):
        return _sanitise_schema(response_schema)
    return None


def _tool_schema(declaration: types.FunctionDeclaration) -> dict[str, Any]:
    """Read the parameters that the ADK declares for one tool."""
    if declaration.parameters_json_schema is not None:
        return _sanitise_schema(declaration.parameters_json_schema)
    parameters = declaration.parameters
    if parameters is None:
        return {"type": "object", "properties": {}}
    if isinstance(parameters, types.Schema):
        return _sanitise_schema(parameters.json_schema.model_dump(exclude_none=True))
    return _sanitise_schema(parameters)



def _system_text(config: types.GenerateContentConfig | None) -> str:
    if config is None or config.system_instruction is None:
        return ""
    instruction = config.system_instruction
    if isinstance(instruction, str):
        return instruction
    if isinstance(instruction, types.Content):
        return "\n\n".join(part.text for part in instruction.parts or [] if part.text)
    return str(instruction)




#: Claude Code picks its own model when the route names none.
TOOL_DEFAULT_MODEL = "tool-default"
_TURN_SECONDS = float(os.environ.get("CLAUDE_CODE_TURN_SECONDS", "900"))
# Each turn is one Node process. A fan-out of many branches must not start them all at once.
# One semaphore for each event loop: a job can run on its own loop.
_CONCURRENCY = int(os.environ.get("CLAUDE_CODE_CONCURRENCY", "3"))
_SLOTS: dict[int, asyncio.Semaphore] = {}


def _slots() -> asyncio.Semaphore:
    loop = id(asyncio.get_running_loop())
    if loop not in _SLOTS:
        _SLOTS[loop] = asyncio.Semaphore(_CONCURRENCY)
    return _SLOTS[loop]

_PROTOCOL = """You are the model behind one turn of an automated agent. The agent framework, not you, runs its tools.
You cannot call those tools directly, and they will not appear among your own tools. To use one, you REQUEST it
in your JSON answer; the framework runs it and shows you the result in the next turn.

Answer this one turn with JSON that matches the given schema:
- To request tools: fill "tool_calls". Each entry has the tool "name" and "arguments_json", which is the tool's
  arguments as one JSON object encoded as a string, for example "{\\"topic\\": \\"returns\\"}". Omit "final".
- To give the answer: fill "final" and leave "tool_calls" empty.
Request a tool whenever the instructions or the question need information you do not have yet.
Never invent a tool result and never claim a tool is unavailable."""


class ClaudeCodeError(ValueError):
    """Claude Code did not give a usable answer for the turn."""


def claude_binary() -> str:
    found = os.environ.get("CLAUDE_CODE_BINARY") or shutil.which("claude")
    if not found:
        raise ClaudeCodeError("The Claude Code CLI is not installed in the served Solution.")
    return found


def _function_config(config: types.GenerateContentConfig | None):
    return config.tool_config.function_calling_config if config and config.tool_config else None


def _declarations(config: types.GenerateContentConfig | None) -> list[types.FunctionDeclaration]:
    functions = _function_config(config)
    if functions and functions.mode == "NONE":
        return []
    declarations = [declaration for tool in (config.tools if config and config.tools else [])
                    for declaration in tool.function_declarations or []]
    if functions and functions.allowed_function_names:
        declarations = [d for d in declarations if d.name in functions.allowed_function_names]
    return declarations


def _turn_schema(declarations: list[types.FunctionDeclaration], final: dict[str, Any] | None) -> dict[str, Any]:
    final_schema = dict(final) if final else {"type": "string", "description": "The answer, as plain text."}
    # A Pydantic schema keeps its sub-types in $defs and points at them from the root ("#/$defs/X").
    # The answer schema sits under "final" here, so its definitions must move to the root for those to resolve.
    definitions = {key: final_schema.pop(key) for key in ("$defs", "definitions") if key in final_schema}
    turn = _turn_body(declarations, final_schema)
    turn.update(definitions)
    return turn


def _turn_body(declarations: list[types.FunctionDeclaration], final_schema: dict[str, Any]) -> dict[str, Any]:
    if not declarations:
        return {"type": "object", "properties": {"final": final_schema}, "required": ["final"]}
    return {
        "type": "object",
        "properties": {
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    # Arguments travel as a JSON string. A free-form object comes back empty from
                    # structured output, because the schema names no properties to fill.
                    "properties": {
                        "name": {"type": "string", "enum": [d.name for d in declarations]},
                        "arguments_json": {"type": "string",
                                           "description": "The tool arguments as one JSON object, matching the tool's schema."},
                    },
                    "required": ["name", "arguments_json"],
                },
            },
            "final": final_schema,
        },
    }


def _tool_catalog(declarations: list[types.FunctionDeclaration]) -> str:
    if not declarations:
        return ""
    lines = ["# Tools you can request through tool_calls"]
    for declaration in declarations:
        lines.append(f"## {declaration.name}\n{declaration.description or ''}\n"
                     f"Arguments (JSON Schema): {json.dumps(_tool_schema(declaration))}")
    return "\n\n".join(lines)


def _transcript(contents: list[types.Content]) -> str:
    """Convert the ADK turns into one conversation. Refuse attachments."""
    blocks: list[str] = []
    for content in contents:
        role = "assistant" if content.role == "model" else "user"
        for part in content.parts or []:
            if part.text:
                blocks.append(f"[{role}]\n{part.text}")
            elif part.inline_data is not None or part.file_data is not None:
                raise ClaudeCodeError("The served Claude runtime does not accept attachments.")
            elif part.function_call is not None:
                call = part.function_call
                blocks.append(f"[assistant tool call] {call.name} {json.dumps(call.args or {}, default=str)}")
            elif part.function_response is not None:
                response = part.function_response
                blocks.append(f"[tool result] {response.name}\n{json.dumps(response.response or {}, default=str)}")
    if not blocks:
        blocks.append("[user]\nBegin.")
    return "# Conversation so far\n\n" + "\n\n".join(blocks) + "\n\n# Your turn\nAnswer the next assistant turn."


def _command(model: str, schema: dict[str, Any], system: str) -> list[str]:
    command = [claude_binary(), "-p", "--output-format", "json", "--no-session-persistence",
               "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--disable-slash-commands", "--permission-mode", "default",
               "--tools", "",
               "--json-schema", json.dumps(schema), "--append-system-prompt", system]
    if model and model != TOOL_DEFAULT_MODEL:
        command += ["--model", model]
    return command


def _environment(pool_url: str, pool_token: str, home: Path) -> dict[str, str]:
    # Only what Claude Code needs. No provider key or studio secret reaches the process.
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude"), "TMPDIR": str(home),
        # Claude Code reads a plan token from CLAUDE_CODE_OAUTH_TOKEN. ANTHROPIC_AUTH_TOKEN counts as no login.
        "ANTHROPIC_BASE_URL": pool_url, "CLAUDE_CODE_OAUTH_TOKEN": pool_token,
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


def _parts(answer: Any, *, json_expected: bool, declarations: list[types.FunctionDeclaration]) -> list[types.Part]:
    if not isinstance(answer, dict):
        raise ClaudeCodeError("Claude Code returned no structured answer for the turn.")
    known = {d.name for d in declarations}
    calls = [call for call in answer.get("tool_calls") or [] if isinstance(call, dict)]
    if calls:
        parts = []
        for call in calls:
            if call.get("name") not in known:
                raise ClaudeCodeError(f"Claude Code asked for an unknown tool: {call.get('name')!r}.")
            raw = call.get("arguments_json")
            try:
                args = json.loads(_unfence(raw)) if isinstance(raw, str) and raw.strip() else (call.get("arguments") or {})
            except json.JSONDecodeError as exc:
                raise ClaudeCodeError(f"Claude Code gave invalid arguments for {call['name']}.") from exc
            if not isinstance(args, dict):
                raise ClaudeCodeError(f"Claude Code gave arguments for {call['name']} that are not an object.")
            parts.append(types.Part(function_call=types.FunctionCall(
                id=f"call_{uuid.uuid4().hex[:16]}", name=call["name"], args=args)))
        return parts
    if "final" not in answer:
        raise ClaudeCodeError("Claude Code answered with neither tool calls nor a final answer.")
    final = answer["final"]
    if json_expected or not isinstance(final, str):
        text = final if isinstance(final, str) else json.dumps(final)
        return [types.Part.from_text(text=_unfence(text) if isinstance(final, str) else text)]
    return [types.Part.from_text(text=final)]


class ClaudeCodePoolLlm(BaseLlm):
    """Run each agent turn through Claude Code with the Solution pool token."""

    _pool_url: str = PrivateAttr()
    _pool_token: str = PrivateAttr()
    _account_id: str = PrivateAttr()

    def __init__(self, *, model: str, pool_url: str, pool_token: str, account_id: str = ""):
        super().__init__(model=model)
        self._pool_url = pool_url.rstrip("/")
        self._pool_token = pool_token
        # The pool picks the account. Claude Code does not report it, so it is known only when one is allowed.
        self._account_id = account_id

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        config = llm_request.config
        declarations = _declarations(config)
        final_schema = _json_schema((config.response_json_schema or config.response_schema) if config else None)
        schema = _sanitise_schema(_turn_schema(declarations, final_schema))
        functions = _function_config(config)
        require_tool = bool(functions and functions.mode == "ANY")
        if require_tool:
            if not declarations:
                raise ClaudeCodeError("This turn requires a tool, but no permitted tool is available.")
            schema["required"] = ["tool_calls"]
            schema["properties"].pop("final", None)
        system = "\n\n".join(filter(None, [_PROTOCOL, _system_text(config), _tool_catalog(declarations)]))
        with tempfile.TemporaryDirectory(prefix="solution-claude-") as raw:
            work = Path(raw)
            prompt = _transcript(llm_request.contents or [])
            command = _command(self.model, schema, system)
            async with _slots():
                process = await asyncio.create_subprocess_exec(
                    *command, cwd=work, env=_environment(self._pool_url, self._pool_token, work),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    out, err = await asyncio.wait_for(process.communicate(prompt.encode()), timeout=_TURN_SECONDS)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise ClaudeCodeError(f"Claude Code did not answer the turn in {_TURN_SECONDS:.0f} s.") from None
        try:
            result = json.loads(out.decode() or "{}")
        except json.JSONDecodeError:
            result = {}
        if process.returncode != 0 or result.get("is_error") or result.get("subtype") not in (None, "success"):
            detail = str(result.get("result") or err.decode(errors="replace")[-400:] or "no output").strip()
            raise ClaudeCodeError(f"Claude Code failed the turn (exit {process.returncode}): {detail}")
        answer = result.get("structured_output")
        if require_tool and (not isinstance(answer, dict) or not answer.get("tool_calls")):
            raise ClaudeCodeError("This turn requires a tool call.")
        parts = _parts(answer, json_expected=final_schema is not None,
                       declarations=declarations)
        usage = result.get("usage") or {}
        cached = int(usage.get("cache_read_input_tokens") or 0)
        prompt_tokens = int(usage.get("input_tokens") or 0) + cached + int(usage.get("cache_creation_input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        yield LlmResponse(
            content=types.Content(role="model", parts=parts),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=prompt_tokens, candidates_token_count=output_tokens,
                total_token_count=prompt_tokens + output_tokens, cached_content_token_count=cached),
            custom_metadata={"pool_account_id": self._account_id,
                             "provider_response_id": str(result.get("session_id") or "")},
        )
