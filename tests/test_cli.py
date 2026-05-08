"""End-to-end CLI tests via typer's CliRunner. respx mocks the HTTP layer."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hn_cli.cli import app

FIREBASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA = "https://hn.algolia.com/api/v1"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


# -- hn item -----------------------------------------------------------------


def test_item_markdown(runner, mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    res = runner.invoke(app, ["item", "42"])
    assert res.exit_code == 0
    assert "A test story" in res.stdout
    assert "## Comments" in res.stdout


def test_item_json_emits_single_object(runner, mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    res = runner.invoke(app, ["item", "42", "--json"])
    assert res.exit_code == 0
    obj = json.loads(res.stdout.strip())
    assert obj["id"] == 42
    assert obj["title"] == "A test story"
    assert isinstance(obj["children"], list)
    # `hn item` always carries the comment-tree fields, even when empty,
    # because absence here would conflate "thread fetched, no comments" with
    # the listing-command shape that drops them entirely.
    assert "truncated_replies" in obj


def test_item_depth_truncates(runner, mock, algolia_item_42):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    res = runner.invoke(app, ["item", "42", "--depth", "1", "--json"])
    obj = json.loads(res.stdout.strip())
    # Top-level kept, replies pruned.
    assert obj["children"][0]["children"] == []
    assert obj["children"][0]["truncated_replies"] == 1


def test_item_invalid_input_exits_1(runner):
    res = runner.invoke(app, ["item", "not_a_number"])
    assert res.exit_code == 1
    assert res.stdout == ""  # error went to stderr
    assert "not_a_number" in res.stderr or "could not parse" in res.stderr


def test_item_http_error_exits_1(runner, mock):
    mock.get(f"{ALGOLIA}/items/9999").mock(return_value=httpx.Response(503))
    res = runner.invoke(app, ["item", "9999"])
    assert res.exit_code == 1
    assert "503" in res.stderr


# -- hn search ---------------------------------------------------------------


def test_search_markdown_list(runner, mock, algolia_search_rust):
    mock.get(f"{ALGOLIA}/search").mock(return_value=httpx.Response(200, json=algolia_search_rust))
    res = runner.invoke(app, ["search", "rust async"])
    assert res.exit_code == 0
    assert "Rust async runtime comparison" in res.stdout
    assert "Tokio vs async-std" in res.stdout


def test_search_jsonl(runner, mock, algolia_search_rust):
    mock.get(f"{ALGOLIA}/search").mock(return_value=httpx.Response(200, json=algolia_search_rust))
    res = runner.invoke(app, ["search", "rust", "--json"])
    assert res.exit_code == 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == 200
    assert json.loads(lines[1])["id"] == 201


def test_search_passes_filters(runner, mock, algolia_search_rust):
    route = mock.get(f"{ALGOLIA}/search").mock(
        return_value=httpx.Response(200, json=algolia_search_rust)
    )
    runner.invoke(app, ["search", "rust", "--min-score", "100", "--limit", "5"])
    sent = str(route.calls[0].request.url)
    assert "hitsPerPage=5" in sent
    assert "100" in sent


def test_search_bad_since_exits_1(runner):
    res = runner.invoke(app, ["search", "rust", "--since", "garbage"])
    assert res.exit_code == 1
    assert "duration" in res.stderr.lower() or "invalid" in res.stderr.lower()


# -- hn top ------------------------------------------------------------------


def test_top_markdown(runner, mock, firebase_topstories, firebase_item_42):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid})
        )
    res = runner.invoke(app, ["top", "--limit", "3"])
    assert res.exit_code == 0
    # Three numbered entries.
    assert " 1." in res.stdout
    assert " 2." in res.stdout
    assert " 3." in res.stdout


def test_top_jsonl(runner, mock, firebase_topstories, firebase_item_42):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid})
        )
    res = runner.invoke(app, ["top", "--limit", "3", "--json"])
    assert res.exit_code == 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        # Listing commands strip the unused tree fields.
        assert "children" not in obj
        assert "truncated_replies" not in obj


@pytest.mark.parametrize(
    "subcmd, feed_file",
    [
        ("new", "newstories.json"),
        ("best", "beststories.json"),
        ("ask", "askstories.json"),
        ("show", "showstories.json"),
        ("jobs", "jobstories.json"),
    ],
)
def test_feed_subcommands_route_correctly(
    runner, mock, firebase_topstories, firebase_item_42, subcmd, feed_file
):
    route = mock.get(f"{FIREBASE}/{feed_file}").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid})
        )
    res = runner.invoke(app, [subcmd, "--limit", "3"])
    assert res.exit_code == 0, res.stderr
    assert route.called


def test_short_help_flag_works(runner):
    # `-h` should be an alias for `--help` at both top-level and per-command.
    top = runner.invoke(app, ["-h"])
    assert top.exit_code == 0
    assert "Usage:" in top.stdout

    sub = runner.invoke(app, ["item", "-h"])
    assert sub.exit_code == 0
    assert "Usage:" in sub.stdout


# -- empty-results stderr (#1) -----------------------------------------------


def test_search_empty_results_writes_stderr(runner, mock):
    mock.get(f"{ALGOLIA}/search").mock(return_value=httpx.Response(200, json={"hits": []}))
    res = runner.invoke(app, ["search", "asdfqwerzxcv"])
    assert res.exit_code == 0
    assert res.stdout == ""
    assert "no results" in res.stderr.lower()


def test_top_empty_after_min_score_filter(runner, mock, firebase_topstories, firebase_item_42):
    mock.get(f"{FIREBASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=firebase_topstories)
    )
    for sid in firebase_topstories:
        mock.get(f"{FIREBASE}/item/{sid}.json").mock(
            return_value=httpx.Response(200, json={**firebase_item_42, "id": sid, "score": 1})
        )
    res = runner.invoke(app, ["top", "--min-score", "999"])
    assert res.exit_code == 0
    assert res.stdout == ""
    assert "no results" in res.stderr.lower()


# -- empty-query rejection (#2) ----------------------------------------------


def test_search_empty_query_rejected(runner):
    res = runner.invoke(app, ["search", ""])
    assert res.exit_code == 1
    assert "empty" in res.stderr.lower()


def test_search_whitespace_query_rejected(runner):
    res = runner.invoke(app, ["search", "   "])
    assert res.exit_code == 1
    assert "empty" in res.stderr.lower()


# -- hn open -----------------------------------------------------------------


def test_open_defaults_to_hn_comment_page(runner, monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr("hn_cli.cli.webbrowser.open", lambda url, new=0: captured.append(url))
    res = runner.invoke(app, ["open", "48052537"])
    assert res.exit_code == 0
    assert captured == ["https://news.ycombinator.com/item?id=48052537"]


def test_open_accepts_url_input(runner, monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr("hn_cli.cli.webbrowser.open", lambda url, new=0: captured.append(url))
    res = runner.invoke(app, ["open", "https://news.ycombinator.com/item?id=42"])
    assert res.exit_code == 0
    assert captured == ["https://news.ycombinator.com/item?id=42"]


def test_open_story_opens_linked_article(runner, mock, algolia_item_42, monkeypatch):
    mock.get(f"{ALGOLIA}/items/42").mock(return_value=httpx.Response(200, json=algolia_item_42))
    captured: list[str] = []
    monkeypatch.setattr("hn_cli.cli.webbrowser.open", lambda url, new=0: captured.append(url))
    res = runner.invoke(app, ["open", "42", "--story"])
    assert res.exit_code == 0
    assert captured == ["https://example.com/foo"]


def test_open_story_errors_on_self_post(runner, mock, algolia_item_ask_hn, monkeypatch):
    mock.get(f"{ALGOLIA}/items/100").mock(
        return_value=httpx.Response(200, json=algolia_item_ask_hn)
    )
    monkeypatch.setattr(
        "hn_cli.cli.webbrowser.open",
        lambda *_a, **_k: pytest.fail("should not open browser on self-post"),
    )
    res = runner.invoke(app, ["open", "100", "--story"])
    assert res.exit_code == 1
    assert "self-post" in res.stderr.lower() or "no url" in res.stderr.lower()


def test_item_json_unescapes_text_fields(runner, mock):
    # JSON consumers should see decoded text — entities are noise to them.
    # Library callers (Story.text) still see raw HTML; the conversion is
    # applied at the JSON serialization step, not at the model boundary.
    payload = {
        "id": 99,
        "created_at_i": 0,
        "type": "story",
        "author": "x",
        "title": "t",
        "url": None,
        "text": "<p>see https:&#x2F;&#x2F;example.com</p>",
        "points": 1,
        "children": [
            {
                "id": 1,
                "type": "comment",
                "author": "y",
                "created_at_i": 0,
                "text": "don&#x27;t",
                "children": [],
            }
        ],
    }
    mock.get(f"{ALGOLIA}/items/99").mock(return_value=httpx.Response(200, json=payload))
    res = runner.invoke(app, ["item", "99", "--json"])
    assert res.exit_code == 0
    obj = json.loads(res.stdout.strip())
    assert "https://example.com" in obj["text"]
    assert "&#x2F;" not in obj["text"]
    assert obj["children"][0]["text"] == "don't"


def test_top_json_unescapes_text(runner, mock, firebase_topstories):
    mock.get(f"{FIREBASE}/topstories.json").mock(return_value=httpx.Response(200, json=[42]))
    mock.get(f"{FIREBASE}/item/42.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "by": "x",
                "title": "Ask HN",
                "score": 1,
                "time": 0,
                "descendants": 0,
                "text": "<p>visit https:&#x2F;&#x2F;example.com</p>",
                "type": "story",
            },
        )
    )
    res = runner.invoke(app, ["top", "--limit", "1", "--json"])
    assert res.exit_code == 0
    obj = json.loads(res.stdout.strip())
    assert "https://example.com" in obj["text"]


def test_open_invalid_id_exits_1(runner, monkeypatch):
    monkeypatch.setattr(
        "hn_cli.cli.webbrowser.open",
        lambda *_a, **_k: pytest.fail("should not open browser on bad id"),
    )
    res = runner.invoke(app, ["open", "not_a_number"])
    assert res.exit_code == 1
    assert res.stderr
