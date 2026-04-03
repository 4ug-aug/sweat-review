from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from sweat_review.config import Settings
from sweat_review.github_client import GitHubClient
from sweat_review.orchestrator import Orchestrator
from sweat_review.poller import PollerService
from sweat_review.state import DeploymentStatus, StateStore


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
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": []},
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
        {"number": 1, "branch": "feat", "sha": "new_sha", "labels": []},
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
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": []},
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
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": []},
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
        {"number": 1, "branch": "feat", "sha": "new_sha", "labels": []},
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


@pytest.fixture
def label_settings(tmp_path: Path) -> Settings:
    return Settings(
        github_token="ghp_test",
        github_repo="owner/repo",
        vps_ip="127.0.0.1",
        clone_base_dir=tmp_path / "repos",
        max_concurrent=3,
        stale_timeout_hours=48,
        poll_interval=30,
        db_path=tmp_path / "test.db",
        compose_file="docker-compose.yml",
        trigger_label="preview",
        template_path=Path(__file__).resolve().parent.parent / "templates" / "docker-compose.override.yml.j2",
    )


@pytest_asyncio.fixture
async def label_state_store(label_settings: Settings) -> StateStore:
    store = StateStore(label_settings.db_path)
    await store.initialize()
    return store


@pytest.fixture
def label_poller(
    label_settings: Settings,
    label_state_store: StateStore,
    mock_orchestrator: AsyncMock,
    mock_github: AsyncMock,
) -> PollerService:
    return PollerService(label_settings, label_state_store, mock_orchestrator, mock_github)


async def test_label_filter_deploys_matching_pr(
    label_poller: PollerService, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": ["preview"]},
    ]

    await label_poller.poll()

    mock_orchestrator.deploy.assert_called_once_with(1, "feat", "abc123")


async def test_label_filter_skips_non_matching_pr(
    label_poller: PollerService, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": ["bug"]},
    ]

    await label_poller.poll()

    mock_orchestrator.deploy.assert_not_called()
    mock_orchestrator.update.assert_not_called()
    mock_orchestrator.teardown.assert_not_called()


async def test_label_removed_triggers_teardown(
    label_poller: PollerService,
    label_state_store: StateStore,
    mock_github: AsyncMock,
    mock_orchestrator: AsyncMock,
) -> None:
    await label_state_store.upsert(1, "feat", "abc123", DeploymentStatus.RUNNING, "url")
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": []},
    ]

    await label_poller.poll()

    mock_orchestrator.teardown.assert_called_once_with(1)


async def test_label_filter_case_insensitive(
    label_poller: PollerService, mock_github: AsyncMock, mock_orchestrator: AsyncMock,
) -> None:
    mock_github.list_open_prs.return_value = [
        {"number": 1, "branch": "feat", "sha": "abc123", "labels": ["Preview"]},
    ]

    await label_poller.poll()

    mock_orchestrator.deploy.assert_called_once_with(1, "feat", "abc123")


async def test_scheduler_start_stop(poller: PollerService) -> None:
    with patch.object(poller, "_run_loop", new_callable=AsyncMock):
        await poller.start()
        assert poller._task is not None

        await poller.stop()
        assert poller._task is None
