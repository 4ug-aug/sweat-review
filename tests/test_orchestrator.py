from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sweat_review.compose import ComposeRenderer
from sweat_review.config import Settings
from sweat_review.github_client import GitHubClient
from sweat_review.orchestrator import Orchestrator
from sweat_review.state import DeploymentStatus, StateStore


@pytest.fixture
def mock_github() -> AsyncMock:
    github = AsyncMock(spec=GitHubClient)
    github.create_or_update_comment = AsyncMock()
    return github


@pytest.fixture
def mock_compose() -> MagicMock:
    compose = MagicMock(spec=ComposeRenderer)
    compose.write_override = MagicMock(return_value=Path("/tmp/override.yml"))
    return compose


@pytest.fixture
def orchestrator(
    settings: Settings, state_store: StateStore, mock_compose: MagicMock, mock_github: AsyncMock
) -> Orchestrator:
    return Orchestrator(settings, state_store, mock_compose, mock_github)


def _make_mock_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def _health_check_ps_output() -> bytes:
    """Fake docker compose ps --format json output with all services running."""
    lines = [
        json.dumps({"Service": "nginx", "State": "running"}),
        json.dumps({"Service": "backend", "State": "running"}),
    ]
    return "\n".join(lines).encode()


@patch("sweat_review.orchestrator.HEALTH_CHECK_DELAY", 0)
@patch("sweat_review.orchestrator.HEALTH_CHECK_INTERVAL", 0)
@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_happy_path(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # git clone + docker compose up
            return _make_mock_process(0, b"ok", b"")
        # health check ps
        return _make_mock_process(0, _health_check_ps_output(), b"")

    with patch("asyncio.create_subprocess_exec", side_effect=side_effect):
        await orchestrator.deploy(pr_number=42, branch="feature", commit_sha="abc123")

    dep = await state_store.get(42)
    assert dep is not None
    assert dep.status == DeploymentStatus.RUNNING
    assert "pr42" in dep.url

    assert mock_github.create_or_update_comment.call_count >= 2


@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_clone_failure(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_mock_process(1, b"", b"fatal: repo not found")
        return _make_mock_process(0)

    with patch("asyncio.create_subprocess_exec", side_effect=side_effect):
        await orchestrator.deploy(pr_number=10, branch="bad", commit_sha="def456")

    dep = await state_store.get(10)
    assert dep is not None
    assert dep.status == DeploymentStatus.FAILED
    assert dep.error_message is not None
    assert "clone failed" in dep.error_message


@patch("sweat_review.orchestrator.check_resources")
async def test_teardown(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    await state_store.upsert(5, "main", "sha", DeploymentStatus.RUNNING, "http://pr-5.test")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0)
        await orchestrator.teardown(5)

    dep = await state_store.get(5)
    assert dep is None

    mock_github.create_or_update_comment.assert_called()


@patch("sweat_review.orchestrator.HEALTH_CHECK_DELAY", 0)
@patch("sweat_review.orchestrator.HEALTH_CHECK_INTERVAL", 0)
@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_commands_are_correct(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore,
) -> None:
    commands_run: list[list[str]] = []

    async def capture_exec(*args, **kwargs):
        commands_run.append(list(args))
        if "ps" in args:
            return _make_mock_process(0, _health_check_ps_output(), b"")
        return _make_mock_process(0)

    with patch("asyncio.create_subprocess_exec", side_effect=capture_exec):
        await orchestrator.deploy(pr_number=7, branch="feat", commit_sha="sha1")

    # First command should be git clone
    assert commands_run[0][0] == "git"
    assert commands_run[0][1] == "clone"
    assert "--branch" in commands_run[0]
    assert "feat" in commands_run[0]

    # Second command should be docker compose up
    assert commands_run[1][0] == "docker"
    assert "pr-7" in commands_run[1]
    assert "up" in commands_run[1]
    assert "--build" in commands_run[1]

    # Third command should be health check ps
    assert commands_run[2][0] == "docker"
    assert "ps" in commands_run[2]


# --- Phase 4 new tests ---


@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_queues_at_max_concurrency(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    # Seed max_concurrent (3) running deployments
    for i in range(1, 4):
        await state_store.upsert(i, "main", f"sha{i}", DeploymentStatus.RUNNING, f"url{i}")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0)
        await orchestrator.deploy(pr_number=99, branch="feat", commit_sha="new")

    dep = await state_store.get(99)
    assert dep is not None
    assert dep.status == DeploymentStatus.QUEUED

    # Should mention queue position in comment
    comment_call = mock_github.create_or_update_comment.call_args
    assert "queued" in comment_call[0][1].lower() or "queued" in str(comment_call)


@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_next_queued_transitions_to_pending(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    # One running, two queued
    await state_store.upsert(1, "main", "sha1", DeploymentStatus.RUNNING, "url1")
    await state_store.upsert(10, "feat-a", "sha10", DeploymentStatus.QUEUED)
    await state_store.upsert(20, "feat-b", "sha20", DeploymentStatus.QUEUED)

    # Mock deploy to avoid actual execution
    with patch.object(orchestrator, "deploy", new_callable=AsyncMock):
        await orchestrator._deploy_next_queued()

    # Oldest queued (PR 10) should transition to PENDING
    dep = await state_store.get(10)
    assert dep is not None
    assert dep.status == DeploymentStatus.PENDING

    # PR 20 should still be queued
    dep20 = await state_store.get(20)
    assert dep20 is not None
    assert dep20.status == DeploymentStatus.QUEUED


@patch("sweat_review.orchestrator.HEALTH_CHECK_DELAY", 0)
@patch("sweat_review.orchestrator.HEALTH_CHECK_INTERVAL", 0)
async def test_health_check_passes(orchestrator: Orchestrator, tmp_path: Path) -> None:
    ps_output = _health_check_ps_output()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0, ps_output, b"")
        result = await orchestrator._check_container_health(1, tmp_path)

    assert result is True


@patch("sweat_review.orchestrator.HEALTH_CHECK_DELAY", 0)
@patch("sweat_review.orchestrator.HEALTH_CHECK_INTERVAL", 0)
async def test_health_check_fails_after_retries(orchestrator: Orchestrator, tmp_path: Path) -> None:
    bad_output = json.dumps({"Service": "backend", "State": "exited"}).encode()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0, bad_output, b"")
        result = await orchestrator._check_container_health(1, tmp_path)

    assert result is False


@patch("sweat_review.orchestrator.check_resources")
async def test_deploy_fails_on_low_resources(
    mock_resources: MagicMock,
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock,
) -> None:
    from sweat_review.resources import InsufficientResourcesError

    mock_resources.side_effect = InsufficientResourcesError("Low disk space: 0.5 GB free")

    await orchestrator.deploy(pr_number=50, branch="feat", commit_sha="sha50")

    dep = await state_store.get(50)
    assert dep is not None
    assert dep.status == DeploymentStatus.FAILED
    assert "disk space" in dep.error_message.lower()
