"""Pure parsing helpers: item-id resolution, duration strings, tree truncation."""

from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from hn_cli.models import Comment, Story

_ITEM_URL_HOST = "news.ycombinator.com"
_DURATION_RE = re.compile(r"^(\d+)([smhdwy])$")
_DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 7 * 86400,
    "y": 365 * 86400,
}


def parse_item_id(value: int | str) -> int:
    """Resolve an HN item ID from an int, decimal string, or HN item URL.

    Raises ValueError on any input we cannot resolve to a positive integer ID.
    """
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"item id must be positive, got {value}")
        return value

    if not isinstance(value, str):
        raise ValueError(f"unsupported item id type: {type(value).__name__}")

    s = value.strip()
    if not s:
        raise ValueError("item id is empty")

    if s.lstrip("-").isdigit():
        n = int(s)
        if n <= 0:
            raise ValueError(f"item id must be positive, got {n}")
        return n

    if "://" in s:
        return _parse_hn_url(s)

    raise ValueError(f"could not parse item id from: {value!r}")


def _parse_hn_url(url: str) -> int:
    parsed = urlparse(url)
    if parsed.hostname != _ITEM_URL_HOST:
        raise ValueError(f"not a Hacker News URL: {url!r}")
    qs = parse_qs(parsed.query)
    raw = qs.get("id", [None])[0]
    if raw is None or not raw.isdigit():
        raise ValueError(f"no item id in URL: {url!r}")
    n = int(raw)
    if n <= 0:
        raise ValueError(f"item id must be positive, got {n}")
    return n


def parse_duration(s: str) -> int:
    """Parse a duration string like '7d' or '24h' into seconds.

    Supported units: s, m, h, d, w, y. Years assume 365 days. Case-insensitive.
    Raises ValueError on bad input. Negative durations are rejected; zero is allowed.
    """
    if not isinstance(s, str):
        raise ValueError(f"duration must be a string, got {type(s).__name__}")
    cleaned = s.strip().lower()
    m = _DURATION_RE.match(cleaned)
    if not m:
        raise ValueError(f"invalid duration: {s!r}")
    n, unit = int(m.group(1)), m.group(2)
    return n * _DURATION_UNITS[unit]


def truncate_story(story: Story, max_depth: int) -> Story:
    """Prune the comment tree on `story` to at most `max_depth` levels.

    `max_depth=0` hides all comments and records the total descendant count
    in `story.truncated_replies`. `max_depth=1` keeps top-level comments but
    strips their replies, and so on.

    Note: this is a client-side prune. Algolia's `items/{id}` returns the
    full thread regardless of depth — there is no server-side knob here.
    """
    if max_depth <= 0:
        n = _count_descendants(story.children)
        return replace(story, children=(), truncated_replies=n)
    new_children = tuple(_truncate_comment(c, max_depth - 1) for c in story.children)
    return replace(story, children=new_children, truncated_replies=0)


def _truncate_comment(c: Comment, remaining: int) -> Comment:
    if remaining <= 0:
        n = _count_descendants(c.children)
        return replace(c, children=(), truncated_replies=n)
    new_children = tuple(_truncate_comment(child, remaining - 1) for child in c.children)
    return replace(c, children=new_children, truncated_replies=0)


def _count_descendants(children: tuple[Comment, ...]) -> int:
    return sum(1 + _count_descendants(c.children) for c in children)
