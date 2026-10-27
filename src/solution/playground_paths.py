"""Find the data of the Playground. A Solution runs from a wheel, from `pip install -e`, or from the source tree.

BUG-109: the data that the runtime needs must not sit only in a folder above the package. A wheel has no such folder.
- The Precord data (mocks, agents, tools) ships as package data: `playground_data.json` beside this module.
  `SOLUTION_PLAYGROUND_PRECORD` names another file. The source copy `playground/src/precord.json` is the last place.
- The production bundle (`playground/dist`) is built by npm and is not package data. `SOLUTION_PLAYGROUND_DIST` names the
  folder. The source folder is the fallback.
Nothing here gives an empty answer for a missing file. A missing Precord file raises. A missing bundle is a problem that
`/playground/status` shows."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

LOG = logging.getLogger("solution.playground")
PRECORD_ENV = "SOLUTION_PLAYGROUND_PRECORD"
DIST_ENV = "SOLUTION_PLAYGROUND_DIST"
_problems: dict[str, str] = {}


def root() -> Path:
    """The folder of the Solution in a source tree or an editable install. It does not exist in a wheel."""
    return Path(__file__).resolve().parents[2]


def problem(key: str, text: str | None) -> None:
    """Record or clear one problem. The status route lists them."""
    if text is None:
        _problems.pop(key, None)
        return
    if _problems.get(key) != text:
        LOG.error(text)
    _problems[key] = text


def problems() -> list[str]:
    return list(_problems.values())


def precord_candidates() -> list[Path]:
    named = os.environ.get(PRECORD_ENV, "").strip()
    return [Path(named)] if named else [Path(__file__).resolve().with_name("playground_data.json"),
                                        root() / "playground" / "src" / "precord.json"]


def precord() -> dict[str, Any]:
    """Read the Precord data of the build. Raise a clear error when no file is found."""
    found = [path for path in precord_candidates() if path.is_file()]
    if found:
        data = json.loads(found[0].read_text(encoding="utf-8"))
        problem("data", _drift(found, data))
        return data
    raise FileNotFoundError("Playground data not found. Looked in: " + ", ".join(str(p) for p in precord_candidates())
                            + f". Set {PRECORD_ENV} to the file, or install the Solution with solution/playground_data.json.")


def _drift(found: list[Path], data: dict[str, Any]) -> str | None:
    """Say so when the packaged copy and the source copy both exist and differ. One request reads one copy only."""
    if len(found) < 2:
        return None
    try:
        other = json.loads(found[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"The Playground data copy {found[1]} cannot be read. The copy {found[0]} is in use."
    if other == data:
        return None
    return f"The Playground data copies differ: {found[0]} (in use) and {found[1]}. Build the Solution again."


def dist_dir() -> Path:
    named = os.environ.get(DIST_ENV, "").strip()
    return Path(named) if named else root() / "playground" / "dist"
