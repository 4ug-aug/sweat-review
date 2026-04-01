from __future__ import annotations

import logging

from preview_agent.config import Settings
from preview_agent.orchestrator import Orchestrator
from preview_agent.state import StateStore

logger = logging.getLogger(__name__)


class CleanupService:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        orchestrator: Orchestrator,
    ) -> None:
        self._settings = settings
        self._state = state
        self._orchestrator = orchestrator

    async def cleanup_stale(self) -> list[int]:
        stale = await self._state.get_stale(self._settings.stale_timeout_hours)
        cleaned: list[int] = []
        for dep in stale:
            logger.info("Cleaning up stale PR #%d", dep.pr_number)
            await self._orchestrator.teardown(dep.pr_number)
            cleaned.append(dep.pr_number)
        return cleaned
