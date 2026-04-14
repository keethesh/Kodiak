import importlib
from uuid import uuid4

import pytest

from kodiak.core.shared_store import SharedScanStore
from kodiak.database.models import ScanEventType


class FakeSession:
    def __init__(self) -> None:
        self.add_count = 0
        self.flush_count = 0
        self.commit_count = 0
        self.refresh_count = 0

    def add(self, _obj) -> None:
        self.add_count += 1

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, _obj) -> None:
        self.refresh_count += 1

    async def rollback(self) -> None:  # pragma: no cover - parity with AsyncSession API
        return None


@pytest.mark.asyncio
async def test_append_event_auto_commit_false_uses_existing_transaction():
    store = SharedScanStore(project_id=uuid4(), scan_id=uuid4())
    session = FakeSession()

    event = await store.append_event(
        session,
        event_type=ScanEventType.NOTE_ADDED,
        payload={"category": "attack_hint"},
        auto_commit=False,
    )

    assert event is not None
    assert session.add_count == 1
    assert session.flush_count == 1
    assert session.commit_count == 0
    assert session.refresh_count == 0


@pytest.mark.asyncio
async def test_append_event_auto_commit_true_commits_immediately():
    store = SharedScanStore(project_id=uuid4(), scan_id=uuid4())
    session = FakeSession()

    event = await store.append_event(
        session,
        event_type=ScanEventType.NOTE_ADDED,
        payload={"category": "attack_hint"},
    )

    assert event is not None
    assert session.add_count == 1
    assert session.flush_count == 0
    assert session.commit_count == 1
    assert session.refresh_count == 1


def test_database_engine_proxy_shares_canonical_singleton(monkeypatch):
    engine_module = importlib.import_module("kodiak.database.engine")

    created = []

    class FakeEngine:
        def __init__(self, marker: str) -> None:
            self.marker = marker

    def fake_create_engine():
        marker = f"engine-{len(created) + 1}"
        instance = FakeEngine(marker)
        created.append(instance)
        return instance

    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_create_engine", fake_create_engine)

    first = engine_module.get_engine()
    via_proxy_marker = engine_module.engine.marker
    second = engine_module.get_engine()

    assert first is second
    assert via_proxy_marker == "engine-1"
    assert len(created) == 1
