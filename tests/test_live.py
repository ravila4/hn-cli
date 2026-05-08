"""Opt-in tests that hit the real Hacker News APIs.

These verify only structural invariants (keys present, types correct) — not
specific values, since live HN data drifts. Run with `uv run pytest -m live`.

The default test session excludes them via `addopts = "-m 'not live'"`.
"""

from __future__ import annotations

import pytest

from hn_cli import api

pytestmark = pytest.mark.live


def test_get_top_returns_stories():
    stories = api.get_top(limit=5)
    assert len(stories) > 0
    s = stories[0]
    assert isinstance(s.id, int) and s.id > 0
    assert isinstance(s.title, str) and s.title
    assert isinstance(s.score, int)
    assert isinstance(s.descendants, int)
    assert isinstance(s.by, str)


def test_get_top_best_feed():
    stories = api.get_top(limit=3, feed="best")
    assert len(stories) > 0


def test_search_returns_hits():
    results = api.search("python", limit=5)
    assert len(results) > 0
    assert all(s.id > 0 for s in results)
    assert all(isinstance(s.title, str) for s in results)


def test_get_item_with_comments():
    # Pull a top story and re-fetch it as a thread.
    top = api.get_top(limit=1)
    assert top, "expected at least one story"
    full = api.get_item(top[0].id, depth=2)
    assert full.id == top[0].id
    # Spec floor for the JSON schema:
    for field in ("id", "title", "url", "score", "by", "time", "descendants"):
        assert hasattr(full, field)
