import asyncio
from types import SimpleNamespace

import pytest

from kodiak.api.events import TUIEventManager
from kodiak.core.agent_scaling import resolve_agent_count
from kodiak.core.scan_runner import ScanRunner


class TestAgentScaling:
    def test_resolve_agent_count_within_limit(self):
        resolved = resolve_agent_count(requested=3, max_agents=5, force_agents=False)
        assert resolved.requested == 3
        assert resolved.effective == 3
        assert resolved.clamped is False
        assert resolved.warning is None

    def test_resolve_agent_count_clamped_without_force(self):
        resolved = resolve_agent_count(requested=9, max_agents=4, force_agents=False)
        assert resolved.requested == 9
        assert resolved.effective == 4
        assert resolved.clamped is True
        assert "Clamping to 4" in (resolved.warning or "")

    def test_resolve_agent_count_force_override(self):
        resolved = resolve_agent_count(requested=9, max_agents=4, force_agents=True)
        assert resolved.requested == 9
        assert resolved.effective == 9
        assert resolved.clamped is False
        assert "force_agents" in (resolved.warning or "")


class TestScanRunnerHelpers:
    def _runner(self) -> ScanRunner:
        return ScanRunner(TUIEventManager())

    def test_role_strategy_role_hinted_cycles(self):
        runner = self._runner()
        assert runner._role_for_index(0, "role_hinted") == "scout"
        assert runner._role_for_index(1, "role_hinted") == "mapper"
        assert runner._role_for_index(5, "role_hinted") == "scout"

    def test_role_strategy_generic(self):
        runner = self._runner()
        assert runner._role_for_index(0, "generic") == "generalist"

    def test_build_agent_goal_includes_role_hint(self):
        runner = self._runner()
        goal = runner._build_agent_goal(
            base_instructions="Conduct a security assessment",
            target="https://example.com",
            role="scout",
            index=0,
            total=3,
            role_strategy="role_hinted",
        )
        assert "Role: scout" in goal
        assert "agent 1 of 3" in goal

    def test_aggregate_prefers_deduped_finding_count(self):
        runner = self._runner()
        raw_results = [
            SimpleNamespace(status="completed", summary="a", findings_count=7, iterations=10),
            SimpleNamespace(status="completed", summary="b", findings_count=4, iterations=9),
        ]
        result = runner._aggregate_agent_results(raw_results, max_iterations=20, deduped_finding_count=5)
        assert result.status == "completed"
        assert result.findings_count == 5
        assert result.iterations == 19

    def test_aggregate_max_iterations(self):
        runner = self._runner()
        raw_results = [
            SimpleNamespace(status="max_iterations", summary="m1", findings_count=1, iterations=10),
            SimpleNamespace(status="max_iterations", summary="m2", findings_count=2, iterations=10),
        ]
        result = runner._aggregate_agent_results(raw_results, max_iterations=20, deduped_finding_count=0)
        assert result.status == "max_iterations"
        assert result.findings_count == 3

    @pytest.mark.asyncio
    async def test_cancel_cancels_all_agent_tasks(self):
        runner = self._runner()
        task_one = asyncio.create_task(asyncio.sleep(30))
        task_two = asyncio.create_task(asyncio.sleep(30))
        runner._agent_tasks = [task_one, task_two]

        await runner.cancel()

        assert all(task.done() for task in runner._agent_tasks)
        assert all(task.cancelled() for task in runner._agent_tasks)
