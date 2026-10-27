"""Construct persistent ADK Sessions from runtime secret injection."""
import os
from google.adk.runners import Runner
from google.adk.sessions.database_session_service import DatabaseSessionService


def make_runner(agent, *, agent_id="", case_id="", tool_bindings=None):
    if getattr(agent, 'tools', None):
        if not agent_id or not case_id:
            raise ValueError('The host must identify the case and agent before tool execution')
        from solution.tool_policy import install, metadata
        install(agent, agent_id, case_id, metadata(), bindings=tool_bindings)
    # The case store takes a plain address. The ADK session service takes an asyncpg address.
    url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    sessions = DatabaseSessionService(url)
    return Runner(app_name="specificity_solution", agent=agent, session_service=sessions)
