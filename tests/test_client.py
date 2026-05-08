"""Tests for HNClient using respx-mocked httpx."""

from __future__ import annotations

import httpx
import pytest
import respx

from hn_cli.client import HNClient
from hn_cli.errors import HNAPIError

FIREBASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA = "https://hn.algolia.com/api/v1"


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


async def test_get_topstories_ids(mock):
    mock.get(f"{FIREBASE}/topstories.json").mock(return_value=httpx.Response(200, json=[1, 2, 3]))
    async with HNClient() as c:
        assert await c.get_topstories_ids() == [1, 2, 3]


async def test_feed_routes_to_correct_filename(mock):
    mock.get(f"{FIREBASE}/beststories.json").mock(return_value=httpx.Response(200, json=[10, 11]))
    async with HNClient() as c:
        assert await c.get_topstories_ids("best") == [10, 11]


async def test_unknown_feed_raises_value_error():
    async with HNClient() as c:
        with pytest.raises(ValueError):
            await c.get_topstories_ids("bogus")


async def test_user_agent_header_set(mock):
    route = mock.get(f"{FIREBASE}/topstories.json").mock(return_value=httpx.Response(200, json=[]))
    async with HNClient() as c:
        await c.get_topstories_ids()
    sent = route.calls[0].request.headers.get("user-agent", "")
    assert sent.startswith("hn-cli/")


async def test_custom_user_agent(mock):
    route = mock.get(f"{FIREBASE}/topstories.json").mock(return_value=httpx.Response(200, json=[]))
    async with HNClient(user_agent="agent-bot/1.0") as c:
        await c.get_topstories_ids()
    assert route.calls[0].request.headers["user-agent"] == "agent-bot/1.0"


async def test_get_thread_algolia(mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    async with HNClient() as c:
        data = await c.get_thread_algolia(42)
        assert data["id"] == 42


async def test_search_algolia_passes_query_and_filters(mock):
    route = mock.get(f"{ALGOLIA}/search").mock(return_value=httpx.Response(200, json={"hits": []}))
    async with HNClient() as c:
        await c.search_algolia(
            "rust",
            numeric_filters=["points>=100", "num_comments>=10"],
            limit=5,
        )
    req = route.calls[0].request
    assert "query=rust" in str(req.url)
    assert "tags=story" in str(req.url)
    assert "hitsPerPage=5" in str(req.url)
    assert "points%3E%3D100" in str(req.url) or "points>=100" in str(req.url)


async def test_search_by_date_endpoint(mock):
    route = mock.get(f"{ALGOLIA}/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    async with HNClient() as c:
        await c.search_algolia("rust", sort="date")
    assert route.called


async def test_non_200_raises_hnapierror(mock):
    mock.get(f"{ALGOLIA}/items/999").mock(return_value=httpx.Response(503, text="upstream busy"))
    async with HNClient() as c:
        with pytest.raises(HNAPIError) as exc_info:
            await c.get_thread_algolia(999)
        assert exc_info.value.status_code == 503
        assert "items/999" in exc_info.value.url


async def test_firebase_null_for_missing_item_raises(mock):
    # Firebase returns a literal JSON `null` (not an empty body) for unknown items.
    mock.get(f"{FIREBASE}/item/9999.json").mock(
        return_value=httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )
    )
    async with HNClient() as c:
        with pytest.raises(HNAPIError) as exc_info:
            await c.get_item_firebase(9999)
        assert exc_info.value.status_code == 404


async def test_network_error_wrapped_in_hnapierror(mock):
    mock.get(f"{ALGOLIA}/items/1").mock(side_effect=httpx.ConnectError("boom"))
    async with HNClient() as c:
        with pytest.raises(HNAPIError) as exc_info:
            await c.get_thread_algolia(1)
        assert exc_info.value.status_code == 0
        assert "boom" in exc_info.value.message
