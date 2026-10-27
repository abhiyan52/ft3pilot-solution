"""Register host routes for the Playground, checkpoints, and declared triggers."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from solution import playground_paths as paths
from solution.playground_bridge import _precord, _state, _write, declared_triggers, dispatch

DEFAULT_USER = {"id": "preview-operator", "name": "Preview operator", "role": "sme"}
EMPTY_DRAFT = {"tickedItems": [], "comments": {}, "tickedRecommendations": [], "freeText": ""}
BUILDER = "solution-builder"
RESOLVED = {"approved", "closed", "resolved", "answered", "done", "dismissed"}
# The builder writes its gaps here (BUG-068). The Precord open_items.csv is protected and is the SDK list.
BUILD_OPEN_ITEMS = ".specificity/build-open-items.csv"
# The severity words of a register row, in the words of the Playground Next steps screen.
SEVERITY_WORDS = {"breaks runtime": "BLOCKS RELEASE", "blocks promotion": "BLOCKS PRODUCTION",
                  "information": "ENVIRONMENT"}


def read_register(name: str) -> list[dict[str, str]]:
    """Read one register of the Solution repository. A missing file gives no rows."""
    path = _root() / name
    if not path.is_file():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8").removeprefix("\ufeff"))))


def register_severity(row: dict[str, str]) -> str:
    """Take the severity from the row. A row without one follows the blocking column."""
    named = SEVERITY_WORDS.get((row.get("severity") or "").strip().lower())
    if named:
        return named
    return "BLOCKS RELEASE" if (row.get("blocking") or "").strip().lower() == "true" else "BLOCKS PRODUCTION"


def feedback_id(proposal: dict) -> str:
    """Give a proposal a stable ID. The same proposal always has the same ID."""
    return hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()[:12]


def pending_feedback(data: Path) -> list[dict]:
    """List the feedback that people sent from the Playground and no fix has used yet."""
    used = set(_state(data, "consumed-feedback", []))
    return [{"id": feedback_id(proposal), "text": proposal.get("reason") or proposal.get("subject") or "",
             "about": proposal.get("provenance", ""), "from": proposal.get("actor", "")}
            for proposal in _state(data, "proposals", []) if feedback_id(proposal) not in used]


def register_next_steps() -> dict[str, list]:
    """Give the builder gaps and the builder deviations. The Precord open items come from the SDK in the bundle.

    A resolved or dismissed row and a deviation a person decided are not items."""
    items = [{"id": f"open_items:{row['item_id']}", "text": row.get("subject") or row.get("detail") or row["item_id"],
              "severity": register_severity(row), "source": "open_items"}
             for row in read_register(BUILD_OPEN_ITEMS)
             if row.get("item_id") and (row.get("status") or "open").strip().lower() not in RESOLVED]
    items += [{"id": f"deviations:{row['deviation_id']}", "text": row.get("departure") or row["deviation_id"],
               "severity": register_severity(row), "source": "deviations"}
              for row in read_register("precord/spec/deviations.csv")
              if row.get("deviation_id") and (row.get("decided_by") or "").strip() == BUILDER]
    return {"items": items, "recommendations": []}


def session_routes(method: str, route: str, body: dict, data: Path) -> object | None:
    """Serve the Playground SDK routes for the operator, the figures, next steps, and sign-off.

    The standalone preview server has the same routes. The served Solution must answer them too,
    or the Playground shows "No runtime data yet" on its first request."""
    from datetime import UTC, datetime
    user = _state(data, "user", dict(DEFAULT_USER))
    if route == "session":
        return user
    if route == "session/role" and method == "PUT":
        if body.get("role") not in {"sme", "technical"}:
            raise ValueError("Unknown role")
        user["role"] = body["role"]
        _write(data, "user", user)
        return user
    if route == "overview/figures":
        agents = _precord()["files"]["spec/agents.yaml"]
        return {"agentsBuilt": {"built": sum(bool(a.get("built")) for a in agents), "total": len(agents)}}
    if route == "next-steps" and method == "GET":
        return register_next_steps()
    if route == "feedback" and method == "GET":
        return pending_feedback(data)
    if route == "feedback/consume" and method == "POST":
        used = set(_state(data, "consumed-feedback", [])) | {str(identity) for identity in body.get("ids", [])}
        _write(data, "consumed-feedback", sorted(used))
        return pending_feedback(data)
    if route == "next-steps/draft":
        if method == "PUT":
            _write(data, "draft", body)
        return _state(data, "draft", dict(EMPTY_DRAFT))
    if route == "next-steps/send" and method == "POST":
        meta = _precord()
        draft = body.get("draft", {})
        actions, proposals = [], _state(data, "proposals", [])
        for identity in dict.fromkeys(draft.get("tickedItems", []) + draft.get("tickedRecommendations", [])):
            text = draft.get("comments", {}).get(identity) or draft.get("freeText") or identity
            proposals.append({"kind": "AddOpenItem", "tenant_id": meta["tenant_id"], "requirement_id": meta["requirement_id"],
                              "actor": user["id"], "reason": text, "build_revision": meta["build"]["buildId"],
                              "expected_hash": meta["open_items_hash"], "provenance": identity, "subject": text,
                              "detail": "Raised in the Solution Playground for " + identity + "."})
            actions.append({"itemId": identity, "text": text, "comment": draft.get("comments", {}).get(identity, ""),
                            "freeText": draft.get("freeText", ""), "userId": user["id"], "userName": user["name"],
                            "role": user["role"], "sentAt": datetime.now(UTC).isoformat(), "buildId": meta["build"]["buildId"],
                            "kind": "open_item" if identity in draft.get("tickedItems", []) else "recommendation"})
        _write(data, "proposals", proposals)
        return actions
    if route == "sign-off":
        state = _state(data, "sign-off", {"records": [], "invitees": []})
        if method == "POST":
            if body.get("tag") not in {"GOOD TO GO", "NOT YET"}:
                raise ValueError("Unknown decision")
            state["records"].append({"userId": user["id"], "name": user["name"], "role": user["role"], "tag": body["tag"],
                                     "comment": body.get("comment", ""), "at": datetime.now(UTC).isoformat(),
                                     "buildId": _precord()["build"]["buildId"]})
            _write(data, "sign-off", state)
        return state
    return None


def _data_dir() -> Path:
    if os.environ.get("PREVIEW_DATA_DIR"):
        path = Path(os.environ["PREVIEW_DATA_DIR"])
    else:
        path = Path(__file__).resolve().parents[2] / ".preview-data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def mount_static(app: FastAPI) -> None:
    """Serve the Playground bundle at / and the checkpoint screens at /ui.

    The mounts come after the JSON routes, so those routes win. A `ui` folder that does not exist is skipped.
    The entry pages are never cached, so a re-served revision reaches the browser on a plain reload."""

    @app.middleware("http")
    async def no_cache_entry_pages(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        path = request.url.path
        if path in {"/", "/index.html", "/ui", "/ui/", "/ui/index.html"} or path.endswith("/index.html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    ui = _root() / "ui"
    if ui.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui), html=True), name="ui")
    # BUG-109: the bundle is not package data. SOLUTION_PLAYGROUND_DIST names it, else the source folder is used.
    # A missing bundle is logged and listed at /playground/status. It is never skipped without a word.
    dist = paths.dist_dir()
    if (dist / "index.html").is_file():
        paths.problem("bundle", None)
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="playground")
    else:
        paths.problem("bundle", f"The Playground bundle is missing: {dist / 'index.html'} is not a file. "
                      f"Build it with npm, or set {paths.DIST_ENV} to the folder that holds it.")



async def uploaded_request(request: Request) -> dict:
    """Read the Playground SDK multipart form: a `request` JSON part and the files under `files`.

    A JSON file that holds an object becomes the agent input when the form sent no field values.
    Every file name is kept, so the run record says what the person uploaded."""
    form = await request.form()
    raw = form.get("request")
    try:
        body = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    files = []
    for item in form.getlist("files"):
        if not hasattr(item, "filename"):
            continue
        content = await item.read()
        files.append({"name": item.filename or "", "type": item.content_type or "", "size": len(content)})
        if (item.filename or "").lower().endswith(".json") and not body.get("input"):
            try:
                parsed = json.loads(content)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"{item.filename} is not valid JSON") from None
            if isinstance(parsed, dict):
                body["input"] = {key: value if isinstance(value, str) else json.dumps(value) for key, value in parsed.items()}
    source = body.get("source") if isinstance(body.get("source"), dict) else {}
    body["source"] = {**source, "kind": "uploaded", "files": files}
    return body


def register(app: FastAPI) -> None:
    """Attach C3, C5, and C8 surfaces to the host FastAPI app. Then mount the demo UI."""
    app.state.triggers = declared_triggers()
    from solution.mock_service import router as mock_router
    app.include_router(mock_router)

    @app.get("/v1/triggers")
    def triggers() -> list[dict[str, str]]:
        return declared_triggers()

    try:
        from checkpoints.service import create_router

        # The router and the Playground share one store, so a decision made on either shows on both.
        from solution.playground_bridge import _checkpoint_store
        router = create_router(_checkpoint_store())
        if router is not None:
            app.include_router(router)
    except ImportError:
        pass

    @app.api_route("/playground/{full_path:path}", methods=["GET", "POST", "PUT"])
    async def playground_routes(full_path: str, request: Request) -> JSONResponse:
        body: dict = {}
        if request.method in {"POST", "PUT", "PATCH"}:
            if request.headers.get("content-type", "").startswith("multipart/form-data"):
                body = await uploaded_request(request)
            else:
                raw = await request.body()
                if raw:
                    try:
                        parsed = json.loads(raw)
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid JSON") from None
                    if not isinstance(parsed, dict):
                        raise HTTPException(status_code=400, detail="Invalid JSON") from None
                    body = parsed
        try:
            result = session_routes(request.method, full_path, body, _data_dir())
            if result is None:
                result = dispatch(request.method, full_path, body, _data_dir())
        except LookupError:
            raise HTTPException(status_code=404, detail="No runtime data yet") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return JSONResponse(result)

    mount_static(app)
