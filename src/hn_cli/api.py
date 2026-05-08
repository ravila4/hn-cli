"""Public library API.

All functions are sync; they wrap async internals via `asyncio.run`.
Filtering, depth-truncation, and concurrency are applied here so the
CLI stays a thin shell around these calls.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from hn_cli.client import HNClient
from hn_cli.errors import HNAPIError
from hn_cli.models import Story
from hn_cli.parsing import parse_duration, parse_item_id, truncate_story

Sort = Literal["relevance", "date"]
Feed = Literal["top", "new", "best", "ask", "show", "job"]
SearchType = Literal["story", "ask", "show", "job"]


def get_item(id_or_url: int | str, *, depth: int = 3) -> Story:
    """Fetch a story plus its comment tree (via Algolia) and prune to `depth`."""
    return asyncio.run(_aget_item(id_or_url, depth=depth))


def search(
    query: str,
    *,
    min_score: int | None = None,
    min_comments: int | None = None,
    since: str | None = None,
    limit: int = 30,
    sort: Sort = "relevance",
    type_: SearchType = "story",
) -> list[Story]:
    """Search HN via Algolia. `since` accepts duration strings like '7d', '24h'.

    `type_` filters by submission kind (`story`, `ask`, `show`, `job`); default
    `story` matches all non-job submissions including Ask/Show HN, mirroring
    the prior behavior.
    """
    return asyncio.run(
        _asearch(
            query,
            min_score=min_score,
            min_comments=min_comments,
            since=since,
            limit=limit,
            sort=sort,
            type_=type_,
        )
    )


def get_top(
    *,
    limit: int = 30,
    min_score: int | None = None,
    feed: Feed = "top",
    concurrency: int = 10,
) -> list[Story]:
    """Fetch the front-page feed: Firebase ID list + parallel per-item lookups.

    `min_score` is a post-fetch filter (per spec); narrow the feed-window with
    `limit` first, then drop low-scorers.
    """
    return asyncio.run(
        _aget_top(limit=limit, min_score=min_score, feed=feed, concurrency=concurrency)
    )


# -- async internals ---------------------------------------------------------


async def _aget_item(id_or_url: int | str, *, depth: int) -> Story:
    item_id = parse_item_id(id_or_url)
    async with HNClient() as c:
        data = await c.get_thread_algolia(item_id)
    story = Story.from_algolia_item(data)
    return truncate_story(story, depth)


async def _asearch(
    query: str,
    *,
    min_score: int | None,
    min_comments: int | None,
    since: str | None,
    limit: int,
    sort: Sort,
    type_: SearchType,
) -> list[Story]:
    if not query.strip():
        # Algolia returns all-time top stories on empty query, which is almost
        # never what a caller (especially an agent) actually wants.
        raise ValueError("search query cannot be empty")
    filters: list[str] = []
    if min_score is not None:
        filters.append(f"points>={min_score}")
    if min_comments is not None:
        filters.append(f"num_comments>={min_comments}")
    if since is not None:
        cutoff = int(time.time()) - parse_duration(since)
        filters.append(f"created_at_i>{cutoff}")
    async with HNClient() as c:
        data = await c.search_algolia(
            query,
            numeric_filters=filters or None,
            limit=limit,
            sort=sort,
            type_=type_,
        )
    return [Story.from_algolia_hit(h) for h in data.get("hits") or ()]


async def _aget_top(
    *, limit: int, min_score: int | None, feed: Feed, concurrency: int
) -> list[Story]:
    async with HNClient() as c:
        ids = await c.get_topstories_ids(feed)
        ids = ids[:limit]
        sem = asyncio.Semaphore(concurrency)

        async def fetch_one(item_id: int) -> Story | None:
            async with sem:
                try:
                    data = await c.get_item_firebase(item_id)
                except HNAPIError:
                    # A 404 mid-feed (deleted item) shouldn't crash the whole listing.
                    return None
            try:
                return Story.from_firebase(data)
            except (KeyError, ValueError, TypeError):
                # Firebase occasionally returns malformed/partial payloads during
                # replication lag. Skip the offending item rather than aborting
                # the whole feed; matches the spirit of the 404 case above.
                return None

        results = await asyncio.gather(*[fetch_one(i) for i in ids])
    stories = [s for s in results if s is not None]
    if min_score is not None:
        stories = [s for s in stories if s.score >= min_score]
    return stories
