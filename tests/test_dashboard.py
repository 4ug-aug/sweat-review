from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sweat_review.compose import ComposeRenderer
from sweat_review.config import Settings
from sweat_review.dashboard import relative_time, render_dashboard, router as dashboard_router
from sweat_review.state import Deployment, DeploymentStatus, StateStore


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
async def app(test_settings: Settings) -> FastAPI:
    state_store = StateStore(test_settings.db_path)
    await state_store.initialize()
    test_app = FastAPI()
    test_app.include_router(dashboard_router)
    test_app.state.settings = test_settings
    test_app.state.state_store = state_store
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_dashboard_returns_html(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Preview Agent" in resp.text


async def test_dashboard_empty_state(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert "No preview environments" in resp.text


async def test_dashboard_shows_deployment(client: AsyncClient, app: FastAPI) -> None:
    state = app.state.state_store
    await state.upsert(
        42, "feat/login", "abc1234def", DeploymentStatus.RUNNING,
        url="http://pr42.127.0.0.1.nip.io",
    )
    resp = await client.get("/")
    assert "#42" in resp.text
    assert "feat/login" in resp.text
    assert "abc1234" in resp.text
    assert "http://pr42.127.0.0.1.nip.io" in resp.text
    assert "Running" in resp.text


async def test_dashboard_failed_no_link(client: AsyncClient, app: FastAPI) -> None:
    state = app.state.state_store
    await state.upsert(
        10, "fix/bug", "deadbeef123", DeploymentStatus.FAILED,
        error_message="build failed",
    )
    resp = await client.get("/")
    assert "#10" in resp.text
    assert "Failed" in resp.text
    # No clickable preview link for failed deployments
    assert "nip.io" not in resp.text


async def test_dashboard_pr_links_to_github(client: AsyncClient, app: FastAPI) -> None:
    state = app.state.state_store
    await state.upsert(5, "main", "sha123", DeploymentStatus.RUNNING)
    resp = await client.get("/")
    assert "https://github.com/owner/repo/pull/5" in resp.text


def test_relative_time_seconds() -> None:
    now = datetime.now(timezone.utc)
    assert relative_time(now - timedelta(seconds=15)) == "15s ago"


def test_relative_time_minutes() -> None:
    now = datetime.now(timezone.utc)
    assert relative_time(now - timedelta(minutes=3)) == "3m ago"


def test_relative_time_hours() -> None:
    now = datetime.now(timezone.utc)
    assert relative_time(now - timedelta(hours=5)) == "5h ago"


def test_relative_time_days() -> None:
    now = datetime.now(timezone.utc)
    assert relative_time(now - timedelta(days=2)) == "2d ago"


def test_relative_time_future() -> None:
    now = datetime.now(timezone.utc)
    assert relative_time(now + timedelta(minutes=5)) == "just now"


def test_relative_time_naive_datetime() -> None:
    # Naive datetimes (from SQLite) should be treated as UTC
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(minutes=10)).replace(tzinfo=None)
    assert relative_time(naive) == "10m ago"
