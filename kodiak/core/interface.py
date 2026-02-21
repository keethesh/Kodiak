import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional

from loguru import logger

from kodiak.api.events import TUIEvent, TUIEventManager, event_manager as default_event_manager
from kodiak.core.interface_events import CoreEvent, map_tui_event_payload
from kodiak.core.scan_runner import ScanRunner, ScanResult
from kodiak.core.config import settings


TERMINAL_EVENTS = {"scan_completed", "scan_failed"}


@dataclass
class _RunState:
    run_id: str
    target: str
    instructions: str
    max_iterations: int
    model: Optional[str]
    agent_count: int
    role_strategy: str
    force_agents: bool
    queue: asyncio.Queue[CoreEvent] = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None
    result: Optional[ScanResult] = None
    error: Optional[str] = None
    scan_id: Optional[str] = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class CoreInterface:
    """
    Frontend-agnostic interface for scan orchestration and runtime events.
    """

    def __init__(self, event_manager: Optional[TUIEventManager] = None):
        self._event_manager = event_manager or default_event_manager
        self._runner = ScanRunner(self._event_manager)
        self._runs: Dict[str, _RunState] = {}
        self._scan_to_run: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._subscribed = False
        self._event_types = [
            "scan_started",
            "scan_completed",
            "scan_failed",
            "tool_start",
            "tool_complete",
            "finding_discovered",
            "agent_thinking",
            "agent_thought",
        ]

    async def start_scan(
        self,
        target: str,
        instructions: str = "Conduct a security assessment",
        model: Optional[str] = None,
        max_iterations: int = 100,
        agent_count: Optional[int] = None,
        role_strategy: str = "role_hinted",
        force_agents: bool = False,
    ) -> str:
        await self._ensure_subscriptions()

        requested_agents = agent_count or settings.default_agent_count

        run_id = str(uuid.uuid4())
        state = _RunState(
            run_id=run_id,
            target=target,
            instructions=instructions,
            max_iterations=max_iterations,
            model=model,
            agent_count=requested_agents,
            role_strategy=role_strategy,
            force_agents=force_agents,
        )

        async with self._lock:
            self._runs[run_id] = state

        state.task = asyncio.create_task(self._run_scan(state), name=f"kodiak-run-{run_id}")
        return run_id

    async def subscribe_events(self, run_id: str) -> AsyncIterator[CoreEvent]:
        state = self._runs.get(run_id)
        if not state:
            raise ValueError(f"Unknown run_id: {run_id}")

        while True:
            if state.done.is_set() and state.queue.empty():
                break
            try:
                event = await asyncio.wait_for(state.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            yield event
            if event.type in TERMINAL_EVENTS:
                break

    async def get_scan_result(self, run_id: str) -> Optional[ScanResult]:
        state = self._runs.get(run_id)
        if not state:
            return None
        await state.done.wait()
        return state.result

    async def get_scan_status(self, run_id: str) -> Dict[str, Any]:
        state = self._runs.get(run_id)
        if not state:
            return {"status": "unknown", "run_id": run_id}
        if state.done.is_set():
            return {
                "status": "completed" if state.error is None else "failed",
                "run_id": run_id,
                "scan_id": state.scan_id,
                "error": state.error,
            }
        return {"status": "running", "run_id": run_id, "scan_id": state.scan_id}

    async def stop_scan(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if not state or not state.task:
            return False
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass
        return True

    async def _run_scan(self, state: _RunState) -> None:
        try:
            from kodiak.core.config import settings

            original_model = settings.llm_model
            if state.model:
                settings.llm_model = state.model
            try:
                result = await self._runner.run(
                    target=state.target,
                    instructions=state.instructions,
                    max_iterations=state.max_iterations,
                    agent_count=state.agent_count,
                    role_strategy=state.role_strategy,
                    force_agents=state.force_agents,
                )
                state.result = result
            finally:
                settings.llm_model = original_model
        except asyncio.CancelledError:
            state.error = "Scan cancelled"
            await self._push_event(state.run_id, "scan_failed", {"error": state.error, "status": "failed"})
            raise
        except Exception as e:
            state.error = str(e)
            logger.error(f"CoreInterface scan run failed ({state.run_id}): {e}")
            await self._push_event(state.run_id, "scan_failed", {"error": state.error, "status": "failed"})
        finally:
            state.done.set()

    async def _ensure_subscriptions(self) -> None:
        async with self._lock:
            if self._subscribed:
                return
            for event_type in self._event_types:
                self._event_manager.subscribe(event_type, self._on_tui_event)
            self._subscribed = True

    async def _on_tui_event(self, event: TUIEvent) -> None:
        run_id = await self._resolve_run_id(event)
        if not run_id:
            return

        payload = map_tui_event_payload(event.type, event.data or {})
        scan_id = event.project_id or payload.get("scan_id")
        core_event = CoreEvent(
            type=event.type,
            run_id=run_id,
            payload=payload,
            scan_id=scan_id,
            timestamp=event.timestamp,
        )
        await self._push_core_event(run_id, core_event)

    async def _resolve_run_id(self, event: TUIEvent) -> Optional[str]:
        # Strongest signal: explicit scan_id attached to event emission.
        if event.project_id and event.project_id in self._scan_to_run:
            return self._scan_to_run[event.project_id]

        # Bind pending run on scan_started by target.
        if event.type == "scan_started":
            scan_id = (event.data or {}).get("scan_id")
            target = (event.data or {}).get("target")
            if scan_id and target:
                async with self._lock:
                    for run_id, state in self._runs.items():
                        if state.scan_id is None and state.target == target and not state.done.is_set():
                            state.scan_id = scan_id
                            self._scan_to_run[scan_id] = run_id
                            return run_id

        # Fallback for single active run.
        active = [r for r in self._runs.values() if not r.done.is_set()]
        if len(active) == 1:
            return active[0].run_id

        return None

    async def _push_event(self, run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        core_event = CoreEvent(type=event_type, run_id=run_id, payload=payload)
        await self._push_core_event(run_id, core_event)

    async def _push_core_event(self, run_id: str, event: CoreEvent) -> None:
        state = self._runs.get(run_id)
        if not state:
            return
        await state.queue.put(event)
