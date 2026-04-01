from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from preview_agent.compose import ComposeRenderer
from preview_agent.config import Settings
from preview_agent.github_client import GitHubClient
from preview_agent.state import DeploymentStatus, StateStore

logger = logging.getLogger(__name__)

DEPLOY_TIMEOUT = 300  # 5 minutes
TEARDOWN_TIMEOUT = 120  # 2 minutes


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        compose: ComposeRenderer,
        github: GitHubClient,
    ) -> None:
        self._settings = settings
        self._state = state
        self._compose = compose
        self._github = github
        self._semaphore = asyncio.Semaphore(settings.max_concurrent)
        self._pr_locks: dict[int, asyncio.Lock] = {}

    def _get_pr_lock(self, pr_number: int) -> asyncio.Lock:
        if pr_number not in self._pr_locks:
            self._pr_locks[pr_number] = asyncio.Lock()
        return self._pr_locks[pr_number]

    def _clone_dir(self, pr_number: int) -> Path:
        return self._settings.clone_base_dir / f"pr-{pr_number}"

    def _preview_url(self, pr_number: int) -> str:
        return f"http://pr{pr_number}.{self._settings.vps_ip}.nip.io"

    def _clone_url(self) -> str:
        repo = self._settings.github_repo
        token = self._settings.github_token
        if token:
            return f"https://x-access-token:{token}@github.com/{repo}.git"
        return f"https://github.com/{repo}.git"

    async def deploy(
        self, pr_number: int, branch: str, commit_sha: str
    ) -> None:
        async with self._get_pr_lock(pr_number):
            # Check concurrency
            active = await self._state.get_active()
            running_count = len(
                [d for d in active if d.status == DeploymentStatus.RUNNING]
            )
            if running_count >= self._settings.max_concurrent:
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.QUEUED
                )
                await self._github.create_or_update_comment(
                    pr_number,
                    "Preview queued — max concurrency reached. "
                    "It will deploy when a slot opens up.",
                )
                logger.warning("PR #%d queued — at max concurrency", pr_number)
                return

            url = self._preview_url(pr_number)
            clone_dir = self._clone_dir(pr_number)

            try:
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.PENDING
                )
                await self._github.create_or_update_comment(
                    pr_number, "Deploying preview environment..."
                )

                # Clone
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.CLONING
                )
                clone_dir.parent.mkdir(parents=True, exist_ok=True)
                if clone_dir.exists():
                    shutil.rmtree(clone_dir)

                returncode, stdout, stderr = await self._run(
                    [
                        "git", "clone", "--depth", "1",
                        "--branch", branch,
                        self._clone_url(), str(clone_dir),
                    ],
                    cwd=clone_dir.parent,
                )
                if returncode != 0:
                    raise RuntimeError(f"git clone failed: {stderr}")

                # Render override
                self._compose.write_override(clone_dir, pr_number, self._settings.vps_ip)

                # Build and start
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.BUILDING
                )
                compose_file = self._settings.compose_file
                returncode, stdout, stderr = await self._run(
                    [
                        "docker", "compose",
                        "-p", f"pr-{pr_number}",
                        "-f", compose_file,
                        "-f", "docker-compose.override.yml",
                        "up", "-d", "--build",
                    ],
                    cwd=clone_dir,
                    timeout=DEPLOY_TIMEOUT,
                )
                if returncode != 0:
                    raise RuntimeError(f"docker compose up failed: {stderr}")

                # Success
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.RUNNING, url=url
                )
                await self._github.create_or_update_comment(
                    pr_number,
                    f"Preview environment ready: {url}",
                )
                logger.info("PR #%d deployed at %s", pr_number, url)

            except Exception as exc:
                error_msg = str(exc)[:500]
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.FAILED,
                    error_message=error_msg,
                )
                await self._github.create_or_update_comment(
                    pr_number,
                    f"Preview deployment failed:\n```\n{error_msg}\n```",
                )
                logger.error("PR #%d deploy failed: %s", pr_number, error_msg)

    async def teardown(self, pr_number: int) -> None:
        async with self._get_pr_lock(pr_number):
            clone_dir = self._clone_dir(pr_number)

            try:
                await self._state.upsert(
                    pr_number, "", "", DeploymentStatus.DESTROYING
                )

                returncode, stdout, stderr = await self._run(
                    [
                        "docker", "compose",
                        "-p", f"pr-{pr_number}",
                        "down", "-v", "--remove-orphans",
                    ],
                    cwd=clone_dir if clone_dir.exists() else Path("/tmp"),
                    timeout=TEARDOWN_TIMEOUT,
                )
                if returncode != 0:
                    logger.warning(
                        "docker compose down for PR #%d returned %d: %s",
                        pr_number, returncode, stderr,
                    )

                shutil.rmtree(clone_dir, ignore_errors=True)
                await self._state.delete(pr_number)
                await self._github.create_or_update_comment(
                    pr_number, "Preview environment torn down."
                )
                logger.info("PR #%d torn down", pr_number)

            except Exception as exc:
                logger.error("PR #%d teardown failed: %s", pr_number, exc)

            # Check for queued deployments
            await self._deploy_next_queued()

    async def update(self, pr_number: int, branch: str, commit_sha: str) -> None:
        async with self._get_pr_lock(pr_number):
            clone_dir = self._clone_dir(pr_number)

            if not clone_dir.exists():
                logger.info("PR #%d clone dir missing, doing full deploy", pr_number)
            # Release lock and do full deploy if no clone dir
            if not clone_dir.exists():
                await self.deploy(pr_number, branch, commit_sha)
                return

            try:
                await self._github.create_or_update_comment(
                    pr_number, "Updating preview environment..."
                )

                # Pull latest
                returncode, stdout, stderr = await self._run(
                    ["git", "fetch", "origin", branch],
                    cwd=clone_dir,
                )
                if returncode != 0:
                    raise RuntimeError(f"git fetch failed: {stderr}")

                returncode, stdout, stderr = await self._run(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    cwd=clone_dir,
                )
                if returncode != 0:
                    raise RuntimeError(f"git reset failed: {stderr}")

                # Re-render override and rebuild
                self._compose.write_override(clone_dir, pr_number, self._settings.vps_ip)

                compose_file = self._settings.compose_file
                returncode, stdout, stderr = await self._run(
                    [
                        "docker", "compose",
                        "-p", f"pr-{pr_number}",
                        "-f", compose_file,
                        "-f", "docker-compose.override.yml",
                        "up", "-d", "--build",
                    ],
                    cwd=clone_dir,
                    timeout=DEPLOY_TIMEOUT,
                )
                if returncode != 0:
                    raise RuntimeError(f"docker compose up failed: {stderr}")

                url = self._preview_url(pr_number)
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.RUNNING, url=url
                )
                await self._github.create_or_update_comment(
                    pr_number, f"Preview environment updated: {url}"
                )
                logger.info("PR #%d updated", pr_number)

            except Exception as exc:
                error_msg = str(exc)[:500]
                await self._state.upsert(
                    pr_number, branch, commit_sha, DeploymentStatus.FAILED,
                    error_message=error_msg,
                )
                await self._github.create_or_update_comment(
                    pr_number,
                    f"Preview update failed:\n```\n{error_msg}\n```",
                )
                logger.error("PR #%d update failed: %s", pr_number, error_msg)

    async def _deploy_next_queued(self) -> None:
        active = await self._state.get_active()
        queued = [d for d in active if d.status == DeploymentStatus.QUEUED]
        if not queued:
            return
        next_dep = min(queued, key=lambda d: d.created_at)
        logger.info("Deploying queued PR #%d", next_dep.pr_number)
        asyncio.create_task(
            self.deploy(next_dep.pr_number, next_dep.branch, next_dep.commit_sha)
        )

    async def _run(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: float = 60,
    ) -> tuple[int, str, str]:
        logger.debug("Running: %s in %s", " ".join(cmd), cwd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return 1, "", f"Command timed out after {timeout}s"

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        logger.debug("Exit %d | stdout: %s | stderr: %s", proc.returncode, stdout[:200], stderr[:200])
        return proc.returncode or 0, stdout, stderr
