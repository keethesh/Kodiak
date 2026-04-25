import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kodiak.api.events import TUIEvent, TUIEventManager
from kodiak.core.analyst import AnalystAgent, AnalystResponse
from kodiak.core.interface import CoreInterface
from kodiak.core.multi_agent_orchestrator import _tool_name_for_unit, _unit_primary_target
from kodiak.core.planner import PlannerAgent
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.models import (
    CapabilityType,
    ScanStatus as DBScanStatus,
    DirectiveType,
    Hypothesis,
    HypothesisStatus,
    HypothesisType,
    ObservationType,
    ScanJob,
    ScanEventType,
    WorkUnit,
    WorkUnitStatus,
)
from kodiak.tui.state import AgentState, AppState, ScanState, ScanStatus


def make_workunit(
    scan_id,
    project_id,
    technique,
    target,
    status=WorkUnitStatus.PENDING,
    command_template="",
    scope_key=None,
    **kwargs,
) -> WorkUnit:
    """Create a WorkUnit with single-scope target fields."""
    scope = scope_key or target
    return WorkUnit(
        scan_id=scan_id,
        project_id=project_id,
        technique=technique,
        target=target,
        scope_key=scope,
        status=status,
        command_template=command_template,
        **kwargs,
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

    def all(self):
        return list(self._items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


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

    httpx_unit = make_workunit(
        scan_id=store.scan_id,
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://app.example.com",
        status=WorkUnitStatus.COMPLETED,
        command_template="httpx ...",
        result_stdout="https://app.example.com [200] [Example App]\nhttps://app.example.com/search?q=test",
        result_stderr="",
    )
    gau_unit = make_workunit(
        scan_id=store.scan_id,
        project_id=uuid4(),
        technique="gau",
        target="example.com",
        status=WorkUnitStatus.COMPLETED,
        command_template="gau example.com --subs",
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
async def test_planner_strips_ansi_sequences_before_extracting_parameterized_urls(monkeypatch):
    store = SimpleNamespace(scan_id=uuid4())
    planner = PlannerAgent(store=store, target="https://example.com")

    noisy_unit = make_workunit(
        scan_id=store.scan_id,
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://app.example.com",
        status=WorkUnitStatus.COMPLETED,
        command_template="httpx ...",
        result_stdout="https://app.example.com/search?q=test\x1b[0m",
        result_stderr="",
    )

    class FakeSession:
        async def execute(self, statement):
            return _FakeResult([noisy_unit])

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._update_state_from_results()

    assert planner._parameterized_urls == ["https://app.example.com/search?q=test"]


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

    active = make_workunit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_critical",
        target="https://a.example.com",
        scope_key="scope-a",
        command_template="nuclei -u https://a.example.com -severity critical",
        status=WorkUnitStatus.CLAIMED,
    )
    blocked = make_workunit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_cves",
        target="https://a.example.com",
        scope_key="scope-a",
        command_template="nuclei -u https://a.example.com -tags cve",
        status=WorkUnitStatus.PENDING,
    )
    allowed = make_workunit(
        scan_id=scan_id,
        project_id=project_id,
        technique="nuclei_config",
        target="https://b.example.com",
        scope_key="scope-b",
        command_template="nuclei -u https://b.example.com -tags config",
        status=WorkUnitStatus.PENDING,
    )
    class FakeClaimResult:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeSession:
        def __init__(self):
            self.refreshed = False
            self.committed = False

        async def execute(self, statement):
            text = str(statement)
            if "FROM workunit" in text and "status IN" in text:
                return _FakeResult([active])
            if "FROM workunit" in text and "status =" in text and "LIMIT" in text:
                return _FakeResult([blocked, allowed])
            if text.startswith("UPDATE workunit"):
                return FakeClaimResult(1)
            raise AssertionError(f"Unexpected statement: {text}")

        def add(self, obj):
            return None

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
    assert claimed.status == WorkUnitStatus.CLAIMED
    assert session.committed is True
    assert session.refreshed is False


@pytest.mark.asyncio
async def test_claim_work_unit_does_not_double_claim_same_unit():
    scan_id = uuid4()
    project_id = uuid4()
    store = SharedScanStore(project_id=project_id, scan_id=scan_id)
    unit_id = uuid4()

    pending_unit = make_workunit(
        id=unit_id,
        scan_id=scan_id,
        project_id=project_id,
        technique="subfinder",
        target="example.com",
        scope_key="scope-example",
        command_template="subfinder -d example.com -silent",
        status=WorkUnitStatus.PENDING,
    )
    claimed_unit = make_workunit(
        id=unit_id,
        scan_id=scan_id,
        project_id=project_id,
        technique="subfinder",
        target="example.com",
        scope_key="scope-example",
        command_template="subfinder -d example.com -silent",
        status=WorkUnitStatus.CLAIMED,
        claimed_by="worker-1",
    )

    class FakeClaimResult:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeSession:
        def __init__(self):
            self.phase = 0
            self.committed = 0

        async def execute(self, statement):
            text = str(statement)
            if "FROM workunit" in text and "status IN" in text:
                return _FakeResult([])
            if "FROM workunit" in text and "status =" in text and "LIMIT" in text:
                return _FakeResult([pending_unit] if self.phase == 0 else [])
            if text.startswith("UPDATE workunit"):
                rowcount = 1 if self.phase == 0 else 0
                self.phase += 1
                return FakeClaimResult(rowcount)
            if "WHERE workunit.id =" in text:
                return _FakeResult([claimed_unit])
            raise AssertionError(f"Unexpected statement: {text}")

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            return None

        def add(self, obj):
            return None

        async def refresh(self, obj):
            return None

    emitted = []

    async def fake_append_event(session, **kwargs):
        emitted.append(kwargs)
        return object()

    store.append_event = fake_append_event
    session = FakeSession()
    first = await store.claim_work_unit(session, "worker-1")
    second = await store.claim_work_unit(session, "worker-2")

    assert first is not None
    assert first.claimed_by == "worker-1"
    assert second is None
    assert emitted[0]["event_type"] == ScanEventType.WORK_UNIT_CLAIMED


@pytest.mark.asyncio
async def test_enqueue_work_unit_populates_single_scope_fields():
    scan_id = uuid4()
    project_id = uuid4()
    store = SharedScanStore(project_id=project_id, scan_id=scan_id)
    captured = {}

    class FakeSession:
        def add(self, obj):
            captured["unit"] = obj

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

        async def rollback(self):
            return None

    async def fake_append_event(session, **kwargs):
        return object()

    store.append_event = fake_append_event
    session = FakeSession()
    unit = await store.enqueue_work_unit(
        session,
        technique="httpx_primary",
        targets=["https://app.example.com"],
        command_template="echo 'https://app.example.com' | httpx -sc -title -tech-detect -silent",
    )

    assert unit is captured["unit"]
    assert unit.target == "https://app.example.com"
    assert unit.target_kind == "origin"
    assert unit.tool_family == "httpx"
    assert unit.scope_key == "https://app.example.com"


@pytest.mark.asyncio
async def test_enqueue_work_unit_rejects_multiple_targets():
    store = SharedScanStore(project_id=uuid4(), scan_id=uuid4())

    with pytest.raises(ValueError, match="exactly one target"):
        await store.enqueue_work_unit(
            object(),
            technique="httpx_primary",
            targets=["https://one.example.com", "https://two.example.com"],
            command_template="httpx -u {target}",
        )


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
    work_unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://app.example.com",
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
async def test_analyst_extracts_tls_names_services_and_legacy_stack_hypotheses():
    calls = {"observations": [], "capabilities": [], "hypotheses": []}

    class RecordingStructuredStore:
        scan_id = uuid4()

        async def add_observation(self, session, **kwargs):
            calls["observations"].append(kwargs)

        async def add_capability(self, session, **kwargs):
            calls["capabilities"].append(kwargs)

        async def add_hypothesis(self, session, **kwargs):
            calls["hypotheses"].append(kwargs)

        async def get_capabilities(self, session, limit=250):
            return []

        async def add_directive(self, session, **kwargs):
            return None

    analyst = AnalystAgent(store=RecordingStructuredStore())
    parsed = AnalystResponse(analysis="structured")
    work_unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="nmap_initial",
        target="metservice.intnet.mu",
        command_template="nmap ...",
        status=WorkUnitStatus.COMPLETED,
        result_stdout=(
            "443/tcp open https\n"
            "Service Info: OS: CentOS 6; CPE: cpe:/o:centos:centos:6\n"
            "Apache httpd 2.2.15 ((CentOS))\n"
            "PHP/5.3.27\n"
            "Subject Alternative Name: DNS:metservice.intnet.mu, DNS:adminmeteo.intnet.mu\n"
        ),
        result_stderr="",
    )

    await analyst._persist_structured_state(object(), parsed, [work_unit])

    observation_types = {call["observation_type"] for call in calls["observations"]}
    capability_types = {call["capability_type"] for call in calls["capabilities"]}
    hypothesis_types = {call["hypothesis_type"] for call in calls["hypotheses"]}
    hypothesis_targets = {call["target"] for call in calls["hypotheses"]}

    assert ObservationType.NETWORK_SERVICE in observation_types
    assert ObservationType.TLS_NAME in observation_types
    assert CapabilityType.NETWORK_SERVICE in capability_types
    assert HypothesisType.HIDDEN_HOST_FOLLOWUP in hypothesis_types
    assert HypothesisType.LEGACY_STACK_RCE_FOLLOWUP in hypothesis_types
    assert "adminmeteo.intnet.mu" in hypothesis_targets


@pytest.mark.asyncio
async def test_analyst_derives_chain_hypotheses_from_capability_combinations():
    calls = {"hypotheses": []}

    class ChainStore:
        scan_id = uuid4()

        async def get_capabilities(self, session, limit=250):
            host = "https://app.example.com"
            return [
                SimpleNamespace(type="auth_surface", target=f"{host}/login", key=f"{host}/login", details={}),
                SimpleNamespace(type="admin_surface", target=f"{host}/admin", key=f"{host}/admin", details={}),
                SimpleNamespace(type="api_surface", target=f"{host}/api", key=f"{host}/api", details={}),
                SimpleNamespace(type="input_surface", target=f"{host}/api/users?id=7", key=f"{host}/api/users?id=7", details={}),
                SimpleNamespace(type="tech_stack", target=host, key="wordpress", details={"tech": "wordpress"}),
            ]

        async def add_hypothesis(self, session, **kwargs):
            calls["hypotheses"].append(kwargs)

    analyst = AnalystAgent(store=ChainStore())

    await analyst._derive_chain_hypotheses(object())

    hypothesis_keys = {call["key"] for call in calls["hypotheses"]}
    hypothesis_types = {call["hypothesis_type"] for call in calls["hypotheses"]}

    assert "app.example.com:auth-admin-chain" in hypothesis_keys
    assert "app.example.com:api-input-chain" in hypothesis_keys
    assert "app.example.com:wordpress-admin-chain" in hypothesis_keys
    assert HypothesisType.ADMIN_FOLLOWUP in hypothesis_types
    assert HypothesisType.API_LOGIC_FOLLOWUP in hypothesis_types
    assert HypothesisType.TECH_FOLLOWUP in hypothesis_types


@pytest.mark.asyncio
async def test_analyst_derives_waf_followup_directives():
    directives = []

    class DirectiveStore:
        scan_id = uuid4()

        async def add_directive(self, session, **kwargs):
            directives.append(kwargs)

    analyst = AnalystAgent(store=DirectiveStore())
    work_unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://app.example.com",
        command_template="httpx ...",
        status=WorkUnitStatus.COMPLETED,
    )

    await analyst._derive_waf_followup_directives(
        object(),
        "Cloudflare bot management is blocking standard CLI probes. A browser-like approach is needed.",
        [work_unit],
    )

    directive_types = {entry["directive_type"] for entry in directives}
    techniques = {entry["content"]["technique"] for entry in directives}

    assert DirectiveType.ATTACK_HINT in directive_types
    assert "waf_detection_followup" in techniques
    assert "browser_like_probe_followup" in techniques


@pytest.mark.asyncio
async def test_planner_supports_deprecated_raw_command_attack_hints(monkeypatch):
    store = RecordingStore()
    planner = PlannerAgent(store=store, target="https://example.com")

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._process_attack_hint(
        {
            "technique": "legacy_raw_hint",
            "targets": ["https://example.com"],
            "context": "compatibility",
            "command": "echo test {target}",
        }
    )

    assert store.enqueued[0]["technique"] == "hint_legacy_raw_hint"
    assert store.enqueued[0]["command_template"] == "echo test https://example.com"


@pytest.mark.asyncio
async def test_analyst_strips_ansi_sequences_from_discovered_urls():
    calls = {"observations": []}

    class StructuredStore:
        scan_id = uuid4()

        async def add_observation(self, session, **kwargs):
            calls["observations"].append(kwargs)

        async def add_capability(self, session, **kwargs):
            return None

        async def add_hypothesis(self, session, **kwargs):
            return None

        async def add_directive(self, session, **kwargs):
            return None

    analyst = AnalystAgent(store=StructuredStore())
    parsed = AnalystResponse(analysis="ansi-safe")
    work_unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://priceguru.mu",
        command_template="httpx ...",
        status=WorkUnitStatus.COMPLETED,
        result_stdout="https://priceguru.mu\x1b[0m/login [403]",
        result_stderr="",
    )

    await analyst._persist_structured_state(object(), parsed, [work_unit])

    live_http_targets = {
        call["target"]
        for call in calls["observations"]
        if call["observation_type"] == ObservationType.LIVE_HTTP
    }

    assert "https://priceguru.mu/login" in live_http_targets
    assert all("\x1b" not in target for target in live_http_targets)


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


def test_planner_maps_hidden_host_and_legacy_stack_hypotheses_to_work():
    planner = PlannerAgent(store=RecordingStore(), target="https://example.com")

    hidden = Hypothesis(
        scan_id=uuid4(),
        project_id=uuid4(),
        type=HypothesisType.HIDDEN_HOST_FOLLOWUP,
        target="adminmeteo.intnet.mu",
        key="tls-hidden",
        rationale="TLS SAN revealed hidden host",
        confidence=0.9,
        status=HypothesisStatus.PENDING,
    )
    legacy = Hypothesis(
        scan_id=uuid4(),
        project_id=uuid4(),
        type=HypothesisType.LEGACY_STACK_RCE_FOLLOWUP,
        target="https://metservice.intnet.mu",
        key="legacy-stack",
        rationale="Legacy stack indicators present",
        confidence=0.9,
        status=HypothesisStatus.PENDING,
    )

    hidden_work = planner._work_item_for_hypothesis(hidden)
    legacy_work = planner._work_item_for_hypothesis(legacy)

    assert hidden_work["technique"] == "hypothesis_hidden_host_followup"
    assert "nmap -sV -sC" in hidden_work["command"]
    assert legacy_work["technique"] == "hypothesis_legacy_stack_rce_followup"
    assert "nuclei -u https://metservice.intnet.mu" in legacy_work["command"]


@pytest.mark.asyncio
async def test_planner_expands_attack_hint_aliases_into_real_work(monkeypatch):
    store = RecordingStore()
    planner = PlannerAgent(store=store, target="metservice.intnet.mu")
    planner._remember_live_http_target("https://metservice.intnet.mu")

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.planner.get_session", fake_get_session)

    await planner._process_attack_hint(
        {
            "technique": "vulnerability_scanning",
            "targets": ["https://metservice.intnet.mu"],
            "context": "Legacy Apache/PHP stack detected",
        }
    )

    techniques = {call["technique"] for call in store.enqueued}
    commands = {call["command_template"] for call in store.enqueued}

    assert "hint_nuclei_cves" in techniques
    assert "hint_nikto" in techniques
    assert any(command.startswith("nuclei -u https://metservice.intnet.mu") for command in commands)
    assert any(command.startswith("nikto -h https://metservice.intnet.mu") for command in commands)


def test_planner_normalizes_nmap_targets_to_hostnames():
    store = RecordingStore()
    planner = PlannerAgent(store=store, target="https://example.com")
    rule = SimpleNamespace(
        command_template="nmap -sV -sC -T3 -p 80,443 {target}",
        technique="nmap_initial",
    )

    normalized = planner._normalize_target_for_rule(rule, "https://example.com", "example.com")

    assert normalized == "example.com"


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


@pytest.mark.asyncio
async def test_shared_store_emits_scan_events_for_work_unit_lifecycle():
    scan_id = uuid4()
    project_id = uuid4()
    store = SharedScanStore(project_id=project_id, scan_id=scan_id)
    emitted = []

    async def fake_append_event(session, **kwargs):
        emitted.append(kwargs)
        return object()

    store.append_event = fake_append_event

    unit = make_workunit(
        id=uuid4(),
        scan_id=scan_id,
        project_id=project_id,
        technique="httpx_primary",
        target="https://app.example.com",
        scope_key="scope-app",
        command_template="httpx -u https://app.example.com",
        status=WorkUnitStatus.PENDING,
    )

    class FakeClaimResult:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.refreshed = False

        def add(self, obj):
            return None

        async def commit(self):
            self.commits += 1

        async def refresh(self, obj):
            return None

        async def rollback(self):
            return None

        async def execute(self, statement):
            text = str(statement)
            if "FROM workunit" in text and "status IN" in text:
                return _FakeResult([])
            if "FROM workunit" in text and "status =" in text and "LIMIT" in text:
                return _FakeResult([unit])
            if text.startswith("UPDATE workunit"):
                return FakeClaimResult(1)
            if "WHERE workunit.id =" in text:
                self.refreshed = True
                return _FakeResult([unit])
            raise AssertionError(f"Unexpected statement: {text}")

    enqueue_session = FakeSession()
    await store.enqueue_work_unit(
        enqueue_session,
        technique="httpx_primary",
        targets=["https://app.example.com"],
        command_template="httpx -u https://app.example.com",
    )

    claim_session = FakeSession()
    claimed = await store.claim_work_unit(claim_session, "worker-7")
    assert claimed is unit

    complete_session = FakeSession()
    await store.complete_work_unit(
        complete_session,
        unit.id,
        stdout="ok",
        exit_code=0,
        status=WorkUnitStatus.COMPLETED,
    )

    event_types = [event["event_type"] for event in emitted]
    assert ScanEventType.WORK_UNIT_QUEUED in event_types
    assert ScanEventType.WORK_UNIT_CLAIMED in event_types
    assert ScanEventType.WORK_UNIT_COMPLETED in event_types


@pytest.mark.asyncio
async def test_shared_store_builds_projection_from_events_and_runtime_state():
    store = SharedScanStore(project_id=uuid4(), scan_id=uuid4())

    async def fake_get_findings(session, limit=100):
        return [SimpleNamespace(title="SQL Injection", severity="high", target="https://app.example.com")]

    async def fake_get_observations(session, limit=200):
        return [SimpleNamespace(type="live_http", target="https://app.example.com", key="https://app.example.com")]

    async def fake_get_capabilities(session, limit=100):
        return [SimpleNamespace(type="auth_surface", target="https://app.example.com/login", key="login")]

    async def fake_get_hypotheses(session, limit=100):
        return [SimpleNamespace(type="auth_followup", target="https://app.example.com/login", status="pending", confidence=0.8)]

    async def fake_get_events(session, limit=25):
        return [
            SimpleNamespace(type="component_degraded", entity_type="component", entity_id="planner", payload={"component": "planner", "reason": "cycle failed"}),
            SimpleNamespace(type="work_unit_completed", entity_type="work_unit", entity_id="abc", payload={"technique": "httpx_primary"}),
        ]

    async def fake_get_notes(session, limit=50):
        return [SimpleNamespace(id=uuid4(), category="attack_hint", target="https://app.example.com", content="Try auth reuse")]

    async def fake_get_attempts(session, limit=100):
        return [SimpleNamespace(id=uuid4(), tool="nuclei", target="https://app.example.com", status="success", reason="baseline")]

    async def fake_get_nodes(session, limit=100):
        return [SimpleNamespace(id=uuid4(), name="https://app.example.com", type="url", label="Endpoint", properties={}, scanned=True)]

    store.get_findings = fake_get_findings
    store.get_observations = fake_get_observations
    store.get_capabilities = fake_get_capabilities
    store.get_hypotheses = fake_get_hypotheses
    store.get_notes = fake_get_notes
    store.get_attempts = fake_get_attempts
    store._get_nodes = fake_get_nodes
    store.get_events = fake_get_events

    class FakeSession:
        async def execute(self, statement):
            return _FakeResult([
                (WorkUnitStatus.PENDING, 2),
                (WorkUnitStatus.COMPLETED, 5),
            ])

    projection = await store.build_projection(FakeSession())

    assert projection["work_queue"]["pending"] == 2
    assert projection["work_queue"]["completed"] == 5
    assert projection["assets"][0]["target"] == "https://app.example.com"
    assert projection["degraded_components"][0]["component"] == "planner"
    assert projection["findings"][0]["title"] == "SQL Injection"
    assert projection["node_count"] == 1
    assert projection["nodes"][0]["type"] == "url"
    assert projection["attempts"][0]["tool"] == "nuclei"
    assert projection["notes"][0]["content"] == "Try auth reuse"
    assert projection["capabilities"][0]["type"] == "auth_surface"
    assert projection["hypotheses"][0]["status"] == "pending"
    assert projection["recent_events"][0]["type"] == "component_degraded"


@pytest.mark.asyncio
async def test_event_manager_attaches_scan_id_to_emitted_event():
    manager = TUIEventManager()
    seen = []

    def capture(event):
        seen.append(event)

    manager.subscribe("tool_start", capture)

    event = TUIEvent("tool_start", {"tool_name": "nmap"})
    await manager.emit(event, scan_id="scan-123")

    assert seen[0].project_id == "scan-123"


def test_scan_state_applies_projection_payload():
    scan = ScanState(
        id="scan-1",
        project_id="project-1",
        name="Test Scan",
        target="https://example.com",
        status=ScanStatus.RUNNING,
        agent_count=1,
        created_at=datetime.now(),
        agents={"agent-1": AgentState(id="agent-1", name="Agent 1")},
    )

    projection = {
        "work_queue": {"pending": 2, "completed": 5},
        "assets": [{"target": "https://example.com", "host": "example.com", "observation_types": ["live_http"], "capability_types": []}],
        "degraded_components": [{"component": "planner", "status": "warning"}],
        "node_count": 1,
        "nodes": [
            {"id": str(uuid4()), "name": "https://example.com", "type": "url", "label": "Endpoint", "properties": {}, "scanned": True},
        ],
        "findings": [
            {"title": "SQL Injection", "severity": "high", "target": "https://example.com"},
        ],
        "attempts": [{"id": str(uuid4()), "tool": "nuclei", "target": "https://example.com", "status": "success", "reason": "baseline"}],
        "notes": [{"id": str(uuid4()), "category": "attack_hint", "target": "https://example.com", "content": "Try auth reuse"}],
        "capabilities": [{"type": "auth_surface", "target": "https://example.com/login", "key": "login"}],
        "hypotheses": [{"type": "auth_followup", "target": "https://example.com/login", "status": "pending", "confidence": 0.8}],
        "recent_events": [{"type": "work_unit_completed", "payload": {"technique": "httpx_primary"}}],
    }

    scan.apply_projection(projection)

    assert scan.work_queue["pending"] == 2
    assert scan.assets[0]["host"] == "example.com"
    assert scan.degraded_components[0]["component"] == "planner"
    assert scan.node_count == 1
    assert scan.nodes[0].type == "url"
    assert scan.findings[0].title == "SQL Injection"
    assert scan.attempts[0]["tool"] == "nuclei"
    assert scan.engagement_notes[0]["category"] == "attack_hint"
    assert scan.capabilities[0]["type"] == "auth_surface"
    assert scan.hypotheses[0]["status"] == "pending"
    assert scan.recent_events[0]["type"] == "work_unit_completed"


def test_app_state_add_scan_prefers_worker_count_from_scan_config():
    state = AppState()
    project_id = uuid4()
    state.add_project(
        SimpleNamespace(
            id=project_id,
            name="Demo",
            description="",
            created_at=datetime.now(),
        )
    )
    scan = ScanJob(
        id=uuid4(),
        project_id=project_id,
        name="Projection-backed scan",
        status=DBScanStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        config={
            "target": "https://app.example.com",
            "worker_count": 4,
            "agent_count": 3,
        },
    )

    state.add_scan(scan)

    added = state.get_scan(str(scan.id))
    assert added is not None
    assert added.target == "https://app.example.com"
    assert added.agent_count == 4
    assert state.get_project(str(project_id)).target == "https://app.example.com"


@pytest.mark.asyncio
async def test_core_interface_returns_scan_projection_by_scan_id(monkeypatch):
    interface = CoreInterface()
    scan_id = str(uuid4())

    fake_scan = SimpleNamespace(id=uuid4(), project_id=uuid4())
    expected_projection = {"scan_id": scan_id, "work_queue": {"pending": 1}}

    async def fake_get(scan_session, lookup_scan_id):
        assert str(lookup_scan_id) == scan_id
        return fake_scan

    class FakeStore:
        def __init__(self, project_id, scan_id):
            self.project_id = project_id
            self.scan_id = scan_id

        async def build_projection(self, session):
            return expected_projection

    async def fake_get_session():
        yield object()

    monkeypatch.setattr("kodiak.core.interface.get_session", fake_get_session)
    monkeypatch.setattr("kodiak.core.interface.crud_scan.get", fake_get)
    monkeypatch.setattr("kodiak.core.interface.SharedScanStore", FakeStore)

    projection = await interface.get_scan_projection(scan_id)

    assert projection == expected_projection


def test_tool_name_for_unit_prefers_last_piped_command():
    unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://example.com",
        command_template="echo 'https://example.com' | httpx -sc -title -tech-detect -silent",
        status=WorkUnitStatus.PENDING,
    )

    assert _tool_name_for_unit(unit) == "httpx"


def test_unit_primary_target_prefers_single_scope_field():
    unit = make_workunit(
        scan_id=uuid4(),
        project_id=uuid4(),
        technique="httpx_primary",
        target="https://single.example.com",
        target_kind="origin",
        tool_family="httpx",
        scope_key="https://single.example.com",
        command_template="echo 'https://single.example.com' | httpx -sc -title -tech-detect -silent",
        status=WorkUnitStatus.PENDING,
    )

    assert _unit_primary_target(unit) == "https://single.example.com"
