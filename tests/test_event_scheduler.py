import asyncio

import pytest

from kodiak.api.events import TUIEventManager
from kodiak.core.manager import ManagerAgent
from kodiak.core.response_schema import Action, ActionType, KodiakResponse, PhaseAction
from kodiak.core.scan_state import ScanState
from kodiak.core.scheduler import EventDrivenScheduler
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.worker import CommandResult, CommandTask


@pytest.mark.asyncio
async def test_scheduler_emits_queued_started_completed(monkeypatch):
    async def fake_execute(task, semaphore):
        return CommandResult(
            task_id=task.task_id,
            command=task.command,
            rationale=task.rationale,
            stdout="ok",
            stderr="",
            exit_code=0,
            duration_seconds=0.01,
        )

    monkeypatch.setattr("kodiak.core.scheduler.execute_command", fake_execute)

    scheduler = EventDrivenScheduler(global_concurrency=1)
    task = CommandTask(command="echo test", rationale="test lifecycle", task_id="task_life")

    submitted = await scheduler.submit(task)
    assert submitted

    events = []
    for _ in range(3):
        event = await scheduler.next_event(timeout_seconds=1)
        assert event is not None
        events.append(event.event_type)

    assert events[0] == "task_queued"
    assert "task_started" in events
    assert "task_completed" in events


@pytest.mark.asyncio
async def test_scheduler_cancel_produces_cancel_event(monkeypatch):
    async def fake_execute(task, semaphore):
        await asyncio.sleep(0.5)
        return CommandResult(
            task_id=task.task_id,
            command=task.command,
            rationale=task.rationale,
            stdout="late",
            stderr="",
            exit_code=0,
            duration_seconds=0.5,
        )

    monkeypatch.setattr("kodiak.core.scheduler.execute_command", fake_execute)

    scheduler = EventDrivenScheduler(global_concurrency=1)
    task = CommandTask(command="sleep 10", rationale="cancel me", task_id="task_cancel")
    await scheduler.submit(task)

    # Drain queue/start events first.
    for _ in range(2):
        _ = await scheduler.next_event(timeout_seconds=1)

    cancelled = await scheduler.cancel("task_cancel")
    assert cancelled

    event = await scheduler.next_event(timeout_seconds=1)
    assert event is not None
    assert event.event_type == "task_cancelled"
    assert event.task_id == "task_cancel"


def test_manager_extract_runtime_actions_supports_actions_and_filters_tools():
    inv = ToolInventory()
    inv.initialize_tools()
    manager = ManagerAgent(event_manager=TUIEventManager(), tool_inventory=inv)
    manager.scan_state = ScanState(target="example.com")

    resp = KodiakResponse(
        analysis="action test",
        actions=[
            Action(type=ActionType.LAUNCH, command="nmap -sV example.com", rationale="scan"),
            Action(type=ActionType.CANCEL, task_id="abc123", reason="low signal"),
            Action(type=ActionType.COMPLETE, reason="done"),
        ],
        commands=[],
        phase_action=PhaseAction.CONTINUE,
    )

    write_tasks, tasks, cancel_ids, phase_action = manager._extract_runtime_actions(
        kodiak_resp=resp,
        allowed_tools=["nmap"],
    )

    assert write_tasks == []
    assert len(tasks) == 1
    assert tasks[0].command.startswith("nmap")
    assert cancel_ids == ["abc123"]
    assert phase_action == PhaseAction.COMPLETE
