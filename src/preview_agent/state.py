from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class DeploymentStatus(StrEnum):
    PENDING = "pending"
    CLONING = "cloning"
    BUILDING = "building"
    RUNNING = "running"
    FAILED = "failed"
    DESTROYING = "destroying"
    QUEUED = "queued"


@dataclass
class Deployment:
    pr_number: int
    branch: str
    commit_sha: str
    status: DeploymentStatus
    url: str
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


class StateStore:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    pr_number     INTEGER PRIMARY KEY,
                    branch        TEXT NOT NULL,
                    commit_sha    TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    url           TEXT NOT NULL DEFAULT '',
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    error_message TEXT
                )
                """
            )
            await db.commit()

    async def upsert(
        self,
        pr_number: int,
        branch: str,
        commit_sha: str,
        status: DeploymentStatus,
        url: str = "",
        error_message: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO deployments
                    (pr_number, branch, commit_sha, status, url, error_message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(pr_number) DO UPDATE SET
                    branch = excluded.branch,
                    commit_sha = excluded.commit_sha,
                    status = excluded.status,
                    url = CASE WHEN excluded.url = '' THEN deployments.url ELSE excluded.url END,
                    error_message = excluded.error_message,
                    updated_at = datetime('now')
                """,
                (pr_number, branch, commit_sha, str(status), url, error_message),
            )
            await db.commit()

    async def get(self, pr_number: int) -> Deployment | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM deployments WHERE pr_number = ?", (pr_number,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_deployment(row)

    async def get_all(self) -> list[Deployment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM deployments ORDER BY pr_number")
            rows = await cursor.fetchall()
            return [self._row_to_deployment(row) for row in rows]

    async def get_active(self) -> list[Deployment]:
        active_statuses = (
            DeploymentStatus.PENDING,
            DeploymentStatus.CLONING,
            DeploymentStatus.BUILDING,
            DeploymentStatus.RUNNING,
            DeploymentStatus.QUEUED,
        )
        placeholders = ",".join("?" for _ in active_statuses)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM deployments WHERE status IN ({placeholders}) ORDER BY pr_number",
                tuple(str(s) for s in active_statuses),
            )
            rows = await cursor.fetchall()
            return [self._row_to_deployment(row) for row in rows]

    async def delete(self, pr_number: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM deployments WHERE pr_number = ?", (pr_number,)
            )
            await db.commit()

    async def get_stale(self, hours: int) -> list[Deployment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM deployments
                WHERE updated_at < datetime('now', ? || ' hours')
                  AND status NOT IN (?, ?)
                ORDER BY pr_number
                """,
                (
                    str(-hours),
                    str(DeploymentStatus.FAILED),
                    str(DeploymentStatus.DESTROYING),
                ),
            )
            rows = await cursor.fetchall()
            return [self._row_to_deployment(row) for row in rows]

    @staticmethod
    def _row_to_deployment(row: aiosqlite.Row) -> Deployment:
        return Deployment(
            pr_number=row["pr_number"],
            branch=row["branch"],
            commit_sha=row["commit_sha"],
            status=DeploymentStatus(row["status"]),
            url=row["url"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error_message=row["error_message"],
        )
