"""Solution health and version boundary. Components register their own routes."""
from fastapi import FastAPI

app = FastAPI(title="Specificity Solution")


def optional(module: str, error: ModuleNotFoundError) -> None:
    """A Component that has not built yet leaves its module out. A missing library of a present module is a fault."""
    if error.name != module and not module.startswith(f"{error.name}."):
        raise error


try:
    from solution.signin import install as install_signin
except ModuleNotFoundError as error:
    optional("solution.signin", error)
    install_signin = None
if install_signin is not None:
    install_signin(app)

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

try:
    from solution.case_routes import router as case_router
except ModuleNotFoundError as error:
    optional("solution.case_routes", error)
else:
    app.include_router(case_router)

try:
    from integrations.inbound_api import router as inbound_router
except ModuleNotFoundError as error:
    optional("integrations.inbound_api", error)
else:
    app.include_router(inbound_router)

try:
    from solution.wiring import register
except ModuleNotFoundError as error:
    optional("solution.wiring", error)
    register = None
if register is not None:
    register(app)
