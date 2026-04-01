from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from preview_agent.compose import ComposeRenderer
from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.health import router as health_router
from preview_agent.orchestrator import Orchestrator
from preview_agent.state import DeploymentStatus, StateStore
from preview_agent.webhook import router as webhook_router

WEBHOOK_SECRET = "test-secret"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        github_webhook_secret=WEBHOOK_SECRET,
        github_token="ghp_test",
        github_repo="owner/repo",
        vps_ip="127.0.0.1",
        clone_base_dir=tmp_path / "repos",
        max_concurrent=3,
        stale_timeout_hours=48,
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
    github.verify_signature = GitHubClient(
        token="", repo="", webhook_secret=WEBHOOK_SECRET
    ).verify_signature

    compose = ComposeRenderer(test_settings.template_path)

    # No lifespan — set state directly on the app
    test_app = FastAPI(title="Preview Agent Test")
    test_app.include_router(webhook_router)
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


def _sign(payload: bytes) -> str:
    digest = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _pr_payload(action: str, pr_number: int = 42) -> bytes:
    return json.dumps(
        {
            "action": action,
            "number": pr_number,
            "pull_request": {
                "head": {
                    "ref": "feature-branch",
                    "sha": "abc123def456",
                }
            },
        }
    ).encode()


async def test_health_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_webhook_rejects_bad_signature(client: AsyncClient) -> None:
    payload = _pr_payload("opened")
    resp = await client.post(
        "/webhook",
        content=payload,
        headers={
            "X-Hub-Signature-256": "sha256=bad",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403


async def test_webhook_accepts_pr_opened(
    client: AsyncClient, mock_orchestrator: AsyncMock
) -> None:
    payload = _pr_payload("opened")
    resp = await client.post(
        "/webhook",
        content=payload,
        headers={
            "X-Hub-Signature-256": _sign(payload),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["action"] == "opened"
    assert data["pr"] == 42


async def test_webhook_accepts_pr_closed(
    client: AsyncClient, mock_orchestrator: AsyncMock
) -> None:
    payload = _pr_payload("closed", pr_number=10)
    resp = await client.post(
        "/webhook",
        content=payload,
        headers={
            "X-Hub-Signature-256": _sign(payload),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "closed"


async def test_webhook_ignores_non_pr_events(client: AsyncClient) -> None:
    payload = b'{"action": "created"}'
    resp = await client.post(
        "/webhook",
        content=payload,
        headers={
            "X-Hub-Signature-256": _sign(payload),
            "X-GitHub-Event": "issues",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


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
