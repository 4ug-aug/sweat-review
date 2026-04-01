from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.orchestrator import Orchestrator, run_subprocess
from preview_agent.state import StateStore

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 1800  # 30 minutes


class CleanupService:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        orchestrator: Orchestrator,
        github: GitHubClient,
    ) -> None:
        self._settings = settings
        self._state = state
        self._orchestrator = orchestrator
        self._github = github
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Cleanup scheduler started (interval: %ds)", CLEANUP_INTERVAL)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            logger.info("Cleanup scheduler stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                stale = await self.cleanup_stale()
                orphans = await self.cleanup_orphans()
                if stale or orphans:
                    logger.info(
                        "Cleanup cycle: %d stale torn down, %d orphans removed",
                        len(stale), len(orphans),
                    )
            except Exception:
                logger.exception("Cleanup cycle failed")
            await asyncio.sleep(CLEANUP_INTERVAL)

    async def cleanup_stale(self) -> list[int]:
        stale = await self._state.get_stale(self._settings.stale_timeout_hours)
        if stale:
            logger.info(
                "Stale check: %d deployments older than %dh — %s",
                len(stale),
                self._settings.stale_timeout_hours,
                [
                    f"PR#{d.pr_number}(status={d.status.value}, updated={d.updated_at})"
                    for d in stale
                ],
            )
        cleaned: list[int] = []
        for dep in stale:
            try:
                pr_open = await self._github.is_pr_open(dep.pr_number)
            except Exception:
                logger.warning(
                    "Could not check PR #%d state, skipping", dep.pr_number
                )
                continue

            if pr_open:
                logger.warning(
                    "PR #%d is stale but still open — leaving deployment",
                    dep.pr_number,
                )
                continue

            logger.info("PR #%d closed and stale — tearing down", dep.pr_number)
            await self._orchestrator.teardown(dep.pr_number)
            cleaned.append(dep.pr_number)
        return cleaned

    async def cleanup_orphans(self) -> list[str]:
        returncode, stdout, stderr = await run_subprocess(
            ["docker", "compose", "ls", "--format", "json"],
            cwd=Path("/tmp"),
        )
        if returncode != 0:
            logger.warning("Could not list compose projects: %s", stderr)
            return []

        try:
            projects = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Could not parse compose project list")
            return []

        cleaned: list[str] = []
        for project in projects:
            name = project.get("Name", "")
            if not name.startswith("pr-"):
                continue
            try:
                pr_number = int(name.removeprefix("pr-"))
            except ValueError:
                continue
            dep = await self._state.get(pr_number)
            if dep is None:
                logger.info("Orphaned project %s — tearing down", name)
                await self._orchestrator.teardown(pr_number)
                cleaned.append(name)
        return cleaned
