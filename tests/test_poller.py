from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.orchestrator import Orchestrator
from preview_agent.poller import PollerService
from preview_agent.state import DeploymentStatus, StateStore


@pytest.fixture
def mock_github() -> AsyncMock:
    github = AsyncMock(spec=GitHubClient)
    github.list_open_prs = AsyncMock(return_value=[])
    return github


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock(spec=Orchestrator)
    orch.deploy = AsyncMock()
    orch.update = AsyncMock()
    orch.teardown = AsyncMock()
    return orch


@pytest.fixture
def poller(
    settings: Settings,
    state_store: StateStore,
    mock_orchestrator: AsyncMock,
    mock_github: AsyncMock,
) -> PollerService:
    return PollerService(settings, state_store, mock_orchestrator, mock_github)


async def test_new_pr_triggers_deploy(
    poller: PollerService, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123"},
    ]

    await poller.poll()

    mock_orchestrator.deploy.assert_called_once_with(1, "feat", "abc123")


async def test_sha_change_triggers_update(
    poller: PollerService,
    state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(1, "feat", "old_sha", DeploymentStatus.RUNNING, "url")
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "new_sha"},
    ]

    await poller.poll()

    mock_orchestrator.update.assert_called_once_with(1, "feat", "new_sha")
    mock_orchestrator.deploy.assert_not_called()


async def test_closed_pr_triggers_teardown(
    poller: PollerService,
    state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(1, "feat", "sha1", DeploymentStatus.RUNNING, "url")
    mock_github.list_open_prs.return_value = []  # PR closed

    await poller.poll()

    mock_orchestrator.teardown.assert_called_once_with(1)


async def test_same_sha_no_action(
    poller: PollerService,
    state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(1, "feat", "abc123", DeploymentStatus.RUNNING, "url")
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123"},
    ]

    await poller.poll()

    mock_orchestrator.deploy.assert_not_called()
    mock_orchestrator.update.assert_not_called()
    mock_orchestrator.teardown.assert_not_called()


async def test_failed_same_sha_no_retry(
    poller: PollerService,
    state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(1, "feat", "abc123", DeploymentStatus.FAILED, "url")
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123"},
    ]

    await poller.poll()

    mock_orchestrator.deploy.assert_not_called()
    mock_orchestrator.update.assert_not_called()


async def test_failed_new_sha_triggers_update(
    poller: PollerService,
    state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await state_store.upsert(1, "feat", "old_sha", DeploymentStatus.FAILED, "url")
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "new_sha"},
    ]

    await poller.poll()

    mock_orchestrator.update.assert_called_once_with(1, "feat", "new_sha")


async def test_github_api_error_no_crash(
    poller: PollerService,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    mock_github.list_open_prs.side_effect = httpx.HTTPError("API down")

    await poller.poll()  # Should not raise

    mock_orchestrator.deploy.assert_not_called()
    mock_orchestrator.update.assert_not_called()
    mock_orchestrator.teardown.assert_not_called()


async def test_scheduler_start_stop(poller: PollerService) -> None:
    with patch.object(poller, "_run_loop", new_callable=AsyncMock):
        await poller.start()
        assert poller._task is not None

        await poller.stop()
        assert poller._task is None
