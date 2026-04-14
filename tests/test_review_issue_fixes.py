from types import SimpleNamespace
from uuid import uuid4

import pytest

from kodiak.core.kernel_result import KernelResult
from kodiak.core.tool_availability import ToolAvailability, get_default_tools_to_check
from kodiak.database.engine import _validate_sqlite_schema


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


@pytest.mark.asyncio
async def test_validate_sqlite_schema_allows_bootstrap_when_workunit_missing():
    class FakeConn:
        async def execute(self, _statement):
            return _FakeResult([])

    await _validate_sqlite_schema(FakeConn())


def test_get_default_tools_to_check_is_normalized():
    tools = get_default_tools_to_check()
    assert "nuclei" in tools
    assert all(tool == tool.strip().lower() for tool in tools)


def test_attack_hint_gating_uses_real_command_tool_family():
    from kodiak.core.planner import PlannerAgent

    planner = PlannerAgent.__new__(PlannerAgent)
    planner._tool_availability = ToolAvailability(unavailable_tools={"wafw00f"})
    planner._current_phase = "recon"
    planner._dedupe_preserve_order = lambda targets: targets
    planner._compose_context = lambda context: context
    planner._canonical_hint_target = lambda target: target

    specs = planner._expand_attack_hint_specs(
        "waf_detection_followup",
        ["https://example.com"],
        {"context": "hint"},
    )
    assert specs == []


@pytest.mark.asyncio
async def test_scan_runner_uses_projection_data_for_summary(monkeypatch):
    from kodiak.core import scan_runner as runtime

    project = SimpleNamespace(id=uuid4(), name="Test Project")
    scan_job = SimpleNamespace(id=uuid4())

    class FakeEventManager:
        def subscribe_scan(self, _scan_id, _handler):
            return None

        def unsubscribe_scan(self, _scan_id, _handler):
            return None

        async def emit_scan_started(self, **_kwargs):
            return None

        async def emit_scan_completed(self, **_kwargs):
            return None

    class FakeStore:
        def __init__(self, project_id, scan_id):
            self.project_id = project_id
            self.scan_id = scan_id

        async def build_projection(self, _session):
            return {"asset_count": 9, "work_queue": {"PENDING": 2, "COMPLETED": 4}}

    class FakeOrchestrator:
        def __init__(self, event_manager, num_workers, max_scan_duration):
            self.event_manager = event_manager
            self.num_workers = num_workers
            self.max_scan_duration = max_scan_duration

        async def run(self, **_kwargs):
            return KernelResult(
                status="completed",
                summary="ok",
                findings_count=0,
                iterations=1,
            )

    async def fake_get_session():
        yield object()

    async def fake_get_or_create_project(self, session, name, project_id=None):
        return project

    async def fake_prepare_scan_job(self, **kwargs):
        return scan_job

    async def fake_preflight_tools(self, inventory):
        return [], []

    async def fake_preflight_dns(self):
        return None

    async def fake_update_status(session, scan_id, status):
        return None

    async def fake_get_nodes(session, project_id):
        return [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    async def fake_get_attempts(session, scan_id, limit=400):
        return []

    monkeypatch.setattr(runtime, "get_session", fake_get_session)
    monkeypatch.setattr(runtime, "SharedScanStore", FakeStore)
    monkeypatch.setattr(runtime.ScanRunner, "_get_or_create_project", fake_get_or_create_project)
    monkeypatch.setattr(runtime.ScanRunner, "_prepare_scan_job", fake_prepare_scan_job)
    monkeypatch.setattr(runtime.ScanRunner, "_preflight_available_tools", fake_preflight_tools)
    monkeypatch.setattr(runtime.ScanRunner, "_preflight_dns_check", fake_preflight_dns)
    monkeypatch.setattr("kodiak.core.multi_agent_orchestrator.MultiAgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(runtime.crud.scan_job, "update_status", fake_update_status)
    monkeypatch.setattr(runtime.crud.node, "get_nodes_by_project", fake_get_nodes)
    monkeypatch.setattr(runtime.crud.attempt, "get_attempts_by_scan", fake_get_attempts)
    monkeypatch.setattr(runtime, "write_scan_report", lambda **kwargs: {})

    runner = runtime.ScanRunner(event_manager=FakeEventManager())
    result = await runner.run(target="https://example.com")
    assert result.status == "completed"
    assert result.asset_count == 9
