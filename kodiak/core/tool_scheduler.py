"""
Simple per-tool queue scheduler for scan-time tool execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from loguru import logger


@dataclass
class _ScheduledWork:
    future: asyncio.Future
    coro_factory: Callable[[], Awaitable[Any]]


@dataclass
class ScheduledExecutionResult:
    result: Any
    coalesced: bool = False


class ToolScheduler:
    """
    Queue-based scheduler with per-tool worker pools.
    Tools not explicitly registered bypass the scheduler.
    """

    def __init__(self, queue_limit: int = 50):
        self._queue_limit = max(1, queue_limit)
        self._queues: Dict[str, asyncio.Queue] = {}
        self._workers: Dict[str, list[asyncio.Task]] = {}
        self._running = False
        self._inflight: Dict[Tuple[str, str], asyncio.Future] = {}
        self._inflight_lock = asyncio.Lock()

    def register_tool(self, tool_name: str, concurrency: int) -> None:
        if tool_name in self._queues:
            return
        self._queues[tool_name] = asyncio.Queue(maxsize=self._queue_limit)
        self._workers[tool_name] = []
        worker_count = max(1, concurrency)
        self._workers[tool_name] = [None] * worker_count

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for tool_name, slots in self._workers.items():
            for index in range(len(slots)):
                task = asyncio.create_task(
                    self._worker_loop(tool_name),
                    name=f"kodiak-tool-worker-{tool_name}-{index + 1}",
                )
                slots[index] = task

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        for queue in self._queues.values():
            # One sentinel per worker.
            workers_for_queue = 1
            for name, q in self._queues.items():
                if q is queue:
                    workers_for_queue = max(1, len(self._workers.get(name, [])))
                    break
            for _ in range(workers_for_queue):
                await queue.put(None)

        all_tasks = []
        for tasks in self._workers.values():
            all_tasks.extend([t for t in tasks if t is not None])
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)

    async def execute(
        self,
        tool_name: str,
        coro_factory: Callable[[], Awaitable[Any]],
        dedupe_key: Optional[str] = None,
    ) -> ScheduledExecutionResult:
        queue = self._queues.get(tool_name)
        loop = asyncio.get_running_loop()
        inflight_key = (tool_name, dedupe_key) if dedupe_key else None
        future: asyncio.Future

        existing_future: Optional[asyncio.Future] = None
        if inflight_key:
            async with self._inflight_lock:
                maybe = self._inflight.get(inflight_key)
                if maybe is not None and not maybe.done():
                    existing_future = maybe
                else:
                    future = loop.create_future()
                    self._inflight[inflight_key] = future
                    future.add_done_callback(
                        lambda _: self._clear_inflight_if_matches(inflight_key, future)
                    )
                    existing_future = None
        if existing_future is not None:
            logger.debug(f"ToolScheduler coalesced duplicate {tool_name} call for key={dedupe_key}")
            return ScheduledExecutionResult(result=await existing_future, coalesced=True)

        if not inflight_key:
            future = loop.create_future()

        if queue is None:
            try:
                result = await coro_factory()
                if not future.done():
                    future.set_result(result)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)
            return ScheduledExecutionResult(result=await future, coalesced=False)

        work = _ScheduledWork(future=future, coro_factory=coro_factory)

        try:
            queue.put_nowait(work)
        except asyncio.QueueFull as e:
            if inflight_key is not None:
                self._clear_inflight_if_matches(inflight_key, future)
            raise RuntimeError(
                f"Tool queue full for {tool_name} (limit={self._queue_limit})."
            ) from e

        return ScheduledExecutionResult(result=await future, coalesced=False)

    def _clear_inflight_if_matches(self, key: Tuple[str, str], future: asyncio.Future) -> None:
        current = self._inflight.get(key)
        if current is future:
            self._inflight.pop(key, None)

    async def _worker_loop(self, tool_name: str) -> None:
        queue = self._queues[tool_name]
        while True:
            item: Optional[_ScheduledWork] = await queue.get()
            if item is None:
                queue.task_done()
                return

            try:
                result = await item.coro_factory()
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as e:
                logger.debug(f"ToolScheduler worker error for {tool_name}: {e}")
                if not item.future.done():
                    item.future.set_exception(e)
            finally:
                queue.task_done()
