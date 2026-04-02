import pytest

from sweat_review.state import DeploymentStatus, StateStore


pytestmark = pytest.mark.asyncio


async def test_initialize_is_idempotent(state_store: StateStore) -> None:
    await state_store.initialize()
    await state_store.initialize()


async def test_upsert_and_get(state_store: StateStore) -> None:
    await state_store.upsert(
        pr_number=1,
        branch="feature-x",
        commit_sha="abc123",
        status=DeploymentStatus.RUNNING,
        url="http://pr-1.127.0.0.1.nip.io",
    )
    dep = await state_store.get(1)
    assert dep is not None
    assert dep.pr_number == 1
    assert dep.branch == "feature-x"
    assert dep.commit_sha == "abc123"
    assert dep.status == DeploymentStatus.RUNNING
    assert dep.url == "http://pr-1.127.0.0.1.nip.io"
    assert dep.error_message is None


async def test_get_nonexistent(state_store: StateStore) -> None:
    assert await state_store.get(999) is None


async def test_upsert_updates_existing(state_store: StateStore) -> None:
    await state_store.upsert(
        pr_number=1,
        branch="feature-x",
        commit_sha="abc123",
        status=DeploymentStatus.BUILDING,
        url="http://pr-1.127.0.0.1.nip.io",
    )
    await state_store.upsert(
        pr_number=1,
        branch="feature-x",
        commit_sha="def456",
        status=DeploymentStatus.RUNNING,
    )
    dep = await state_store.get(1)
    assert dep is not None
    assert dep.commit_sha == "def456"
    assert dep.status == DeploymentStatus.RUNNING
    # URL preserved when new url is empty
    assert dep.url == "http://pr-1.127.0.0.1.nip.io"


async def test_get_all(state_store: StateStore) -> None:
    await state_store.upsert(1, "a", "sha1", DeploymentStatus.RUNNING, "url1")
    await state_store.upsert(2, "b", "sha2", DeploymentStatus.FAILED, "url2")
    all_deps = await state_store.get_all()
    assert len(all_deps) == 2
    assert all_deps[0].pr_number == 1
    assert all_deps[1].pr_number == 2


async def test_get_active(state_store: StateStore) -> None:
    await state_store.upsert(1, "a", "sha1", DeploymentStatus.RUNNING, "url1")
    await state_store.upsert(2, "b", "sha2", DeploymentStatus.FAILED, "url2")
    await state_store.upsert(3, "c", "sha3", DeploymentStatus.BUILDING, "url3")
    active = await state_store.get_active()
    assert len(active) == 2
    assert {d.pr_number for d in active} == {1, 3}


async def test_delete(state_store: StateStore) -> None:
    await state_store.upsert(1, "a", "sha1", DeploymentStatus.RUNNING, "url1")
    await state_store.delete(1)
    assert await state_store.get(1) is None


async def test_get_stale(state_store: StateStore) -> None:
    await state_store.upsert(1, "a", "sha1", DeploymentStatus.RUNNING, "url1")
    # Manually set updated_at to 72 hours ago
    import aiosqlite

    async with aiosqlite.connect(str(state_store._db_path)) as db:
        await db.execute(
            "UPDATE deployments SET updated_at = datetime('now', '-72 hours') WHERE pr_number = 1"
        )
        await db.commit()

    stale = await state_store.get_stale(48)
    assert len(stale) == 1
    assert stale[0].pr_number == 1

    # Non-stale deployment should not appear
    await state_store.upsert(2, "b", "sha2", DeploymentStatus.RUNNING, "url2")
    stale = await state_store.get_stale(48)
    assert len(stale) == 1
