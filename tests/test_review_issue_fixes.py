from types import SimpleNamespace
from uuid import uuid4

import pytest

from kodiak.core.kernel_result import KernelResult
from kodiak.core.tool_availability import ToolAvailability, get_default_tools_to_check
from kodiak.database.engine import _validate_sqlite_schema
from kodiak.services.base import LLMConfig
from kodiak.services.litellm_client import LiteLLMClient


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
            return {"asset_count": 9, "work_queue": {"pending": 2, "completed": 4}}

    class FakeOrchestrator:
        def __init__(self, event_manager, num_workers, max_scan_duration):
            self.event_manager = event_manager
            self.num_workers = num_workers
            self.max_scan_duration = max_scan_duration

        async def run(self, **_kwargs):
            availability = _kwargs["tool_availability"]
            assert availability.is_checked()
            assert availability.is_unavailable("nikto")
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
        return ["httpx"], ["nikto"]

    async def fake_preflight_dns(self):
        return None

    async def fake_update_status(session, scan_id, status):
        return None

    async def fake_get_nodes(session, project_id):
        return [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    async def fake_get_attempts(session, scan_id, limit=400):
        return []

    captured_report = {}

    def fake_write_scan_report(**kwargs):
        captured_report.update(kwargs["report_data"])
        return {}

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
    monkeypatch.setattr(runtime, "write_scan_report", fake_write_scan_report)

    runner = runtime.ScanRunner(event_manager=FakeEventManager())
    result = await runner.run(target="https://example.com")
    assert result.status == "completed"
    assert result.asset_count == 9
    assert captured_report["summary"]["work_pending"] == 2
    assert captured_report["summary"]["work_completed"] == 4
    assert captured_report["summary"]["unavailable_tools"] == {"nikto": "not found in Docker container"}


def test_kernel_result_exposes_extended_token_accounting_defaults():
    result = KernelResult(status="completed", summary="ok", findings_count=0, iterations=1)

    assert result.total_thinking_tokens == 0
    assert result.total_cached_tokens == 0


def test_cli_exposes_documented_setup_commands():
    from kodiak.cli import main

    assert "config" in main.commands
    assert "init" in main.commands


def test_migrate_without_reset_returns_guidance():
    from click.testing import CliRunner

    from kodiak.cli import main

    result = CliRunner().invoke(main, ["migrate"])

    assert result.exit_code == 0
    assert "kodiak migrate --reset" in result.output


def test_config_wizard_database_and_success_screens_are_separate():
    from kodiak.tui.config_wizard import DatabaseScreen, SuccessScreen

    assert "_do_initialize" not in DatabaseScreen.__dict__
    assert "_do_initialize" in SuccessScreen.__dict__
    assert DatabaseScreen.compose is not SuccessScreen.compose


@pytest.mark.asyncio
async def test_core_interface_stop_scan_calls_runner_cancel_before_task_cancel(monkeypatch):
    from kodiak.core.interface import CoreInterface, _RunState

    called = {"cancel": 0}

    async def fake_cancel():
        called["cancel"] += 1

    async def sleeper():
        await asyncio.sleep(10)

    import asyncio

    interface = CoreInterface()
    monkeypatch.setattr(interface._runner, "cancel", fake_cancel)
    task = asyncio.create_task(sleeper())
    state = _RunState(
        run_id="run-1",
        target="https://example.com",
        instructions="",
        model=None,
        worker_count=None,
        report_format="json+md",
        report_path=None,
        task=task,
    )
    interface._runs["run-1"] = state

    stopped = await interface.stop_scan("run-1")

    assert stopped is True
    assert called["cancel"] == 1
    assert task.cancelled() is True


@pytest.mark.asyncio
async def test_litellm_client_awaits_async_completion():
    class FakeLiteLLM:
        def __init__(self):
            self.kwargs = None

        async def acompletion(self, **kwargs):
            self.kwargs = kwargs
            assert kwargs["model"] == "test/model"
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="analysis complete", tool_calls=[]),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
                _response_cost=0.001,
            )

    client = LiteLLMClient.__new__(LiteLLMClient)
    client.config = LLMConfig(api_key="test-key", base_url="https://openrouter.ai/api/v1")
    fake_litellm = FakeLiteLLM()
    client._litellm = fake_litellm

    response = await client.generate(
        model="test/model",
        system_prompt="system",
        messages=[{"role": "user", "content": "analyze"}],
    )

    assert response.content == "analysis complete"
    assert response.finish_reason == "stop"
    assert response.input_tokens == 3
    assert response.output_tokens == 4
    assert fake_litellm.kwargs["extra_headers"] == {
        "HTTP-Referer": "https://kodiak.security",
        "X-Title": "Kodiak Security Scanner",
    }


def test_worker_docker_network_args_require_explicit_mode():
    from kodiak.core.worker import _docker_network_args

    assert _docker_network_args(None) == []
    assert _docker_network_args("") == []
    assert _docker_network_args("host") == ["--network", "host"]
    assert _docker_network_args("bridge") == ["--network", "bridge"]
    assert _docker_network_args("invalid mode") == []
