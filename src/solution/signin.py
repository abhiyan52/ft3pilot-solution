"""One sign-in in front of the served Solution (C6-3, C6-4).

The runtime sets SOLUTION_SIGNIN_PASSWORD. With no password the Solution is open, as in local
development. `/health` stays open for the host. The Solution calls its own mocks from this host, so
a loopback request to a mock needs no sign-in."""
import base64
import hmac
import os

from fastapi import FastAPI, Request, Response

USER = "solution"
LOOPBACK = {"127.0.0.1", "::1"}


def allowed(header: str, password: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        user, _, given = base64.b64decode(header[6:]).decode().partition(":")
    except ValueError:
        return False
    return hmac.compare_digest(user, USER) and hmac.compare_digest(given.encode(), password.encode())


def install(app: FastAPI) -> None:
    password = os.environ.get("SOLUTION_SIGNIN_PASSWORD", "")
    if not password:
        return

    @app.middleware("http")
    async def sign_in(request: Request, call_next):
        path = request.url.path
        host = request.client.host if request.client else ""
        if path == "/health" or (path.startswith("/__MOCK__/") and host in LOOPBACK):
            return await call_next(request)
        if allowed(request.headers.get("authorization", ""), password):
            return await call_next(request)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Solution"'})
