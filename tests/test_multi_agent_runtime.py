import asyncio
from types import SimpleNamespace

import pytest

from kodiak.api.events import TUIEventManager
from kodiak.core.scan_runner import ScanRunner
from kodiak.core.scan_state import ScanState, ScanPhase
from kodiak.core.manager import ManagerAgent
from kodiak.core.response_schema import (
    Command,
    Discovery,
    Finding,
    KodiakResponse,
    Note,
    PhaseAction,
    SeverityEnum,
    NoteCategoryEnum,
)


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


# =====================================================================
# Response Schema Tests
# =====================================================================

class TestResponseSchema:
    """Tests for the KodiakResponse structured output schema."""

    def test_command_requires_rationale(self):
        """Every command must have a rationale explaining why it's being run."""
        cmd = Command(
            command="nmap -sV -p- example.com",
            rationale="Full port scan to discover all services on the target",
        )
        assert cmd.rationale
        assert cmd.timeout == 300  # default

    def test_command_custom_timeout(self):
        cmd = Command(
            command="sqlmap -u http://target.com --batch",
            rationale="Test for SQL injection",
            timeout=600,
        )
        assert cmd.timeout == 600

    def test_kodiak_response_minimal(self):
        """Minimal valid response: just analysis and phase_action."""
        resp = KodiakResponse(
            analysis="Initial scan — nothing discovered yet.",
            phase_action=PhaseAction.CONTINUE,
        )
        assert resp.commands == []
        assert resp.findings == []
        assert resp.notes == []
        assert resp.scan_summary is None

    def test_kodiak_response_full(self):
        """Full response with commands, findings, notes, discoveries."""
        resp = KodiakResponse(
            analysis="Found open ports, testing for vulns.",
            commands=[
                Command(
                    command="nuclei -u http://target.com -rl 20",
                    rationale="Scan for known vulnerabilities",
                )
            ],
            discoveries=Discovery(
                hosts=["sub.target.com"],
                ports={"target.com": [80, 443]},
                technologies={"target.com": ["Apache 2.4"]},
            ),
            findings=[
                Finding(
                    title="SQL Injection — POST /login",
                    severity=SeverityEnum.HIGH,
                    target="target.com",
                    description="Boolean-based blind SQLi in username param",
                    evidence="' OR 1=1-- returns 200",
                    remediation="Use parameterized queries",
                )
            ],
            notes=[
                Note(
                    category=NoteCategoryEnum.BEHAVIORAL,
                    target="target.com",
                    content="WAF blocks after 10 req/s",
                )
            ],
            phase_action=PhaseAction.ADVANCE,
        )
        assert len(resp.commands) == 1
        assert resp.commands[0].rationale == "Scan for known vulnerabilities"
        assert len(resp.findings) == 1
        assert resp.findings[0].severity == SeverityEnum.HIGH
        assert len(resp.notes) == 1
        assert resp.phase_action == PhaseAction.ADVANCE

    def test_kodiak_response_complete_requires_summary(self):
        """When phase_action is COMPLETE, scan_summary should be provided."""
        resp = KodiakResponse(
            analysis="Scan complete.",
            phase_action=PhaseAction.COMPLETE,
            scan_summary="Found 3 vulnerabilities: 1 critical, 2 high.",
        )
        assert resp.scan_summary is not None

    def test_kodiak_response_from_json(self):
        """Parse a JSON string into KodiakResponse."""
        import json
        data = {
            "analysis": "Starting recon phase",
            "commands": [
                {
                    "command": "subfinder -d example.com -silent",
                    "rationale": "Enumerate subdomains",
                    "timeout": 120,
                }
            ],
            "discoveries": {"hosts": [], "ports": {}, "technologies": {}, "urls": []},
            "findings": [],
            "notes": [],
            "phase_action": "continue",
            "scan_summary": None,
        }
        resp = KodiakResponse.model_validate(data)
        assert resp.commands[0].command == "subfinder -d example.com -silent"
        assert resp.phase_action == PhaseAction.CONTINUE


# =====================================================================
# Manager Agent Tests
# =====================================================================

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

    def test_system_prompt_contains_tool_catalog(self):
        """System prompt should describe tools as text, not function declarations."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        assert "<tool_catalog>" in prompt
        assert "subfinder" in prompt
        assert "nmap" in prompt
        assert "nuclei" in prompt
        assert "sqlmap" in prompt
        assert "curl" in prompt

    def test_system_prompt_no_reasoning_line_limit(self):
        """Reasoning line limit was removed — Gemini 3 handles token efficiency."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        assert "3–4 lines" not in prompt
        assert "3-4 lines" not in prompt

    def test_system_prompt_no_hardcoded_subdomain_list(self):
        """Hardcoded subdomain priority list was removed."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        # The old prompt had a specific list: "prelive, staging, dev, gitlab, db, shop"
        assert "prelive, staging, dev, gitlab, db, shop" not in prompt

    def test_system_prompt_context_before_task(self):
        """Scan state should appear before the task (Gemini 3 best practice)."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        state_idx = prompt.index("<scan_state>")
        task_idx = prompt.index("<task>")
        assert state_idx < task_idx

    def test_system_prompt_has_recording_section(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        assert "<recording>" in prompt
        assert "findings" in prompt
        assert "notes" in prompt
        assert "dead_end" in prompt

    def test_system_prompt_waf_context_offensive(self):
        """When WAF detected, prompt should have offensive bypass guidance."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager.scan_state.waf_detected = True
        prompt = manager._build_system_prompt()
        assert "<waf_context>" in prompt
        assert "origin" in prompt.lower() or "bypass" in prompt.lower()
        assert "Adapt" in prompt or "adapt" in prompt

    def test_parse_kodiak_response_valid_json(self):
        """Valid JSON should parse into KodiakResponse."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        json_str = '{"analysis":"test","commands":[],"phase_action":"continue"}'
        resp = manager._parse_kodiak_response(json_str)
        assert resp is not None
        assert resp.analysis == "test"
        assert resp.phase_action == PhaseAction.CONTINUE

    def test_parse_kodiak_response_invalid_json(self):
        """Invalid JSON should return None."""
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        resp = manager._parse_kodiak_response("not valid json at all")
        assert resp is None

    def test_apply_discoveries_updates_scan_state(self):
        """Discoveries from LLM response should update scan state."""
        from kodiak.core.response_schema import HostPorts, HostTechs
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")

        resp = KodiakResponse(
            analysis="Found new hosts and ports",
            discoveries=Discovery(
                hosts=["sub1.example.com", "sub2.example.com"],
                ports=[HostPorts(host="example.com", ports=[80, 443, 8080])],
                technologies=[HostTechs(host="example.com", technologies=["Apache 2.4.41", "PHP 7.4"])],
                urls=["https://example.com/admin"],
            ),
            phase_action=PhaseAction.CONTINUE,
        )

        manager._apply_discoveries(resp)

        assert "sub1.example.com" in manager.scan_state.targets
        assert "sub2.example.com" in manager.scan_state.targets
        ts = manager.scan_state.targets["example.com"]
        assert 80 in ts.ports
        assert 443 in ts.ports
        assert 8080 in ts.ports
        assert "Apache 2.4.41" in ts.technologies

    def test_system_prompt_includes_prior_knowledge_when_available(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager._prior_knowledge = (
            "<prior_knowledge>\n"
            "<prior_notes count=\"1\">\n"
            "  [2025-01-15 behavioral] (example.com) WAF rate limit 10/s\n"
            "</prior_notes>\n"
            "</prior_knowledge>"
        )
        prompt = manager._build_system_prompt()
        assert "<prior_knowledge>" in prompt
        assert "WAF rate limit" in prompt

    def test_system_prompt_omits_prior_knowledge_when_empty(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager._prior_knowledge = ""
        prompt = manager._build_system_prompt()
        assert "<prior_knowledge>" not in prompt
        # But recording section should still be there
        assert "<recording>" in prompt


# =====================================================================
# Scan Runner Preflight Tests
# =====================================================================

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


# =====================================================================
# Engagement Memory Tests
# =====================================================================

class TestEngagementMemoryModels:
    """Tests for EngagementNote and enriched Finding models."""

    def test_engagement_note_model_fields(self):
        from kodiak.database.models import EngagementNote, NoteCategory
        note = EngagementNote(
            project_id="00000000-0000-0000-0000-000000000001",
            scan_id="00000000-0000-0000-0000-000000000002",
            category=NoteCategory.ATTACK_HINT,
            target="example.com",
            content="Parameter id= is suspiciously reflective",
        )
        assert note.category == NoteCategory.ATTACK_HINT
        assert note.target == "example.com"
        assert "reflective" in note.content

    def test_note_category_enum_values(self):
        from kodiak.database.models import NoteCategory
        assert NoteCategory.RECON_INTEL == "recon_intel"
        assert NoteCategory.BEHAVIORAL == "behavioral"
        assert NoteCategory.ATTACK_HINT == "attack_hint"
        assert NoteCategory.DEAD_END == "dead_end"
        assert NoteCategory.GENERAL == "general"

    def test_enriched_finding_model_fields(self):
        from kodiak.database.models import Finding, FindingSeverity
        finding = Finding(
            project_id="00000000-0000-0000-0000-000000000001",
            title="SQL Injection — POST /login",
            description="The username parameter is vulnerable to boolean-based blind SQLi",
            severity=FindingSeverity.CRITICAL,
            target="example.com",
            tool="sqlmap",
            vulnerability_type="sqli",
            exploitation_steps="1. Run sqlmap -u ...\n2. Use --dump flag",
            impact="Full database read, potential RCE via INTO OUTFILE",
            poc="' OR 1=1-- returns 200 + session cookie",
            remediation="Use parameterized queries",
            raw_evidence="sqlmap output...",
        )
        assert finding.severity == FindingSeverity.CRITICAL
        assert finding.vulnerability_type == "sqli"
        assert "parameterized" in finding.remediation
        assert finding.target == "example.com"
        assert finding.tool == "sqlmap"

    def test_finding_has_optional_target(self):
        from kodiak.database.models import Finding
        finding = Finding(
            title="Test",
            description="desc",
        )
        assert finding.target is None
        assert finding.node_id is None
        assert finding.project_id is None


class TestEngagementMemoryTools:
    """Tests for save_note and save_finding tool definitions."""

    def test_save_note_tool_schema(self):
        from kodiak.core.tools.definitions.engagement_memory import SaveNoteTool
        tool = SaveNoteTool()
        assert tool.name == "save_note"
        schema = tool.parameters_schema
        assert "target" in schema["properties"]
        assert "category" in schema["properties"]
        assert "content" in schema["properties"]
        assert set(schema["required"]) == {"target", "category", "content"}
        # Category should have enum
        assert "enum" in schema["properties"]["category"]

    def test_save_finding_tool_schema(self):
        from kodiak.core.tools.definitions.engagement_memory import SaveFindingTool
        tool = SaveFindingTool()
        assert tool.name == "save_finding"
        schema = tool.parameters_schema
        assert "target" in schema["properties"]
        assert "title" in schema["properties"]
        assert "severity" in schema["properties"]
        assert "exploitation_steps" in schema["properties"]
        assert "poc" in schema["properties"]
        assert "remediation" in schema["properties"]
        assert set(schema["required"]) == {"target", "title", "severity", "description"}

    @pytest.mark.asyncio
    async def test_save_note_tool_execute(self):
        from kodiak.core.tools.definitions.engagement_memory import SaveNoteTool
        tool = SaveNoteTool()
        result = await tool.execute(
            target="example.com",
            category="behavioral",
            content="WAF blocks after 10 req/s",
        )
        assert result.success
        assert result.data["saved"]
        assert result.data["category"] == "behavioral"
        assert "WAF" in result.output

    @pytest.mark.asyncio
    async def test_save_finding_tool_execute(self):
        from kodiak.core.tools.definitions.engagement_memory import SaveFindingTool
        tool = SaveFindingTool()
        result = await tool.execute(
            target="example.com",
            title="XSS in search",
            severity="high",
            description="Reflected XSS in search param",
        )
        assert result.success
        assert result.data["saved"]
        assert "HIGH" in result.output

    def test_tools_registered_in_inventory(self):
        from kodiak.core.tools.inventory import ToolInventory
        inv = ToolInventory()
        inv.initialize_tools()
        assert inv.get("save_note") is not None
        assert inv.get("save_finding") is not None


class TestManagerPriorKnowledge:
    """Tests for prior knowledge loading and system prompt injection."""

    def _manager(self) -> ManagerAgent:
        from kodiak.core.tools.inventory import ToolInventory
        inv = ToolInventory()
        inv.initialize_tools()
        return ManagerAgent(
            event_manager=TUIEventManager(),
            tool_inventory=inv,
        )

    def test_system_prompt_includes_recording_section(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        assert "<recording>" in prompt
        assert "findings" in prompt
        assert "notes" in prompt
        assert "dead_end" in prompt

    def test_system_prompt_includes_prior_knowledge_when_available(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager._prior_knowledge = (
            "<prior_knowledge>\n"
            "<prior_notes count=\"1\">\n"
            "  [2025-01-15 behavioral] (example.com) WAF rate limit 10/s\n"
            "</prior_notes>\n"
            "</prior_knowledge>"
        )
        prompt = manager._build_system_prompt()
        assert "<prior_knowledge>" in prompt
        assert "WAF rate limit" in prompt

    def test_system_prompt_omits_prior_knowledge_when_empty(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        manager._prior_knowledge = ""
        prompt = manager._build_system_prompt()
        assert "<prior_knowledge>" not in prompt
        # But recording section should still be there
        assert "<recording>" in prompt

    def test_system_prompt_task_is_last_section(self):
        manager = self._manager()
        manager.scan_state = ScanState(target="example.com")
        prompt = manager._build_system_prompt()
        # <task> should be after <recording>
        rec_idx = prompt.index("<recording>")
        task_idx = prompt.index("<task>")
        assert task_idx > rec_idx
