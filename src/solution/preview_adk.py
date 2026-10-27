"""Invoke C3 ADK agents in preview when PLAYGROUND_INVOKE_ADK is enabled."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from solution.adk_model import configure_litellm_proxy
from solution.llm_config import problem as llm_problem

_PREVIEW_APP = "solution_playground_preview"


def _enabled() -> bool:
    return (os.environ.get("PLAYGROUND_INVOKE_ADK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


async def _run_async(module: Any, payload: dict[str, Any], *, agent_id: str = "", case_id: str = "") -> str:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    configure_litellm_proxy()
    reason = llm_problem()
    if reason:
        raise RuntimeError(f"The agent has no model to call. {reason} See deploy/.env.example.")

    make_agent = getattr(module, "make_agent", None)
    if not callable(make_agent):
        raise RuntimeError("make_agent() is missing")

    agent = make_agent()
    if getattr(agent, 'tools', None):
        from solution.playground_bridge import _precord
        from solution.tool_policy import install

        metadata = _precord()
        if not agent_id:
            declarations = metadata['files']['spec/agents.yaml']
            if len(declarations) != 1:
                raise RuntimeError('The host must identify the invoked agent')
            agent_id = declarations[0]['agent_id']
        identity = case_id or (payload.get('case') if isinstance(payload.get('case'), str) else '')
        install(agent, agent_id, identity, metadata, bindings=getattr(module, 'TOOL_BINDINGS', None))
    runner = InMemoryRunner(agent=agent, app_name=_PREVIEW_APP)
    session = await runner.session_service.create_session(
        app_name=_PREVIEW_APP, user_id="preview-operator"
    )
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    "Run on this case input JSON. Follow your instruction and tools.\n"
                    + json.dumps(payload, indent=2)
                )
            )
        ],
    )
    text = ""
    async for event in runner.run_async(
        user_id="preview-operator",
        session_id=session.id,
        new_message=message,
    ):
        if event.error_code:
            # The provider message says why (for example a retired model). The code alone hides it.
            detail = f" {event.error_message}" if getattr(event, "error_message", None) else ""
            raise RuntimeError(f"Agent execution failed: {event.error_code}{detail}")
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(part.text for part in event.content.parts if part.text and not part.thought)
    return text.strip()



def _run_coroutine(coroutine: Any) -> Any:
    """Run the coroutine to completion. Inside a running loop (a FastAPI route) a worker thread runs it."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


def _validate_with_output_schema(module: Any, output: dict[str, Any]) -> None:
    """Check the output against OUTPUT_SCHEMA and SCHEMA_STORE, as the runtime does (agent_runtime.validate).

    C3 requires OUTPUT_SCHEMA in every agent module and checks it. It asks for no validator function, so a module
    without one is validated here. A module that has no OUTPUT_SCHEMA still has no validator and fails."""
    schema = getattr(module, "OUTPUT_SCHEMA", None)
    if not isinstance(schema, dict):
        raise ValueError("The generated agent has no output validator and no OUTPUT_SCHEMA")
    from solution import agent_runtime

    agent_runtime.validate(output, schema, getattr(module, "SCHEMA_STORE", None), agent_runtime.AgentOutputInvalid)


def invoke_make_agent(module: Any, agent_id: str, payload: dict[str, Any], *, case_id: str = "") -> dict[str, Any]:
    """Run one ADK preview turn. Raise on configuration or API errors."""
    if not _enabled():
        raise RuntimeError("PLAYGROUND_INVOKE_ADK is not enabled")
    try:
        text = _run_coroutine(_run_async(module, payload, agent_id=agent_id, case_id=case_id))
    except Exception as error:  # noqa: BLE001 — surface API failures to the bridge
        raise RuntimeError(f"ADK run failed for {agent_id}: {error}") from error
    try:
        output = json.loads(text)
        if not isinstance(output, dict):
            raise ValueError("The agent output must be a JSON object")
        validate = getattr(module, "validate_output", None) or getattr(module, "validate_agent_output", None)
        if callable(validate):
            validate(output)
        else:
            _validate_with_output_schema(module, output)
    except Exception as error:
        raise RuntimeError(f"Agent {agent_id} returned invalid output: {error}") from error
    return {
        "fields": [{"label": "response", "value": text[:2000]}],
        "raw": {"json": json.dumps({"agent": agent_id, "output": output}, indent=2)},
        "summary": "ADK run completed. The output passed the generated schema validator.",
        "output": output,
        "invoked": True,
    }
