"""Async HTTP client wrapping the Firebase and Algolia HN endpoints.

Single class with two private helpers — `_firebase_get` and `_algolia_get` —
because the routing rule is one-line stable: Firebase for the canonical
front-page feed, Algolia for search and full-thread fetches.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from hn_cli.errors import HNAPIError

_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"

_FEED_FILES = {
    "top": "topstories.json",
    "new": "newstories.json",
    "best": "beststories.json",
    "ask": "askstories.json",
    "show": "showstories.json",
    "job": "jobstories.json",
}


def _user_agent() -> str:
    try:
        return f"hn-cli/{version('hn-cli')}"
    except PackageNotFoundError:
        return "hn-cli/unknown"


class HNClient:
    def __init__(self, *, timeout: float = 10.0, user_agent: str | None = None) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent or _user_agent()},
            timeout=timeout,
        )

    async def __aenter__(self) -> HNClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, str] | None = None) -> Any:
        try:
            r = await self._client.get(url, params=params)
        except httpx.HTTPError as e:
            raise HNAPIError(status_code=0, url=url, message=str(e)) from e
        if r.status_code != 200:
            raise HNAPIError(status_code=r.status_code, url=str(r.url), message=r.text[:200])
        return r.json()

    async def _firebase_get(self, path: str) -> Any:
        return await self._get(f"{_FIREBASE_BASE}/{path}")

    async def _algolia_get(self, path: str, params: dict[str, str] | None = None) -> Any:
        return await self._get(f"{_ALGOLIA_BASE}/{path}", params=params)

    async def get_topstories_ids(self, feed: str = "top") -> list[int]:
        if feed not in _FEED_FILES:
            raise ValueError(f"unknown feed {feed!r}; expected one of {sorted(_FEED_FILES)}")
        ids = await self._firebase_get(_FEED_FILES[feed])
        return list(ids or [])

    async def get_item_firebase(self, item_id: int) -> dict[str, Any]:
        data = await self._firebase_get(f"item/{item_id}.json")
        if data is None:
            raise HNAPIError(
                status_code=404,
                url=f"{_FIREBASE_BASE}/item/{item_id}.json",
                message="item not found",
            )
        return data

    async def get_thread_algolia(self, item_id: int) -> dict[str, Any]:
        return await self._algolia_get(f"items/{item_id}")

    async def search_algolia(
        self,
        query: str,
        *,
        numeric_filters: list[str] | None = None,
        limit: int = 30,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        endpoint = "search" if sort == "relevance" else "search_by_date"
        params: dict[str, str] = {
            "query": query,
            "tags": "story",
            "hitsPerPage": str(limit),
        }
        if numeric_filters:
            params["numericFilters"] = ",".join(numeric_filters)
        return await self._algolia_get(endpoint, params=params)
