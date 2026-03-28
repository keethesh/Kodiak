import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kodiak.core.analyst import AnalystAgent, AnalystResponse
from kodiak.core.planner import PlannerAgent
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.models import (
    Hypothesis,
    HypothesisStatus,
    HypothesisType,
    ObservationType,
    WorkUnit,
    WorkUnitStatus,
)


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


@pytest.mark.asyncio
async def test_analyst_persists_structured_state_from_urls_and_tech():
    calls = {"observations": [], "capabilities": [], "hypotheses": []}

    class RecordingStructuredStore:
        scan_id = uuid4()

        async def add_observation(self, session, **kwargs):
            calls["observations"].append(kwargs)

        async def add_capability(self, session, **kwargs):
            calls["capabilities"].append(kwargs)

        async def add_hypothesis(self, session, **kwargs):
            calls["hypotheses"].append(kwargs)

    analyst = AnalystAgent(store=RecordingStructuredStore())
    parsed = AnalystResponse(analysis="structured")
    work_unit = WorkUnit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        targets_json=json.dumps(["https://app.example.com"]),
        targets_hash="hash-1",
        command_template="httpx ...",
        status=WorkUnitStatus.COMPLETED,
        result_stdout=(
            "https://app.example.com/login [200]\n"
            "https://app.example.com/admin [403]\n"
            "https://app.example.com/api/users?id=7\n"
            "WordPress Apache"
        ),
        result_stderr="",
    )

    await analyst._persist_structured_state(object(), parsed, [work_unit])

    observation_types = {call["observation_type"] for call in calls["observations"]}
    capability_types = {call["capability_type"] for call in calls["capabilities"]}
    hypothesis_types = {call["hypothesis_type"] for call in calls["hypotheses"]}

    assert ObservationType.PARAMETERIZED_URL in observation_types
    assert ObservationType.LOGIN_SURFACE in observation_types
    assert ObservationType.ADMIN_SURFACE in observation_types
    assert ObservationType.API_SURFACE in observation_types
    assert ObservationType.TECHNOLOGY in observation_types
    assert hypothesis_types >= {
        HypothesisType.INJECTION_FOLLOWUP,
        HypothesisType.AUTH_FOLLOWUP,
        HypothesisType.ADMIN_FOLLOWUP,
        HypothesisType.API_LOGIC_FOLLOWUP,
        HypothesisType.TECH_FOLLOWUP,
    }
    assert capability_types


@pytest.mark.asyncio
async def test_planner_processes_pending_hypotheses_into_followup_work(monkeypatch):
    class HypothesisStore(RecordingStore):
        def __init__(self):
            super().__init__()
            self.marked = []
            self.hypotheses = [
                Hypothesis(
                    scan_id=self.scan_id,
                    project_id=uuid4(),
                    type=HypothesisType.INJECTION_FOLLOWUP,
                    target="https://app.example.com/items?id=7",
                    key="inj-1",
                    rationale="parameterized URL",
                    confidence=0.8,
                    status=HypothesisStatus.PENDING,
                ),
                Hypothesis(
                    scan_id=self.scan_id,
                    project_id=uuid4(),
                    type=HypothesisType.ADMIN_FOLLOWUP,
                    target="https://app.example.com/admin",
                    key="admin-1",
                    rationale="admin surface",
                    confidence=0.8,
                    status=HypothesisStatus.PENDING,
                ),
            ]

        async def get_hypotheses(self, session, statuses=None, limit=100):
            return list(self.hypotheses)

        async def mark_hypothesis_status(self, session, hypothesis_ids, status):
            self.marked.append((tuple(hypothesis_ids), status))

    store = HypothesisStore()
    planner = PlannerAgent(store=store, target="https://example.com")

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._process_hypotheses()

    techniques = {call["technique"] for call in store.enqueued}
    assert "hypothesis_sqlmap_followup" in techniques
    assert "hypothesis_admin_surface_followup" in techniques
    assert store.marked[0][1] == HypothesisStatus.QUEUED


@pytest.mark.asyncio
async def test_planner_refreshes_local_state_from_observations(monkeypatch):
    store = SimpleNamespace(
        scan_id=uuid4(),
        get_observations=None,
    )
    planner = PlannerAgent(store=store, target="https://example.com")

    observations = [
        SimpleNamespace(type=ObservationType.LIVE_HTTP, target="https://api.example.com", key="https://api.example.com"),
        SimpleNamespace(type=ObservationType.PARAMETERIZED_URL, target="https://api.example.com/users?id=1", key="https://api.example.com/users?id=1"),
        SimpleNamespace(type=ObservationType.TECHNOLOGY, target="https://api.example.com", key="wordpress"),
    ]

    async def get_observations(session, limit=250):
        return observations

    store.get_observations = get_observations

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._refresh_state_from_store()

    assert planner._live_http_origins["api.example.com"] == "https://api.example.com"
    assert "https://api.example.com/users?id=1" in planner._parameterized_urls
    assert "wordpress" in planner._detected_techs["https://api.example.com"]
