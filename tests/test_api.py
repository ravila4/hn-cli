"""Tests for the public sync API in hn_cli.api.

These exercise both the async internals (via respx) and the sync wrappers.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from hn_cli import api
from hn_cli.errors import HNAPIError

FIREBASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA = "https://hn.algolia.com/api/v1"


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


# -- get_item ----------------------------------------------------------------


def test_get_item_by_int_id(mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    s = api.get_item(42, depth=10)
    assert s.id == 42
    assert s.descendants == 3
    assert len(s.children) == 2


def test_get_item_by_url(mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    s = api.get_item("https://news.ycombinator.com/item?id=42")
    assert s.id == 42


def test_get_item_truncates_tree(mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    s = api.get_item(42, depth=1)
    # Top-level kept, their replies pruned with truncated_replies set on parents.
    assert len(s.children) == 2
    assert s.children[0].children == ()
    # Comment id 43 had one child (44) → truncated_replies should be 1.
    assert s.children[0].truncated_replies == 1


def test_get_item_invalid_input_raises_value_error():
    with pytest.raises(ValueError):
        api.get_item("not_a_number")


def test_get_item_propagates_hnapierror(mock):
    mock.get(f"{ALGOLIA}/items/9999").mock(return_value=httpx.Response(404))
    with pytest.raises(HNAPIError):
        api.get_item(9999)


# -- search ------------------------------------------------------------------


def test_search_returns_stories(mock, algolia_search_rust):
    mock.get(f"{ALGOLIA}/search").mock(return_value=httpx.Response(200, json=algolia_search_rust))
    results = api.search("rust async")
    assert len(results) == 2
    assert results[0].id == 200
    assert results[0].score == 250
    assert results[1].id == 201


def test_search_passes_filters(mock, algolia_search_rust):
    route = mock.get(f"{ALGOLIA}/search").mock(
        return_value=httpx.Response(200, json=algolia_search_rust)
    )
    api.search("rust", min_score=100, min_comments=10, limit=5)
    sent = str(route.calls[0].request.url)
    assert "hitsPerPage=5" in sent
    # numericFilters value gets URL-encoded
    assert "points" in sent and "100" in sent
    assert "num_comments" in sent and "10" in sent


def test_search_since_adds_time_filter(mock, algolia_search_rust):
    route = mock.get(f"{ALGOLIA}/search").mock(
        return_value=httpx.Response(200, json=algolia_search_rust)
    )
    api.search("rust", since="7d")
    sent = str(route.calls[0].request.url)
    assert "created_at_i" in sent


def test_search_by_date_uses_search_by_date_endpoint(mock, algolia_search_rust):
    route = mock.get(f"{ALGOLIA}/search_by_date").mock(
        return_value=httpx.Response(200, json=algolia_search_rust)
    )
    api.search("rust", sort="date")
    assert route.called


# -- get_top -----------------------------------------------------------------


def test_get_top_fetches_ids_then_items(mock, firebase_topstories, firebase_item_42):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid})
        )
    stories = api.get_top(limit=3)
    assert {s.id for s in stories} == set(firebase_topstories)


def test_get_top_filters_by_min_score(mock, firebase_topstories):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    scores = {42: 200, 100: 50, 200: 10}
    for sid, score in scores.items():
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": sid,
                    "by": "x",
                    "title": "t",
                    "url": "https://x",
                    "score": score,
                    "time": 0,
                    "descendants": 0,
                    "type": "story",
                },
            )
        )
    stories = api.get_top(limit=3, min_score=100)
    assert len(stories) == 1
    assert stories[0].id == 42


def test_get_top_uses_feed_kwarg(mock, firebase_topstories, firebase_item_42):
    route = mock.get(f"{FIREBASE}/beststories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid})
        )
    api.get_top(limit=3, feed="best")
    assert route.called


def test_get_top_skips_malformed_firebase_payload(mock, firebase_topstories, firebase_item_42):
    # Firebase occasionally returns partial data during replication lag — a row
    # with missing required keys must not abort the whole feed.
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    mock.get(f"{FIREBASE}/item/42.json").mock(
        return_value=httpx.Response(200, json={**firebase_item_42, "id": 42})
    )
    mock.get(f"{FIREBASE}/item/100.json").mock(
        return_value=httpx.Response(200, json={"by": "x"})  # missing id, title, etc.
    )
    mock.get(f"{FIREBASE}/item/200.json").mock(
        return_value=httpx.Response(200, json={**firebase_item_42, "id": 200})
    )
    stories = api.get_top(limit=3)
    assert {s.id for s in stories} == {42, 200}


def test_get_top_skips_failed_items(mock, firebase_topstories, firebase_item_42):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    mock.get(f"{FIREBASE}/item/42.json").mock(
        return_value=httpx.Response(200, json={**firebase_item_42, "id": 42})
    )
    mock.get(f"{FIREBASE}/item/100.json").mock(return_value=httpx.Response(404))
    mock.get(f"{FIREBASE}/item/200.json").mock(
        return_value=httpx.Response(200, json={**firebase_item_42, "id": 200})
    )
    stories = api.get_top(limit=3)
    # 100 was a 404; should be silently dropped, not crash the listing.
    assert {s.id for s in stories} == {42, 200}
