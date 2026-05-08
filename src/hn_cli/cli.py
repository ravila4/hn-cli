"""Hacker News for humans and agents — markdown by default, JSON on demand.

Read-only: fetches stories, comment trees, and search hits. No auth, no cache.
"""

from __future__ import annotations

import json
import webbrowser
from dataclasses import asdict
from enum import StrEnum

import typer

from hn_cli.api import get_item, get_top
from hn_cli.api import search as api_search
from hn_cli.errors import HNAPIError
from hn_cli.models import Story
from hn_cli.parsing import parse_item_id
from hn_cli.render import story_to_markdown

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help=__doc__,
    context_settings={"help_option_names": ["-h", "--help"]},
)


class _Sort(StrEnum):
    relevance = "relevance"
    date = "date"


@app.command("item", help="Fetch a story plus its comment tree.")
def cmd_item(
    id_or_url: str = typer.Argument(..., help="Item ID or news.ycombinator.com/item URL."),
    depth: int = typer.Option(3, "--depth", "-d", help="Max comment nesting depth shown."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of markdown."),
) -> None:
    try:
        story = get_item(id_or_url, depth=depth)
    except (ValueError, HNAPIError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    if as_json:
        typer.echo(json.dumps(asdict(story), ensure_ascii=False))
    else:
        typer.echo(story_to_markdown(story), nl=False)


@app.command("open", help="Open an HN item in the default web browser.")
def cmd_open(
    id_or_url: str = typer.Argument(..., help="Item ID or news.ycombinator.com/item URL."),
    story: bool = typer.Option(
        False,
        "--story",
        help="Open the linked article instead of the HN comment page (errors on self-posts).",
    ),
) -> None:
    try:
        item_id = parse_item_id(id_or_url)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    if not story:
        webbrowser.open(f"https://news.ycombinator.com/item?id={item_id}", new=2)
        return
    try:
        s = get_item(item_id, depth=0)
    except HNAPIError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    if not s.url:
        typer.echo(f"item {item_id} is a self-post; no external URL to open.", err=True)
        raise typer.Exit(1)
    webbrowser.open(s.url, new=2)


@app.command("search", help="Full-text search HN via Algolia.")
def cmd_search(
    query: str = typer.Argument(..., help="Search query (must be non-empty)."),
    min_score: int = typer.Option(None, "--min-score", help="Drop hits below this score."),
    min_comments: int = typer.Option(
        None, "--min-comments", help="Drop hits below this comment count."
    ),
    since: str = typer.Option(
        None, "--since", help="Only items newer than this duration (e.g. 7d, 24h, 1y)."
    ),
    limit: int = typer.Option(30, "--limit", "-n", help="Max hits to return."),
    sort: _Sort = typer.Option(_Sort.relevance, "--sort", help="Ranking strategy."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSONL instead of markdown."),
) -> None:
    try:
        stories = api_search(
            query,
            min_score=min_score,
            min_comments=min_comments,
            since=since,
            limit=limit,
            sort=sort.value,
        )
    except (ValueError, HNAPIError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    _emit_list(stories, as_json=as_json, kind="search")


def _run_feed(
    feed: str, *, limit: int, min_score: int | None, concurrency: int, as_json: bool
) -> None:
    try:
        stories = get_top(limit=limit, min_score=min_score, feed=feed, concurrency=concurrency)
    except (ValueError, HNAPIError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    _emit_list(stories, as_json=as_json, kind=feed)


@app.command("top", help="Front-page feed (topstories.json).")
def cmd_top(
    limit: int = typer.Option(30, "--limit", "-n", help="Max stories to fetch."),
    min_score: int = typer.Option(None, "--min-score", help="Post-fetch score filter."),
    concurrency: int = typer.Option(10, "--concurrency", help="Parallel item fetches."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSONL instead of markdown."),
) -> None:
    _run_feed("top", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


@app.command("new", help="Newest stories (newstories.json).")
def cmd_new(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(None, "--min-score"),
    concurrency: int = typer.Option(10, "--concurrency"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    _run_feed("new", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


@app.command("best", help="Highest-scoring recent stories (beststories.json).")
def cmd_best(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(None, "--min-score"),
    concurrency: int = typer.Option(10, "--concurrency"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    _run_feed("best", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


@app.command("ask", help="Ask HN feed (askstories.json).")
def cmd_ask(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(None, "--min-score"),
    concurrency: int = typer.Option(10, "--concurrency"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    _run_feed("ask", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


@app.command("show", help="Show HN feed (showstories.json).")
def cmd_show(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(None, "--min-score"),
    concurrency: int = typer.Option(10, "--concurrency"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    _run_feed("show", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


@app.command("jobs", help="Job postings (jobstories.json).")
def cmd_jobs(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(None, "--min-score"),
    concurrency: int = typer.Option(10, "--concurrency"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    _run_feed("job", limit=limit, min_score=min_score, concurrency=concurrency, as_json=as_json)


def _emit_list(stories: list[Story], *, as_json: bool, kind: str) -> None:
    if not stories:
        # Empty results aren't an error (the API call succeeded), but a silent
        # exit-0-with-no-output is indistinguishable from a broken call to an
        # agent. Surface a hint on stderr; stdout stays empty for `| jq` etc.
        typer.echo(f"No results from `hn {kind}` matching the given filters.", err=True)
        return
    if as_json:
        for s in stories:
            typer.echo(json.dumps(_listing_dict(s), ensure_ascii=False))
        return
    for i, s in enumerate(stories, 1):
        typer.echo(_story_one_liner(s, i))


def _listing_dict(s: Story) -> dict:
    """Drop comment-tree fields from feed/search rows (we never fetched them).

    `hn item` keeps `children: []` because there a story with zero comments
    is meaningfully different from "thread not fetched"; here it isn't.
    """
    d = asdict(s)
    d.pop("children", None)
    d.pop("truncated_replies", None)
    return d


def _story_one_liner(s: Story, idx: int) -> str:
    tail = f"  {s.url}" if s.url else ""
    return f"{idx:>2}. {s.title}\n    {s.score} pts · {s.by} · {s.descendants}c · id {s.id}{tail}"


if __name__ == "__main__":  # pragma: no cover
    app()
