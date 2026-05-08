"""typer CLI: `hn item`, `hn search`, `hn top`. Thin shell over hn_cli.api."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import StrEnum

import typer

from hn_cli.api import get_item, get_top
from hn_cli.api import search as api_search
from hn_cli.errors import HNAPIError
from hn_cli.models import Story
from hn_cli.render import story_to_markdown

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)


class _Feed(StrEnum):
    top = "top"
    new = "new"
    best = "best"
    ask = "ask"
    show = "show"
    job = "job"


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


@app.command("search", help="Full-text search HN via Algolia.")
def cmd_search(
    query: str = typer.Argument(..., help="Search query."),
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
    _emit_list(stories, as_json=as_json)


@app.command("top", help="Front-page scan: fetch the top-stories feed in parallel.")
def cmd_top(
    limit: int = typer.Option(30, "--limit", "-n", help="Max stories to fetch."),
    min_score: int = typer.Option(None, "--min-score", help="Post-fetch score filter."),
    feed: _Feed = typer.Option(_Feed.top, "--feed", help="Alternate front-page feed."),
    concurrency: int = typer.Option(10, "--concurrency", help="Parallel item fetches."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSONL instead of markdown."),
) -> None:
    try:
        stories = get_top(
            limit=limit,
            min_score=min_score,
            feed=feed.value,
            concurrency=concurrency,
        )
    except (ValueError, HNAPIError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    _emit_list(stories, as_json=as_json)


def _emit_list(stories: list[Story], *, as_json: bool) -> None:
    if as_json:
        for s in stories:
            typer.echo(json.dumps(asdict(s), ensure_ascii=False))
        return
    for i, s in enumerate(stories, 1):
        typer.echo(_story_one_liner(s, i))


def _story_one_liner(s: Story, idx: int) -> str:
    tail = f"  {s.url}" if s.url else ""
    return f"{idx:>2}. {s.title}\n    {s.score} pts · {s.by} · {s.descendants}c · id {s.id}{tail}"


if __name__ == "__main__":  # pragma: no cover
    app()
