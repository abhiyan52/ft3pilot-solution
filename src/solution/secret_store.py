"""Resolve a declared secret from its declared store (C1-4, C3-23, F31-44).

`secret_bindings.json` lists each secret that the Precord declares (runtime.yaml secrets, or auth_ref of the integration map) with its name and store. It holds no value.
A store is a reader: a function that takes the secret name and gives the value, or None. A deployment registers
the reader of its store with `register_store`. A store with no reader falls back to its local equivalent, and the
result says so. The local equivalents are an environment variable of the secret name, then a file of that name in
SOLUTION_SECRETS_DIR. This module never prints or logs a value, and its errors name the secret and the store only."""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

BINDINGS_PATH = Path(__file__).with_name("secret_bindings.json")
Reader = Callable[[str], "str | None"]
_stores: dict[str, Reader] = {}


class SecretUnavailable(LookupError):
    """The secret has no value in its store. The message names the secret and the store, never a value."""


@dataclass(frozen=True)
class Resolved:
    name: str
    store: str
    value: str
    source: str  # "store" for a registered reader; "local-equivalent" for the fallback

    def __repr__(self) -> str:
        return f"Resolved(name={self.name!r}, store={self.store!r}, source={self.source!r})"


def register_store(store: str, reader: Reader) -> None:
    _stores[store] = reader


def bindings() -> dict[str, str]:
    """Give the store of each declared secret. A file that is missing or unreadable declares none."""
    try:
        rows = json.loads(BINDINGS_PATH.read_text()).get("secrets") or []
    except (OSError, ValueError):
        return {}
    return {str(row["name"]): str(row.get("store") or "") for row in rows if isinstance(row, dict) and row.get("name")}


def _local(name: str, env: Mapping[str, str]) -> str | None:
    value = (env.get(name) or "").strip()
    if value:
        return value
    directory = (env.get("SOLUTION_SECRETS_DIR") or "").strip()
    if directory:
        path = Path(directory) / name
        if path.parent == Path(directory) and path.is_file():
            return path.read_text().strip() or None
    return None


def resolve(name: str, env: Mapping[str, str] | None = None) -> Resolved:
    """Give the value of a declared secret. Raise SecretUnavailable when the store has none."""
    values = os.environ if env is None else env
    declared = bindings()
    if name not in declared:
        raise SecretUnavailable(f"{name} is not a secret that the Precord declares.")
    store = declared[name]
    reader = _stores.get(store)
    if reader is not None:
        value = reader(name)
        if value:
            return Resolved(name, store, value, "store")
        raise SecretUnavailable(f"{name} has no value in the store {store}.")
    value = _local(name, values)
    if value:
        return Resolved(name, store, value, "local-equivalent")
    raise SecretUnavailable(f"{name} has no value. Its store is {store}. Register a reader for the store, "
                            f"or set {name} in the environment or in SOLUTION_SECRETS_DIR.")


def value(name: str, env: Mapping[str, str] | None = None) -> str:
    """Give the value of a declared secret, or an empty text when the name is not declared or has no value."""
    try:
        return resolve(name, env).value
    except SecretUnavailable:
        return ""
