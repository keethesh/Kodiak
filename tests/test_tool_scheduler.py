import asyncio

import pytest

from kodiak.core.tool_scheduler import ToolScheduler


@pytest.mark.asyncio
async def test_tool_scheduler_executes_registered_tool():
    scheduler = ToolScheduler(queue_limit=10)
    scheduler.register_tool("nuclei", concurrency=1)
    await scheduler.start()

    try:
        result = await scheduler.execute("nuclei", lambda: _async_value("ok"))
        assert result == "ok"
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_tool_scheduler_bypasses_unregistered_tool():
    scheduler = ToolScheduler(queue_limit=10)
    await scheduler.start()
    try:
        result = await scheduler.execute("httpx", lambda: _async_value("bypass"))
        assert result == "bypass"
    finally:
        await scheduler.stop()


async def _async_value(value: str) -> str:
    await asyncio.sleep(0)
    return value
