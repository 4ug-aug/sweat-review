from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sweat_review.cleanup import CleanupService
from sweat_review.config import Settings
from sweat_review.github_client import GitHubClient
from sweat_review.orchestrator import Orchestrator
from sweat_review.state import DeploymentStatus, StateStore


@pytest.fixture
def mock_github() -> AsyncMock:
    github = AsyncMock(spec=GitHubClient)
    github.is_pr_open = AsyncMock(return_value=False)
    return github


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock(spec=Orchestrator)
    orch.teardown = AsyncMock()
    return orch


@pytest.fixture
def cleanup(
    settings: Settings,
    state_store: StateStore,
    mock_orchestrator: AsyncMock,
    mock_github: AsyncMock,
) -> CleanupService:
    return CleanupService(settings, state_store, mock_orchestrator, mock_github)


async def _make_stale(state_store: StateStore, pr_number: int) -> None:
    """Insert a deployment and backdate it to be stale."""
    await state_store.upsert(
        pr_number, "main", "sha1", DeploymentStatus.RUNNING, f"url{pr_number}"
    )
    import aiosqlite

    async with aiosqlite.connect(str(state_store._db_path)) as db:
        await db.execute(
            "UPDATE deployments SET updated_at = datetime('now', '-72 hours') WHERE pr_number = ?",
            (pr_number,),
        )
        await db.commit()


async def test_cleanup_stale_tears_down_closed_pr(
    cleanup: CleanupService, state_store: StateStore, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    await _make_stale(state_store, 1)
    mock_github.is_pr_open.return_value = False

    cleaned = await cleanup.cleanup_stale()

    assert cleaned == [1]
    mock_orchestrator.teardown.assert_called_once_with(1)


async def test_cleanup_stale_skips_open_pr(
    cleanup: CleanupService, state_store: StateStore, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    await _make_stale(state_store, 2)
    mock_github.is_pr_open.return_value = True

    cleaned = await cleanup.cleanup_stale()

    assert cleaned == []
    mock_orchestrator.teardown.assert_not_called()


async def test_cleanup_stale_skips_on_api_error(
    cleanup: CleanupService, state_store: StateStore, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    await _make_stale(state_store, 3)
    mock_github.is_pr_open.side_effect = httpx.HTTPError("API down")

    cleaned = await cleanup.cleanup_stale()

    assert cleaned == []
    mock_orchestrator.teardown.assert_not_called()


async def test_cleanup_orphans_tears_down_unknown_project(
    cleanup: CleanupService, state_store: StateStore, mock_orchestrator: AsyncMock,
) -> None:
    docker_ls_output = json.dumps([
        {"Name": "pr-99", "Status": "running(1)"},
        {"Name": "myapp", "Status": "running(1)"},
    ])

    with patch("sweat_review.cleanup.run_subprocess", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, docker_ls_output, "")
        cleaned = await cleanup.cleanup_orphans()

    assert cleaned == ["pr-99"]
    mock_orchestrator.teardown.assert_called_once_with(99)


async def test_cleanup_orphans_ignores_known_project(
    cleanup: CleanupService, state_store: StateStore, mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(5, "main", "sha", DeploymentStatus.RUNNING, "url5")
    docker_ls_output = json.dumps([{"Name": "pr-5", "Status": "running(1)"}])

    with patch("sweat_review.cleanup.run_subprocess", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, docker_ls_output, "")
        cleaned = await cleanup.cleanup_orphans()

    assert cleaned == []
    mock_orchestrator.teardown.assert_not_called()


async def test_scheduler_start_stop(cleanup: CleanupService) -> None:
    with patch.object(cleanup, "_run_loop", new_callable=AsyncMock):
        await cleanup.start()
        assert cleanup._task is not None

        await cleanup.stop()
        assert cleanup._task is None
