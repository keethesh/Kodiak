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


@pytest.mark.asyncio
async def test_tool_scheduler_coalesces_inflight_duplicate_keys():
    scheduler = ToolScheduler(queue_limit=10)
    scheduler.register_tool("whatweb", concurrency=2)
    await scheduler.start()
    calls = {"count": 0}

    async def _work():
        calls["count"] += 1
        await asyncio.sleep(0.02)
        return "shared-result"

    try:
        first = asyncio.create_task(
            scheduler.execute("whatweb", _work, dedupe_key="whatweb:abc")
        )
        second = asyncio.create_task(
            scheduler.execute("whatweb", _work, dedupe_key="whatweb:abc")
        )
        r1, r2 = await asyncio.gather(first, second)
        assert r1 == "shared-result"
        assert r2 == "shared-result"
        assert calls["count"] == 1
    finally:
        await scheduler.stop()


async def _async_value(value: str) -> str:
    await asyncio.sleep(0)
    return value
