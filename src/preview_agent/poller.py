from __future__ import annotations

import asyncio
import contextlib
import logging

from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.orchestrator import Orchestrator
from preview_agent.state import DeploymentStatus, StateStore

logger = logging.getLogger(__name__)

SKIP_STATUSES = frozenset({DeploymentStatus.DESTROYING})
IN_PROGRESS_STATUSES = frozenset(
    {
        DeploymentStatus.PENDING,
        DeploymentStatus.CLONING,
        DeploymentStatus.BUILDING,
        DeploymentStatus.QUEUED,
    }
)


class PollerService:
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
        logger.info(
            "Poller started (interval: %ds)", self._settings.poll_interval
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            logger.info("Poller stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.poll()
            except Exception:
                logger.exception("Poll cycle failed")
            await asyncio.sleep(self._settings.poll_interval)

    async def poll(self) -> None:
        # Fetch open PRs from GitHub
        try:
            open_prs = await self._github.list_open_prs()
        except Exception:
            logger.warning("Failed to fetch open PRs, skipping cycle", exc_info=True)
            return

        open_pr_map = {pr["number"]: pr for pr in open_prs}
        open_pr_numbers = set(open_pr_map.keys())

        # Fetch all deployments from state
        deployments = await self._state.get_all()
        deployment_map = {dep.pr_number: dep for dep in deployments}

        logger.info(
            "Poll: %d open PRs %s, %d tracked deployments %s",
            len(open_pr_map),
            sorted(open_pr_map.keys()),
            len(deployment_map),
            {pr: dep.status.value for pr, dep in deployment_map.items()},
        )

        # New or updated PRs
        for pr_number, pr in open_pr_map.items():
            dep = deployment_map.get(pr_number)

            if dep is None:
                # New PR — deploy
                logger.info(
                    "PR #%d new — branch=%s sha=%s — deploying",
                    pr_number, pr["branch"], pr["sha"][:7],
                )
                await self._orchestrator.deploy(
                    pr_number, pr["branch"], pr["sha"]
                )
                continue

            if dep.status in SKIP_STATUSES:
                logger.debug(
                    "PR #%d status=%s — skipping (teardown in progress)",
                    pr_number, dep.status.value,
                )
                continue

            if dep.status in IN_PROGRESS_STATUSES:
                logger.debug(
                    "PR #%d status=%s sha=%s — skipping (in progress)",
                    pr_number, dep.status.value, dep.commit_sha[:7],
                )
                continue

            if dep.commit_sha == pr["sha"]:
                logger.debug(
                    "PR #%d status=%s sha=%s — no change",
                    pr_number, dep.status.value, dep.commit_sha[:7],
                )
                continue

            # SHA changed — update (handles both RUNNING and FAILED with new push)
            logger.info(
                "PR #%d SHA changed (%s → %s) status=%s — updating",
                pr_number, dep.commit_sha[:7], pr["sha"][:7], dep.status.value,
            )
            await self._orchestrator.update(
                pr_number, pr["branch"], pr["sha"]
            )

        # Closed PRs — teardown deployments for PRs no longer open
        for pr_number, dep in deployment_map.items():
            if pr_number not in open_pr_numbers and dep.status not in SKIP_STATUSES:
                logger.info(
                    "PR #%d no longer open (was %s, sha=%s, updated=%s) — tearing down",
                    pr_number, dep.status.value, dep.commit_sha[:7], dep.updated_at,
                )
                await self._orchestrator.teardown(pr_number)
