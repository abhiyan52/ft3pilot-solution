"""C3-11: every log line and span of an agent carries the build, the agent, and a correlation ID."""
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_CORRELATION: ContextVar[str] = ContextVar("correlation_id", default="")


@contextmanager
def correlation(correlation_id: str) -> Iterator[None]:
    token = _CORRELATION.set(correlation_id)
    try:
        yield
    finally:
        _CORRELATION.reset(token)


def tags(agent_id: str) -> dict[str, str]:
    return {"build_id": os.environ.get("SOLUTION_BUILD_ID", ""), "agent_id": agent_id,
            "correlation_id": _CORRELATION.get()}


def logger(agent_id: str) -> logging.LoggerAdapter:  # type: ignore[type-arg]
    """Give a logger whose records carry the tags in `extra`."""
    return logging.LoggerAdapter(logging.getLogger(f"solution.{agent_id}"), tags(agent_id))
