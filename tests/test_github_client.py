from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from preview_agent.github_client import GitHubClient


def _mock_response(status_code: int, json_data=None, headers=None):
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.github.com/test"),
    )
    return resp


class TestListOpenPrsEtag:
    async def test_first_call_caches_etag(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")
        pr_data = [{"number": 1, "head": {"ref": "feat", "sha": "abc"}}]

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, pr_data, {"etag": '"etag1"'})
            result = await client.list_open_prs()

        assert len(result) == 1
        assert result[0] == {"number": 1, "branch": "feat", "sha": "abc"}
        assert client._prs_etag == '"etag1"'

    async def test_304_returns_cached_data(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")
        client._prs_etag = '"etag1"'
        client._prs_cache = [{"number": 1, "branch": "feat", "sha": "abc"}]

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(304)
            result = await client.list_open_prs()

        assert result == client._prs_cache
        # Verify If-None-Match was sent
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("headers", {}).get("If-None-Match") == '"etag1"'

    async def test_200_updates_cache(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")
        client._prs_etag = '"etag1"'
        client._prs_cache = [{"number": 1, "branch": "feat", "sha": "abc"}]

        new_data = [{"number": 2, "head": {"ref": "fix", "sha": "def"}}]

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, new_data, {"etag": '"etag2"'})
            result = await client.list_open_prs()

        assert len(result) == 1
        assert result[0] == {"number": 2, "branch": "fix", "sha": "def"}
        assert client._prs_etag == '"etag2"'


class TestIsPrOpenEtag:
    async def test_first_call_caches(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, {"state": "open"}, {"etag": '"e1"'})
            result = await client.is_pr_open(1)

        assert result is True
        assert client._pr_state_cache[1] == ('"e1"', True)

    async def test_304_returns_cached(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")
        client._pr_state_cache[1] = ('"e1"', True)

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(304)
            result = await client.is_pr_open(1)

        assert result is True

    async def test_200_updates_cache(self) -> None:
        client = GitHubClient(token="tok", repo="o/r")
        client._pr_state_cache[1] = ('"e1"', True)

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, {"state": "closed"}, {"etag": '"e2"'})
            result = await client.is_pr_open(1)

        assert result is False
        assert client._pr_state_cache[1] == ('"e2"', False)
