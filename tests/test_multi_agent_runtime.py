import asyncio
from types import SimpleNamespace

import pytest

from kodiak.api.events import TUIEventManager
from kodiak.core.scan_runner import ScanRunner
from kodiak.core.scan_state import ScanState, ScanPhase
from kodiak.core.manager import ManagerAgent


class TestScanStateBasics:
    """Tests for the ScanState model."""

    def test_initial_phase_is_recon(self):
        state = ScanState(target="example.com")
        assert state.phase == ScanPhase.RECON

    def test_advance_phase_cycles_correctly(self):
        state = ScanState(target="example.com")
        assert state.advance_phase()
        assert state.phase == ScanPhase.ENUMERATION
        assert state.advance_phase()
        assert state.phase == ScanPhase.VULN_SCAN
        assert state.advance_phase()
        assert state.phase == ScanPhase.EXPLOITATION
        assert state.advance_phase()
        assert state.phase == ScanPhase.REPORTING
        assert not state.advance_phase()  # no more phases

    def test_ensure_target_creates_new(self):
        state = ScanState(target="example.com")
        ts = state.ensure_target("sub.example.com")
        assert ts.hostname == "sub.example.com"
        assert "sub.example.com" in state.targets

    def test_ensure_target_returns_existing(self):
        state = ScanState(target="example.com")
        ts1 = state.ensure_target("host.com")
        ts1.ports.append(80)
        ts2 = state.ensure_target("host.com")
        assert ts2.ports == [80]

    def test_record_tool_result(self):
        state = ScanState(target="example.com")
        state.record_tool_result("nmap", "example.com", "success", "3 ports open")
        assert len(state.completed_tools) == 1
        assert state.completed_tools[0].tool == "nmap"

    def test_add_finding(self):
        state = ScanState(target="example.com")
        state.add_finding("SQLi", "high", "example.com/login", evidence="parameter id")
        assert state.findings_count == 1
        assert state.findings[0].severity == "high"

    def test_has_tool_been_run(self):
        state = ScanState(target="example.com")
        assert not state.has_tool_been_run("nmap", "example.com")
        state.record_tool_result("nmap", "example.com", "success", "done")
        assert state.has_tool_been_run("nmap", "example.com")

    def test_to_prompt_context_bounded(self):
        state = ScanState(target="example.com")
        for i in range(100):
            state.record_tool_result(f"tool{i}", "example.com", "success", f"result {i}")
        ctx = state.to_prompt_context(max_tool_records=10)
        assert "showing last 10" in ctx
        assert len(ctx) < 5000  # bounded


class TestManagerAgent:
    """Unit tests for the ManagerAgent helper methods."""

    def _manager(self) -> ManagerAgent:
        from kodiak.core.tools.inventory import ToolInventory
        inv = ToolInventory()
        inv.initialize_tools()
        return ManagerAgent(
            event_manager=TUIEventManager(),
            tool_inventory=inv,
        )

    def test_prepare_tools_excludes_blackboard(self):
        manager = self._manager()
        tools = manager._prepare_tools()
        names = [t["function"]["name"] for t in tools]
        assert not any(n.startswith("blackboard_") for n in names)
        assert "complete_scan" in names

    def test_check_phase_advance_with_keyword(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        assert manager.scan_state.phase == ScanPhase.RECON
        manager._check_phase_advance("Recon is done. ADVANCE_PHASE to enumeration.")
        assert manager.scan_state.phase == ScanPhase.ENUMERATION

    def test_check_phase_advance_without_keyword(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager._check_phase_advance("Running nmap next.")
        assert manager.scan_state.phase == ScanPhase.RECON

    def test_parse_args_string(self):
        args = ManagerAgent._parse_args('{"target": "example.com"}')
        assert args == {"target": "example.com"}

    def test_parse_args_dict(self):
        args = ManagerAgent._parse_args({"target": "example.com"})
        assert args == {"target": "example.com"}

    def test_parse_args_invalid(self):
        args = ManagerAgent._parse_args("not json")
        assert args == {}

    def test_extract_key_evidence(self):
        output = "80/tcp open http\n443/tcp open https\nSome noise line"
        evidence = ManagerAgent._extract_key_evidence(output)
        assert any("open" in e for e in evidence)


class TestScanRunnerPreflight:
    """Tests for Docker toolbox preflight checks."""

    def _runner(self) -> ScanRunner:
        return ScanRunner(TUIEventManager())

    @pytest.mark.asyncio
    async def test_preflight_gates_missing_docker_tools(self, monkeypatch):
        runner = self._runner()

        class FakeInventory:
            def list_tools(self):
                return {
                    "nuclei": "nuclei",
                    "katana": "katana",
                    "searchsploit": "searchsploit",
                    "web_search": "web_search",
                    "complete_scan": "complete_scan",
                }

        class FakeExecutor:
            async def run_command(self, command, cwd=None, env=None, stdin=None):
                return SimpleNamespace(
                    exit_code=0,
                    stdout="nuclei=1\nkatana=0\nsearchsploit=0\n",
                    stderr="",
                )

        async def fake_get_docker_executor(*args, **kwargs):
            return FakeExecutor()

        monkeypatch.setattr("kodiak.core.scan_runner.get_docker_executor", fake_get_docker_executor)

        allowed, missing = await runner._preflight_available_tools(FakeInventory())

        assert set(missing) == {"katana", "searchsploit"}
        assert "nuclei" in allowed
        assert "katana" not in allowed
        assert "searchsploit" not in allowed
        assert "web_search" in allowed
        assert "complete_scan" in allowed

    @pytest.mark.asyncio
    async def test_preflight_failure_keeps_all_tools_enabled(self, monkeypatch):
        runner = self._runner()

        class FakeInventory:
            def list_tools(self):
                return {"nuclei": "nuclei", "katana": "katana", "web_search": "web_search"}

        class FakeExecutor:
            async def run_command(self, command, cwd=None, env=None, stdin=None):
                return SimpleNamespace(exit_code=2, stdout="", stderr="docker error")

        async def fake_get_docker_executor(*args, **kwargs):
            return FakeExecutor()

        monkeypatch.setattr("kodiak.core.scan_runner.get_docker_executor", fake_get_docker_executor)

        allowed, missing = await runner._preflight_available_tools(FakeInventory())

        assert set(allowed) == {"nuclei", "katana", "web_search"}
        assert missing == []

    @pytest.mark.asyncio
    async def test_preflight_probe_script_uses_safe_loop_separators(self, monkeypatch):
        runner = self._runner()
        captured = {}

        class FakeInventory:
            def list_tools(self):
                return {"nuclei": "nuclei", "whatweb": "whatweb"}

        class FakeExecutor:
            async def run_command(self, command, cwd=None, env=None, stdin=None):
                captured["command"] = command
                return SimpleNamespace(exit_code=0, stdout="nuclei=1\nwhatweb=1\n", stderr="")

        async def fake_get_docker_executor(*args, **kwargs):
            return FakeExecutor()

        monkeypatch.setattr("kodiak.core.scan_runner.get_docker_executor", fake_get_docker_executor)

        allowed, missing = await runner._preflight_available_tools(FakeInventory())

        assert set(allowed) == {"nuclei", "whatweb"}
        assert missing == []
        script = captured["command"][2]
        assert "fi\ndone" in script
