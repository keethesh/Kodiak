import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import kodiak.core.memory_central as memory_central_module
import kodiak.services.executor as executor_module
from kodiak.core.agent import KodiakAgent
from kodiak.core.memory_central import CentralMemoryService
from kodiak.core.tools.definitions.exploitation import SQLMapTool
from kodiak.core.tools.definitions.terminal import (
    TerminalExecuteTool,
    TerminalStartTool,
    _terminal_sessions,
)
from kodiak.services.executor import CommandResult


class FakeExecutor:
    def __init__(self, stdout: str = "ok", stderr: str = "", exit_code: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.calls = []

    async def run_command(self, command, cwd=None, env=None, stdin=None):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": dict(env or {}),
                "stdin": stdin,
            }
        )
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr=self.stderr)


@pytest.fixture(autouse=True)
def reset_terminal_sessions():
    _terminal_sessions.clear()
    yield
    _terminal_sessions.clear()


def _make_agent() -> KodiakAgent:
    inventory = Mock()
    inventory.list_tools.return_value = {"sqlmap": "sqlmap", "httpx": "httpx"}
    inventory.get.return_value = Mock(to_openai_schema=Mock(return_value={"type": "function"}))

    event_manager = Mock()
    event_manager.emit_tool_start = AsyncMock()
    event_manager.emit_tool_complete = AsyncMock()

    return KodiakAgent(
        agent_id="agent-test",
        tool_inventory=inventory,
        event_manager=event_manager,
        role="scout",
    )


@pytest.mark.asyncio
async def test_terminal_execute_does_not_treat_equals_as_env_assignment(monkeypatch):
    fake_executor = FakeExecutor(stdout="/tmp")
    monkeypatch.setattr(
        "kodiak.core.tools.definitions.terminal.get_executor",
        lambda mode="local": fake_executor,
    )

    start_result = await TerminalStartTool().execute()
    assert start_result.success
    session_id = start_result.data["session_id"]

    command = 'curl -s "https://example.com/news.php?id=1&a=b"'
    result = await TerminalExecuteTool().execute(
        session_id=session_id,
        command=command,
        capture_output=False,
    )

    assert result.success is True
    assert len(fake_executor.calls) == 2
    assert fake_executor.calls[1]["command"] == ["bash", "-c", command]
    assert _terminal_sessions[session_id].environment == {}


@pytest.mark.asyncio
async def test_terminal_execute_explicit_export_updates_session_environment(monkeypatch):
    fake_executor = FakeExecutor(stdout="/tmp")
    monkeypatch.setattr(
        "kodiak.core.tools.definitions.terminal.get_executor",
        lambda mode="local": fake_executor,
    )

    start_result = await TerminalStartTool().execute()
    assert start_result.success
    session_id = start_result.data["session_id"]

    result = await TerminalExecuteTool().execute(
        session_id=session_id,
        command="export TOKEN=abc123 REGION=us-east-1",
    )

    assert result.success is True
    assert "TOKEN=abc123" in result.output
    assert "REGION=us-east-1" in result.output
    assert len(fake_executor.calls) == 1  # startup only; export handled in-memory
    assert _terminal_sessions[session_id].environment["TOKEN"] == "abc123"
    assert _terminal_sessions[session_id].environment["REGION"] == "us-east-1"


@pytest.mark.asyncio
async def test_terminal_execute_chained_export_is_executed_normally(monkeypatch):
    fake_executor = FakeExecutor(stdout="hello")
    monkeypatch.setattr(
        "kodiak.core.tools.definitions.terminal.get_executor",
        lambda mode="local": fake_executor,
    )

    start_result = await TerminalStartTool().execute()
    assert start_result.success
    session_id = start_result.data["session_id"]

    command = "export TOKEN=abc123 && echo hello"
    result = await TerminalExecuteTool().execute(
        session_id=session_id,
        command=command,
        capture_output=False,
    )

    assert result.success is True
    assert len(fake_executor.calls) == 2
    assert fake_executor.calls[1]["command"] == ["bash", "-c", command]
    assert "TOKEN" not in _terminal_sessions[session_id].environment


@pytest.mark.asyncio
async def test_central_memory_handles_none_error_without_crashing(monkeypatch):
    statuses = []

    async def fake_create(session, record):
        statuses.append(record.status)
        return record

    monkeypatch.setattr(memory_central_module.attempt_crud, "create", fake_create)

    service = CentralMemoryService()
    await service.record_attempt(
        session=object(),
        project_id=uuid4(),
        scan_id=uuid4(),
        agent_id="agent-1",
        tool_name="sqlmap",
        target="https://example.com/news.php?id=1",
        fingerprint="fp-1",
        args={},
        result={"success": False, "error": None, "output": "failed"},
    )
    await service.record_attempt(
        session=object(),
        project_id=uuid4(),
        scan_id=uuid4(),
        agent_id="agent-1",
        tool_name="sqlmap",
        target="https://example.com/news.php?id=1",
        fingerprint="fp-2",
        args={},
        result={"success": False, "error": "Skipping duplicate sqlmap call", "output": ""},
    )

    assert statuses == ["failure", "skipped"]


def test_agent_skip_logic_ignores_persisted_advice_as_hard_block():
    agent = _make_agent()
    fingerprint = "sqlmap:deadbeef"
    agent._persisted_do_not_repeat[fingerprint] = "old guidance"

    assert agent._should_skip_tool_call("sqlmap", {}, fingerprint) is None

    agent._attempts_by_fingerprint[fingerprint] = [{"success": True, "timed_out": False}]
    assert "Skipping duplicate sqlmap call" in agent._should_skip_tool_call("sqlmap", {}, fingerprint)

    agent._attempts_by_fingerprint[fingerprint] = [{"success": False, "timed_out": True}]
    assert "previous attempt timed out" in agent._should_skip_tool_call("sqlmap", {}, fingerprint)


@pytest.mark.asyncio
async def test_sqlmap_rejects_url_with_embedded_cli_flags():
    tool = SQLMapTool()
    result = await tool.execute(url="https://example.com/news.php?id=1 --is-dba")

    assert result.success is False
    assert "CLI flags" in result.output


@pytest.mark.asyncio
async def test_sqlmap_appends_privilege_and_context_flags(monkeypatch):
    captured = {}

    class FakeDockerExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            captured["command"] = command
            return CommandResult(exit_code=0, stdout="ok", stderr="")

    async def fake_get_docker_executor(preferred_image=None, fallback_image=None, fallback_entrypoint=None):
        return FakeDockerExecutor()

    monkeypatch.setattr(executor_module, "get_docker_executor", fake_get_docker_executor)

    tool = SQLMapTool()
    result = await tool.execute(
        url="https://example.com/news.php?id=1",
        is_dba=True,
        privileges=True,
        users=True,
        passwords=True,
        current_user=True,
        current_db=True,
    )

    assert result.success is True
    command = captured["command"]
    for flag in ["--is-dba", "--privileges", "--users", "--passwords", "--current-user", "--current-db"]:
        assert flag in command


def test_agent_history_content_includes_compact_tool_data():
    agent = _make_agent()
    content = agent._build_tool_history_content(
        {
            "output": "SQLMap completed",
            "data": {"exit_code": 0, "vulnerable": True, "total_found": 2, "verbose_blob": {"a": 1}},
        }
    )

    assert "SQLMap completed" in content
    assert "[tool_data]" in content
    assert '"vulnerable":true' in content
