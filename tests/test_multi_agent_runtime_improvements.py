import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kodiak.core.analyst import AnalystAgent
from kodiak.core.planner import PlannerAgent
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.models import WorkUnit, WorkUnitStatus


class RecordingStore:
    def __init__(self):
        self.scan_id = uuid4()
        self.enqueued = []

    async def enqueue_work_unit(self, session, **kwargs):
        self.enqueued.append(kwargs)
        return object()


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


@pytest.mark.asyncio
async def test_planner_generates_single_scope_work_units_per_live_http_target(monkeypatch):
    store = RecordingStore()
    planner = PlannerAgent(store=store, target="https://example.com")
    planner._current_phase = "enumeration"
    planner._live_http_hosts = {"a.example.com", "b.example.com"}
    planner._live_http_origins = {
        "a.example.com": "https://a.example.com",
        "b.example.com": "https://b.example.com",
    }

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    generated = await planner._generate_work_units()

    ffuf_targets = [
        tuple(call["targets"])
        for call in store.enqueued
        if call["technique"] == "ffuf_common"
    ]

    assert generated >= 6
    assert ("https://a.example.com",) in ffuf_targets
    assert ("https://b.example.com",) in ffuf_targets


@pytest.mark.asyncio
async def test_planner_updates_http_origins_and_parameterized_urls_from_completed_results(monkeypatch):
    store = SimpleNamespace(scan_id=uuid4())
    planner = PlannerAgent(store=store, target="https://example.com")

    httpx_unit = WorkUnit(
        scan_id=store.scan_id,
        project_id=uuid4(),
        technique="httpx_primary",
        targets_json='["https://app.example.com"]',
        targets_hash="hash-httpx",
        command_template="httpx ...",
        status=WorkUnitStatus.COMPLETED,
        result_stdout="https://app.example.com [200] [Example App]\nhttps://app.example.com/search?q=test",
        result_stderr="",
    )
    gau_unit = WorkUnit(
        scan_id=store.scan_id,
        project_id=uuid4(),
        technique="gau",
        targets_json='["example.com"]',
        targets_hash="hash-gau",
        command_template="gau example.com --subs",
        status=WorkUnitStatus.COMPLETED,
        result_stdout="https://app.example.com/api/items?id=42",
        result_stderr="",
    )

    class FakeSession:
        async def execute(self, statement):
            return _FakeResult([httpx_unit, gau_unit])

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._update_state_from_results()

    assert planner._live_http_origins["app.example.com"] == "https://app.example.com"
    assert "https://app.example.com/api/items?id=42" in planner._parameterized_urls
    assert "https://app.example.com/search?q=test" in planner._parameterized_urls


@pytest.mark.asyncio
async def test_analyst_waits_for_planner_done_before_completing(monkeypatch):
    class IdleStore:
        scan_id = uuid4()

        async def get_unanalyzed_results(self, session, limit=15):
            return []

        async def get_pending_count(self, session):
            return 0

    class FakeSession:
        pass

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr("kodiak.core.analyst.get_session", fake_get_session)

    analyst = AnalystAgent(store=IdleStore())
    planner_done = asyncio.Event()
    task = asyncio.create_task(
        analyst.run(
            poll_interval=0.01,
            max_cycles=5,
            planner_done_event=planner_done,
            settle_cycles=2,
        )
    )

    await asyncio.sleep(0.03)
    assert task.done() is False

    planner_done.set()
    result = await asyncio.wait_for(task, timeout=0.2)

    assert result.phase_recommendation == "complete"


@pytest.mark.asyncio
async def test_claim_work_unit_serializes_same_scope_heavy_tool_families():
    scan_id = uuid4()
    project_id = uuid4()
    store = SharedScanStore(project_id=project_id, scan_id=scan_id)

    active = WorkUnit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_critical",
        targets_json='["https://a.example.com"]',
        targets_hash="scope-a",
        command_template="nuclei -u https://a.example.com -severity critical",
        status=WorkUnitStatus.CLAIMED,
    )
    blocked = WorkUnit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_cves",
        targets_json='["https://a.example.com"]',
        targets_hash="scope-a",
        command_template="nuclei -u https://a.example.com -tags cve",
        status=WorkUnitStatus.PENDING,
    )
    allowed = WorkUnit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_config",
        targets_json='["https://b.example.com"]',
        targets_hash="scope-b",
        command_template="nuclei -u https://b.example.com -tags config",
        status=WorkUnitStatus.PENDING,
    )

    class FakeSession:
        def __init__(self):
            self._responses = [
                _FakeResult([active]),
                _FakeResult([blocked, allowed]),
            ]
            self.added = []
            self.committed = False

        async def execute(self, statement):
            return self._responses.pop(0)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

        async def refresh(self, obj):
            return None

        async def rollback(self):
            return None

    session = FakeSession()

    claimed = await store.claim_work_unit(session, "worker-1")

    assert claimed is allowed
    assert claimed.claimed_by == "worker-1"
    assert session.committed is True
