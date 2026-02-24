import pytest

import kodiak.services.executor as executor_module
from kodiak.core.tools.definitions.discovery import FfufTool
from kodiak.core.tools.definitions.exploitation import SQLMapTool
from kodiak.core.tools.definitions.web import NucleiTool
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
    assert len(fake_executor.calls) == 3
    assert fake_executor.calls[2]["command"] == ["bash", "-c", command]
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
    assert len(fake_executor.calls) == 2  # startup shell probe + pwd; export handled in-memory
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
    assert len(fake_executor.calls) == 3
    assert fake_executor.calls[2]["command"] == ["bash", "-c", command]
    assert "TOKEN" not in _terminal_sessions[session_id].environment


@pytest.mark.asyncio
async def test_terminal_start_rejects_unsupported_shell(monkeypatch):
    fake_executor = FakeExecutor(stdout="/tmp")
    monkeypatch.setattr(
        "kodiak.core.tools.definitions.terminal.get_executor",
        lambda mode="local": fake_executor,
    )

    result = await TerminalStartTool().execute(shell_type="fish")

    assert result.success is False
    assert "Unsupported shell type" in result.output


@pytest.mark.asyncio
async def test_terminal_execute_session_not_found_message_lists_active_sessions(monkeypatch):
    fake_executor = FakeExecutor(stdout="/tmp")
    monkeypatch.setattr(
        "kodiak.core.tools.definitions.terminal.get_executor",
        lambda mode="local": fake_executor,
    )

    started = await TerminalStartTool().execute(shell_type="bash")
    assert started.success is True

    result = await TerminalExecuteTool().execute(
        session_id="term_missing",
        command="echo hello",
    )

    assert result.success is False
    assert "Active sessions: 1" in result.output


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


@pytest.mark.asyncio
async def test_ffuf_supports_multi_wordlists_post_and_match_filters(monkeypatch):
    captured = {}

    class FakeDockerExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            captured["command"] = command
            return CommandResult(exit_code=0, stdout='{"results":[]}', stderr="")

    async def fake_get_docker_executor(preferred_image=None, fallback_image=None, fallback_entrypoint=None):
        return FakeDockerExecutor()

    monkeypatch.setattr(executor_module, "get_docker_executor", fake_get_docker_executor)

    tool = FfufTool()
    result = await tool.execute(
        url="https://example.com/login",
        method="POST",
        data="username=USER&password=PASS",
        wordlists=["/tmp/users.txt:USER", "/tmp/passwords.txt:PASS"],
        mode="clusterbomb",
        match_status="302",
        filter_regex="Invalid username or password",
        headers="Content-Type: application/x-www-form-urlencoded",
    )

    assert result.success is True
    command = captured["command"]
    assert command.count("-w") == 2
    assert "/tmp/users.txt:USER" in command
    assert "/tmp/passwords.txt:PASS" in command
    assert "-d" in command
    assert "username=USER&password=PASS" in command
    assert "-mode" in command
    assert "clusterbomb" in command
    assert "-mc" in command and "302" in command
    assert "-fr" in command


@pytest.mark.asyncio
async def test_ffuf_downgrades_clusterbomb_when_only_single_wordlist(monkeypatch):
    captured = {}

    class FakeDockerExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            captured["command"] = command
            return CommandResult(exit_code=0, stdout='{"results":[]}', stderr="")

    async def fake_get_docker_executor(preferred_image=None, fallback_image=None, fallback_entrypoint=None):
        return FakeDockerExecutor()

    monkeypatch.setattr(executor_module, "get_docker_executor", fake_get_docker_executor)

    tool = FfufTool()
    result = await tool.execute(
        url="https://example.com/FUZZ",
        mode="clusterbomb",
    )

    assert result.success is True
    assert result.data.get("mode") == "sniper"
    assert any("downgraded to 'sniper'" in w for w in (result.data.get("warnings") or []))
    command = captured["command"]
    assert "-mode" in command
    mode_index = command.index("-mode")
    assert command[mode_index + 1] == "sniper"


@pytest.mark.asyncio
async def test_nuclei_does_not_fallback_on_generic_exit_code_two(monkeypatch):
    calls = {"count": 0}

    class FakeToolboxExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            calls["count"] += 1
            return CommandResult(exit_code=2, stdout="", stderr="template parse error")

    class FakeFallbackExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            calls["count"] += 1
            return CommandResult(exit_code=0, stdout='{"template-id":"ok"}', stderr="")

    async def fake_get_docker_executor(preferred_image=None, fallback_image=None, fallback_entrypoint=None):
        # Should only be called once for this test
        if calls["count"] == 0:
            return FakeToolboxExecutor()
        return FakeFallbackExecutor()

    monkeypatch.setattr(executor_module, "get_docker_executor", fake_get_docker_executor)

    tool = NucleiTool()
    result = await tool.execute(target="https://example.com")

    assert result.success is False
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_nuclei_fallback_when_binary_missing(monkeypatch):
    calls = {"count": 0}

    class FakeToolboxExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            calls["count"] += 1
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr="/bin/sh: 1: nuclei: not found",
            )

    class FakeFallbackExecutor:
        async def run_command(self, command, cwd=None, env=None, stdin=None):
            calls["count"] += 1
            return CommandResult(exit_code=0, stdout='{"template-id":"detected"}', stderr="")

    async def fake_get_docker_executor(preferred_image=None, fallback_image=None, fallback_entrypoint=None):
        if "projectdiscovery/nuclei:latest" in str(preferred_image):
            return FakeFallbackExecutor()
        return FakeToolboxExecutor()

    monkeypatch.setattr(executor_module, "get_docker_executor", fake_get_docker_executor)

    tool = NucleiTool()
    result = await tool.execute(target="https://example.com")

    assert result.success is True
    assert result.data.get("execution_mode") == "docker-fallback"
    assert calls["count"] == 2
