from pathlib import Path

import pytest
import pytest_asyncio

from preview_agent.config import Settings
from preview_agent.compose import ComposeRenderer
from preview_agent.state import StateStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
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
        template_path=PROJECT_ROOT / "templates" / "docker-compose.override.yml.j2",
    )


@pytest_asyncio.fixture
async def state_store(settings: Settings) -> StateStore:
    store = StateStore(settings.db_path)
    await store.initialize()
    return store


@pytest.fixture
def compose_renderer(settings: Settings) -> ComposeRenderer:
    return ComposeRenderer(settings.template_path)
