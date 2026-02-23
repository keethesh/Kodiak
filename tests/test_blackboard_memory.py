from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from kodiak.core.blackboard import BlackboardService
from kodiak.core.blackboard_schema import role_scoped_entity_types
from kodiak.core.agent import KodiakAgent


def test_role_scope_exposes_task_memory_for_primary_roles():
    for role in ("scout", "mapper", "attacker", "verifier"):
        assert "task" in role_scoped_entity_types(role)


def test_blackboard_derives_tool_execution_event_with_strategy():
    service = BlackboardService()
    events = service._derive_events_for_tool(
        tool_name="whatweb",
        target="https://example.com",
        args={"target": "https://example.com", "aggression": 1},
        result={
            "success": True,
            "output": "whatweb ok",
            "data": {
                "results": [
                    {
                        "target": "https://example.com",
                        "technologies": [{"name": "PrestaShop", "version": "8.1"}],
                    }
                ]
            },
        },
        fingerprint="fp-whatweb",
        execution_context={
            "status": "success",
            "strategy": "fingerprint stack first",
            "outcome": "executed_success",
            "next_step": "run focused nuclei templates",
        },
    )

    tool_exec = [event for event in events if event["event_type"] == "tool_execution"]
    assert len(tool_exec) == 1
    payload = tool_exec[0]["payload"]
    assert payload["tool"] == "whatweb"
    assert payload["strategy"] == "fingerprint stack first"
    assert payload["outcome"] == "executed_success"
    assert payload["next_step"] == "run focused nuclei templates"
    assert tool_exec[0]["status"] == "success"


def test_blackboard_failed_scan_emits_execution_event_only():
    service = BlackboardService()
    events = service._derive_events_for_tool(
        tool_name="nmap",
        target="example.com",
        args={"target": "example.com"},
        result={"success": False, "output": "", "error": "timed out", "data": {}},
        fingerprint="fp-nmap-timeout",
        execution_context={
            "status": "timeout",
            "strategy": "broad top ports",
            "outcome": "timeout",
            "next_step": "retry with lower intensity",
        },
    )

    assert any(event["event_type"] == "tool_execution" for event in events)
    assert not any(event["event_type"] == "host_discovered" for event in events)


@pytest.mark.asyncio
async def test_blackboard_prompt_context_includes_peer_execution_ledger(monkeypatch):
    service = BlackboardService()

    facts = [
        SimpleNamespace(
            entity_type="endpoint",
            entity_key="endpoint:https://example.com/admin",
            canonical={"url": "https://example.com/admin", "status_code": 200},
            confidence="high",
            verification_status="verified",
            updated_at=0,
        ),
        SimpleNamespace(
            entity_type="task",
            entity_key="task:nuclei:fp-1",
            canonical={
                "tool": "nuclei",
                "target": "https://example.com",
                "status": "failure",
                "strategy": "target prestashop CVEs first",
                "outcome": "target_blocked_or_rate_limited",
                "next_step": "reduce rate and retry focused templates",
            },
            confidence="medium",
            verification_status="unverified",
            updated_at=1,
        ),
    ]

    async def fake_list_facts(*args, **kwargs):
        return facts

    async def fake_list_edges(*args, **kwargs):
        return []

    async def fake_list_pending(*args, **kwargs):
        return []

    monkeypatch.setattr("kodiak.core.blackboard.crud.blackboard_fact.list_by_scan", fake_list_facts)
    monkeypatch.setattr("kodiak.core.blackboard.crud.blackboard_edge.list_by_scan", fake_list_edges)
    monkeypatch.setattr("kodiak.core.blackboard.crud.verification_queue.list_pending_by_scan", fake_list_pending)

    context = await service.build_prompt_context(
        session=object(),
        scan_id=uuid4(),
        role="attacker",
        target="example.com",
        limit=10,
    )

    assert "BLACKBOARD FACTS" in context
    assert "PEER STRATEGIES & EXECUTION OUTCOMES" in context
    assert "outcome=target_blocked_or_rate_limited" in context
    assert "why=target prestashop CVEs first" in context


@pytest.mark.asyncio
async def test_blackboard_prompt_context_respects_char_cap(monkeypatch):
    service = BlackboardService()
    long_obs = "x" * 2500
    facts = [
        SimpleNamespace(
            entity_type="endpoint",
            entity_key="endpoint:https://example.com/very/long",
            canonical={"url": "https://example.com/very/long", "title": long_obs},
            confidence="high",
            verification_status="verified",
            updated_at=1,
        ),
    ]

    async def fake_list_facts(*args, **kwargs):
        return facts

    async def fake_list_edges(*args, **kwargs):
        return []

    async def fake_list_pending(*args, **kwargs):
        return []

    monkeypatch.setattr("kodiak.core.blackboard.crud.blackboard_fact.list_by_scan", fake_list_facts)
    monkeypatch.setattr("kodiak.core.blackboard.crud.blackboard_edge.list_by_scan", fake_list_edges)
    monkeypatch.setattr("kodiak.core.blackboard.crud.verification_queue.list_pending_by_scan", fake_list_pending)

    context = await service.build_prompt_context(
        session=object(),
        scan_id=uuid4(),
        role="mapper",
        target="example.com",
        limit=10,
        max_chars=220,
    )

    assert len(context) <= 220
    assert context.endswith("...")


def test_blackboard_manual_payload_validation_requires_source():
    service = BlackboardService()
    with pytest.raises(ValueError):
        service._validate_manual_payload("endpoint", {"url": "https://example.com"})

    ok = service._validate_manual_payload(
        "endpoint",
        {"url": "https://example.com", "source_tool": "httpx"},
    )
    assert ok["source_tool"] == "httpx"


@pytest.mark.asyncio
async def test_agent_persists_blackboard_execution_context():
    inventory = SimpleNamespace(
        list_tools=lambda: {},
        get=lambda _name: None,
    )
    events = SimpleNamespace()
    events.emit_tool_start = AsyncMock()
    events.emit_tool_complete = AsyncMock()

    agent = KodiakAgent(
        agent_id="agent-test",
        tool_inventory=inventory,
        event_manager=events,
        role="attacker",
    )
    agent._blackboard_service.publish_tool_result = AsyncMock(return_value=[])

    await agent._persist_blackboard_tool_result(
        session=object(),
        project_id=uuid4(),
        scan_id=uuid4(),
        tool_name="sqlmap",
        target="https://example.com/news.php?id=1",
        fingerprint="fp-sqlmap-1",
        args={"url": "https://example.com/news.php?id=1"},
        result_dict={"success": False, "output": "blocked", "error": "403"},
        status="failure",
        outcome="target_blocked_or_rate_limited",
        next_step="lower level/risk and pivot",
        strategy="validate SQLi without full dump",
    )

    agent._blackboard_service.publish_tool_result.assert_awaited_once()
    kwargs = agent._blackboard_service.publish_tool_result.await_args.kwargs
    execution_context = kwargs["execution_context"]
    assert execution_context["status"] == "failure"
    assert execution_context["strategy"] == "validate SQLi without full dump"
    assert execution_context["outcome"] == "target_blocked_or_rate_limited"
