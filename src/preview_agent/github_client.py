from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

logger = logging.getLogger(__name__)

COMMENT_MARKER = "<!-- preview-agent -->"
GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, repo: str, webhook_secret: str) -> None:
        self._token = token
        self._repo = repo
        self._webhook_secret = webhook_secret
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self._webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

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

    async def close(self) -> None:
        await self._client.aclose()
