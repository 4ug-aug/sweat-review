from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from preview_agent.cleanup import CleanupService
from preview_agent.poller import PollerService
from preview_agent.compose import ComposeRenderer
from preview_agent.config import get_settings
from preview_agent.github_client import GitHubClient
from preview_agent.health import router as health_router
from preview_agent.orchestrator import Orchestrator
from preview_agent.state import StateStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Initialize state store
    state_store = StateStore(settings.db_path)
    await state_store.initialize()

    # Create services
    github = GitHubClient(
        token=settings.github_token,
        repo=settings.github_repo,
    )
    compose = ComposeRenderer(settings.template_path)
    orchestrator = Orchestrator(settings, state_store, compose, github)

    # Ensure clone base dir exists
    settings.clone_base_dir.mkdir(parents=True, exist_ok=True)

    # Store on app state
    app.state.settings = settings
    app.state.state_store = state_store
    app.state.github = github
    app.state.compose = compose
    app.state.orchestrator = orchestrator

    # Start cleanup scheduler
    cleanup = CleanupService(settings, state_store, orchestrator, github)
    await cleanup.start()
    app.state.cleanup = cleanup

    # Start poller
    poller = PollerService(settings, state_store, orchestrator, github)
    await poller.start()
    app.state.poller = poller

    logger.info("Preview agent started — repo: %s, vps: %s", settings.github_repo, settings.vps_ip)

    yield

    # Shutdown
    await poller.stop()
    await cleanup.stop()
    await github.close()
    logger.info("Preview agent stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Preview Agent", lifespan=lifespan)
    app.include_router(health_router)
    return app


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
