from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from kodiak.api.events import TUIEventManager
from kodiak.core.analyst import AnalystResult
from kodiak.core.planner import PlannerAgent


@pytest.mark.asyncio
async def test_orchestrator_marks_failed_when_agent_task_raises(monkeypatch):
    from kodiak.core import multi_agent_orchestrator as runtime

    class FakeStore:
        def __init__(self, project_id, scan_id):
            self.project_id = project_id
            self.scan_id = scan_id

        async def get_findings(self, session, limit=1000):
            return []

    class CrashingPlanner:
        def __init__(self, store, target, instructions="", event_manager=None, tool_availability=None):
            self._cycle_count = 0

        async def run(self, cycle_interval=8.0, max_cycles=200):
            raise RuntimeError("planner exploded")

    class IdleAnalyst:
        def __init__(self, store, instructions="", event_manager=None):
            self._cycle_count = 0

        async def run(self, **kwargs):
            return AnalystResult(
                findings_count=0,
                notes_count=0,
                directives_count=0,
                phase_recommendation="continue",
            )

    async def fake_worker_loop(**kwargs):
        return {"executed": 0, "failed": 0, "timed_out": 0}

    async def fake_init_db():
        return None

    async def fake_get_session():
        yield object()

    monkeypatch.setattr(runtime, "SharedScanStore", FakeStore)
    monkeypatch.setattr(runtime, "PlannerAgent", CrashingPlanner)
    monkeypatch.setattr(runtime, "AnalystAgent", IdleAnalyst)
    monkeypatch.setattr(runtime, "_worker_loop", fake_worker_loop)
    monkeypatch.setattr(runtime, "get_session", fake_get_session)
    import importlib

    engine_module = importlib.import_module("kodiak.database.engine")
    monkeypatch.setattr(engine_module, "init_db", fake_init_db)

    orchestrator = runtime.MultiAgentOrchestrator(
        event_manager=TUIEventManager(),
        num_workers=1,
        max_scan_duration=5,
    )
    result = await orchestrator.run(
        target="https://example.com",
        instructions="passive only",
        project_id=uuid4(),
        scan_id=uuid4(),
    )

    assert result.status == "failed"
    assert "Runtime task failures: 1" in result.summary


@pytest.mark.asyncio
async def test_orchestrator_passes_instructions_to_agents(monkeypatch):
    from kodiak.core import multi_agent_orchestrator as runtime

    captures = {"planner": None, "analyst": None}

    class FakeStore:
        def __init__(self, project_id, scan_id):
            self.project_id = project_id
            self.scan_id = scan_id

        async def get_findings(self, session, limit=1000):
            return []

    class Planner:
        def __init__(self, store, target, instructions="", event_manager=None, tool_availability=None):
            captures["planner"] = instructions
            self._cycle_count = 1

        async def run(self, cycle_interval=8.0, max_cycles=200):
            return {"cycles": 1, "input_tokens": 0, "output_tokens": 0}

    class Analyst:
        def __init__(self, store, instructions="", event_manager=None):
            captures["analyst"] = instructions
            self._cycle_count = 1

        async def run(self, **kwargs):
            return AnalystResult(
                findings_count=0,
                notes_count=0,
                directives_count=0,
                phase_recommendation="continue",
            )

    async def fake_worker_loop(**kwargs):
        return {"executed": 0, "failed": 0, "timed_out": 0}

    async def fake_init_db():
        return None

    async def fake_get_session():
        yield object()

    monkeypatch.setattr(runtime, "SharedScanStore", FakeStore)
    monkeypatch.setattr(runtime, "PlannerAgent", Planner)
    monkeypatch.setattr(runtime, "AnalystAgent", Analyst)
    monkeypatch.setattr(runtime, "_worker_loop", fake_worker_loop)
    monkeypatch.setattr(runtime, "get_session", fake_get_session)
    import importlib

    engine_module = importlib.import_module("kodiak.database.engine")
    monkeypatch.setattr(engine_module, "init_db", fake_init_db)

    orchestrator = runtime.MultiAgentOrchestrator(
        event_manager=TUIEventManager(),
        num_workers=1,
        max_scan_duration=5,
    )
    result = await orchestrator.run(
        target="https://example.com",
        instructions="Do not run destructive tests",
        project_id=uuid4(),
        scan_id=uuid4(),
    )

    assert result.status == "completed"
    assert captures["planner"] == "Do not run destructive tests"
    assert captures["analyst"] == "Do not run destructive tests"


@pytest.mark.asyncio
async def test_event_manager_normalizes_command_result_payload():
    bridge = SimpleNamespace(
        send_tool_update=AsyncMock(),
        send_agent_update=AsyncMock(),
        send_finding_update=AsyncMock(),
    )
    manager = TUIEventManager(bridge)

    captured = []
    manager.subscribe("tool_complete", lambda event: captured.append(event))

    raw_result = SimpleNamespace(
        exit_code=-1,
        stdout="partial-output",
        stderr="timed out",
        timed_out=True,
        duration_seconds=12.3,
    )
    await manager.emit_tool_complete("nmap", raw_result, scan_id="scan-1")

    assert captured
    payload = captured[0].data
    assert payload["status"] == "timeout"
    assert payload["success"] is False
    assert payload["output"] == "partial-output"
    assert payload["error"] == "timed out"
    assert payload["data"]["exit_code"] == -1
    assert payload["data"]["timed_out"] is True
    assert bridge.send_tool_update.await_count == 1


@pytest.mark.asyncio
async def test_planner_rejects_unsafe_attack_hint_target(monkeypatch):
    class RecordingStore:
        def __init__(self):
            self.scan_id = uuid4()
            self.enqueued = []

        async def enqueue_work_unit(self, session, **kwargs):
            self.enqueued.append(kwargs)
            return object()

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    store = RecordingStore()
    planner = PlannerAgent(
        store=store,
        target="https://example.com",
        instructions="No destructive actions",
    )
    await planner._process_attack_hint(
        {
            "technique": "vulnerability_scanning",
            "targets": ["https://example.com;rm -rf /"],
            "context": "test hardening",
        }
    )

    assert store.enqueued == []


@pytest.mark.asyncio
async def test_planner_injects_operator_instruction_context(monkeypatch):
    class RecordingStore:
        def __init__(self):
            self.scan_id = uuid4()
            self.enqueued = []

        async def enqueue_work_unit(self, session, **kwargs):
            self.enqueued.append(kwargs)
            return object()

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    store = RecordingStore()
    planner = PlannerAgent(
        store=store,
        target="https://example.com",
        instructions="Passive-first, avoid exploitation",
    )
    await planner._process_attack_hint(
        {
            "technique": "vulnerability_scanning",
            "targets": ["https://example.com"],
            "context": "hint",
        }
    )

    assert store.enqueued
    assert any("operator_instructions:" in (entry.get("context") or "") for entry in store.enqueued)

