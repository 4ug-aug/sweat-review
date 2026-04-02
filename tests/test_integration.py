from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from sweat_review.compose import ComposeRenderer
from sweat_review.config import Settings
from sweat_review.github_client import GitHubClient
from sweat_review.health import router as health_router
from sweat_review.orchestrator import Orchestrator
from sweat_review.state import DeploymentStatus, StateStore


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    return Settings(
        github_token="ghp_test",
        github_repo="owner/repo",
        vps_ip="127.0.0.1",
        clone_base_dir=repos_dir,
        max_concurrent=3,
        stale_timeout_hours=48,
        poll_interval=30,
        db_path=tmp_path / "test.db",
        compose_file="docker-compose.yml",
        template_path=Path(__file__).resolve().parent.parent
        / "templates"
        / "docker-compose.override.yml.j2",
    )


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock(spec=Orchestrator)
    orch.deploy = AsyncMock()
    orch.update = AsyncMock()
    orch.teardown = AsyncMock()
    return orch


@pytest.fixture
async def app(
    test_settings: Settings, mock_orchestrator: AsyncMock
) -> FastAPI:
    state_store = StateStore(test_settings.db_path)
    await state_store.initialize()

    github = MagicMock(spec=GitHubClient)
    compose = ComposeRenderer(test_settings.template_path)

    test_app = FastAPI(title="Preview Agent Test")
    test_app.include_router(health_router)

    test_app.state.settings = test_settings
    test_app.state.state_store = state_store
    test_app.state.github = github
    test_app.state.compose = compose
    test_app.state.orchestrator = mock_orchestrator

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "disk_free_gb" in data
    assert isinstance(data["disk_free_gb"], float)


async def test_status_empty(client: AsyncClient) -> None:
    resp = await client.get("/status")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_status_after_insert(client: AsyncClient, app: FastAPI) -> None:
    state = app.state.state_store
    await state.upsert(7, "main", "sha1", DeploymentStatus.RUNNING, "http://pr-7.test")

    resp = await client.get("/status/7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pr_number"] == 7
    assert data["status"] == "running"

    resp = await client.get("/status/999")
    assert resp.status_code == 404
