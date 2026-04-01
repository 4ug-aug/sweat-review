from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

COMMENT_MARKER = "<!-- preview-agent -->"
GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        self._token = token
        self._repo = repo
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        self._prs_etag: str | None = None
        self._prs_cache: list[dict] = []
        self._pr_state_cache: dict[int, tuple[str | None, bool]] = {}  # pr_number -> (etag, is_open)

    async def create_or_update_comment(
        self, pr_number: int, body: str
    ) -> None:
        marked_body = f"{COMMENT_MARKER}\n{body}"
        existing_id = await self._find_comment(pr_number)
        if existing_id is not None:
            resp = await self._client.patch(
                f"/repos/{self._repo}/issues/comments/{existing_id}",
                json={"body": marked_body},
            )
            resp.raise_for_status()
            logger.info("Updated comment %d on PR #%d", existing_id, pr_number)
        else:
            resp = await self._client.post(
                f"/repos/{self._repo}/issues/{pr_number}/comments",
                json={"body": marked_body},
            )
            resp.raise_for_status()
            logger.info("Created comment on PR #%d", pr_number)

    async def _find_comment(self, pr_number: int) -> int | None:
        page = 1
        while True:
            resp = await self._client.get(
                f"/repos/{self._repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            comments = resp.json()
            if not comments:
                return None
            for comment in comments:
                if COMMENT_MARKER in comment.get("body", ""):
                    return comment["id"]
            page += 1

    async def list_open_prs(self) -> list[dict]:
        headers = {}
        if self._prs_etag:
            headers["If-None-Match"] = self._prs_etag

        resp = await self._client.get(
            f"/repos/{self._repo}/pulls",
            params={"state": "open", "per_page": 100},
            headers=headers,
        )

        if resp.status_code == 304:
            logger.debug("list_open_prs: 304 Not Modified (cached)")
            return self._prs_cache

        resp.raise_for_status()
        self._prs_etag = resp.headers.get("etag")

        results: list[dict] = []
        prs = resp.json()
        for pr in prs:
            results.append(
                {
                    "number": pr["number"],
                    "branch": pr["head"]["ref"],
                    "sha": pr["head"]["sha"],
                }
            )

        # Fetch remaining pages (no ETag caching for subsequent pages)
        if len(prs) >= 100:
            page = 2
            while True:
                resp = await self._client.get(
                    f"/repos/{self._repo}/pulls",
                    params={"state": "open", "per_page": 100, "page": page},
                )
                resp.raise_for_status()
                prs = resp.json()
                if not prs:
                    break
                for pr in prs:
                    results.append(
                        {
                            "number": pr["number"],
                            "branch": pr["head"]["ref"],
                            "sha": pr["head"]["sha"],
                        }
                    )
                if len(prs) < 100:
                    break
                page += 1

        self._prs_cache = results
        return results

    async def is_pr_open(self, pr_number: int) -> bool:
        cached = self._pr_state_cache.get(pr_number)
        headers = {}
        if cached:
            etag, _ = cached
            if etag:
                headers["If-None-Match"] = etag

        resp = await self._client.get(
            f"/repos/{self._repo}/pulls/{pr_number}",
            headers=headers,
        )

        if resp.status_code == 304 and cached:
            logger.debug("is_pr_open(%d): 304 Not Modified (cached)", pr_number)
            return cached[1]

        resp.raise_for_status()
        is_open = resp.json().get("state") == "open"
        self._pr_state_cache[pr_number] = (resp.headers.get("etag"), is_open)
        return is_open

    async def close(self) -> None:
        await self._client.aclose()
