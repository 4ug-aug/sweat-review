from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from preview_agent.compose import ComposeRenderer
from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.orchestrator import Orchestrator
from preview_agent.state import DeploymentStatus, StateStore


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


async def test_deploy_happy_path(
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock
) -> None:
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0, b"ok", b"")
        await orchestrator.deploy(pr_number=42, branch="feature", commit_sha="abc123")

    dep = await state_store.get(42)
    assert dep is not None
    assert dep.status == DeploymentStatus.RUNNING
    assert "pr42" in dep.url

    # Should have posted at least 2 comments (deploying + ready)
    assert mock_github.create_or_update_comment.call_count >= 2


async def test_deploy_clone_failure(
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock
) -> None:
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # git clone fails
            return _make_mock_process(1, b"", b"fatal: repo not found")
        return _make_mock_process(0)

    with patch("asyncio.create_subprocess_exec", side_effect=side_effect):
        await orchestrator.deploy(pr_number=10, branch="bad", commit_sha="def456")

    dep = await state_store.get(10)
    assert dep is not None
    assert dep.status == DeploymentStatus.FAILED
    assert dep.error_message is not None
    assert "clone failed" in dep.error_message


async def test_teardown(
    orchestrator: Orchestrator, state_store: StateStore, mock_github: AsyncMock
) -> None:
    # Seed a running deployment
    await state_store.upsert(5, "main", "sha", DeploymentStatus.RUNNING, "http://pr-5.test")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(0)
        await orchestrator.teardown(5)

    dep = await state_store.get(5)
    assert dep is None  # deleted after teardown

    mock_github.create_or_update_comment.assert_called()


async def test_deploy_commands_are_correct(
    orchestrator: Orchestrator, state_store: StateStore
) -> None:
    commands_run: list[list[str]] = []

    async def capture_exec(*args, **kwargs):
        commands_run.append(list(args))
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
