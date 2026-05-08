---
name: hn-cli
description: Read-only Hacker News CLI and library. Use when triaging the HN front page, fetching a comment thread for a specific story (URL or ID), or running a full-text search with score/recency filters. Markdown for humans, JSON for piping or programmatic consumption.
---

# hn-cli

A small read-only tool for fetching and searching Hacker News. Two surfaces, same data:

- **CLI**: `hn <subcommand>` for shell or subprocess use
- **Library**: `from hn_cli import get_item, search, get_top` for in-process use

Output is markdown by default; `--json` emits structured data (single object for `hn item`, JSONL for everything else). Read-only — no auth, no commenting, no voting.

## When to use

- A `news.ycombinator.com/item?id=…` URL was pasted and you need the thread
- Quick triage of the HN front page ("anything interesting?")
- Full-text search with filters ("Rust posts in the last week with > 100 points")
- Pulling a comment tree as JSON for analysis or summarization

## Subcommands

| Subcommand | What it does | Source |
|---|---|---|
| `hn item <id-or-url>` | Story plus full comment tree | Algolia `items/{id}` |
| `hn search <query>` | Full-text search of stories | Algolia `search` |
| `hn top` | Front-page feed | Firebase `topstories.json` |
| `hn new` | Newest submissions | Firebase `newstories.json` |
| `hn best` | Highest-scoring recent stories | Firebase `beststories.json` |
| `hn ask` | Ask HN | Firebase `askstories.json` |
| `hn show` | Show HN | Firebase `showstories.json` |
| `hn jobs` | Job postings | Firebase `jobstories.json` |

All commands accept `-h` / `--help`.

## Common flags

- `--json` — emit JSON. Single object for `hn item`; JSONL (one object per line) for everything else.
- `-n / --limit N` — cap result count (default 30 for feeds and search).
- `--min-score N` — drop low-scoring results.
- `-d / --depth N` (item only) — max comment nesting depth (default 3). Beyond that, replies are pruned and reported via `truncated_replies` in JSON / `[N replies not shown]` in markdown.
- `--since DURATION` (search only) — filter to recent items. Duration strings: `30s`, `30m`, `24h`, `7d`, `2w`, `1y`. Case-insensitive. Strings — not integers.
- `--sort relevance|date` (search only) — Algolia ranking strategy.
- `--concurrency N` (feeds only) — bound parallel item fetches (default 10).

## Examples

```sh
# Triage the front page
hn top --limit 10
hn top --limit 30 --json | jq -c '{id, title, score}'

# Pull a thread by URL or ID
hn item https://news.ycombinator.com/item?id=48052537 --depth 2
hn item 48052537 --json > thread.json

# Search with filters
hn search "rust async" --min-score 100 --since 7d --limit 5
hn search "AI safety" --sort date --json
```

## Library use

```python
from hn_cli import get_item, search, get_top, Story, Comment, HNAPIError

story  = get_item(48052537, depth=2)
hits   = search("rust async", min_score=100, since="7d", limit=5)
front  = get_top(limit=30, min_score=50, feed="top")  # also: "new"|"best"|"ask"|"show"|"job"
```

Library kwargs match CLI flag names one-to-one (snake_case where flags use kebab-case). `since` is a duration string, never an integer day count. The library exposes `get_top(feed=…)` for all six feeds rather than separate functions; the CLI splits them into named subcommands purely for ergonomics.

## Output schema (when `--json`)

Story / search-hit / item objects always include:

| field | type |
|---|---|
| `id` | int |
| `title` | string |
| `url` | string \| null (null for self-posts) |
| `score` | int |
| `by` | string |
| `time` | int (Unix epoch seconds) |
| `descendants` | int (comment count at fetch time) |
| `text` | string \| null (HTML body for self-posts; null otherwise) |

`hn item` additionally includes:

| field | type |
|---|---|
| `children` | array of comment objects (each: `id`, `by`, `time`, `text`, `children`, `truncated_replies`) |
| `truncated_replies` | int (>0 if `--depth` pruned descendants at the root) |

`hn top|new|best|ask|show|jobs` and `hn search` **omit** `children` and `truncated_replies` because those commands never fetch the comment tree. Detect a missing `children` key as "thread not fetched, call `hn item <id>` to drill in."

`text` fields have HTML entities decoded (`&#x2F;` → `/`, `&#x27;` → `'`, `&amp;` → `&`) but tags are preserved as-is — strip or render to taste.

Deleted/dead comments appear in the tree with `text: "[deleted]"` and `by: null`, never silently dropped.

## Exit codes and errors

- **0** — success, including "no results matching filters" (which writes a hint to **stderr**; stdout stays clean for `| jq`).
- **1** — error. Bad input (`hn item not_a_number`, empty search query, malformed `--since`), HTTP non-2xx (`HNAPIError`), or a network failure. Message goes to stderr; no traceback.
- **2** — usage error (typer/click parse failure, e.g. unknown subcommand).

The library raises `ValueError` for parse errors and `hn_cli.HNAPIError` for HTTP failures. `HNAPIError` exposes `.status_code` and `.url` for branching (e.g. backoff on 429/503). The library does **not** retry — that decision belongs to the caller.

## Quirks

- **Empty search query is rejected.** Algolia returns all-time top stories on empty query, which is almost never what a caller wants.
- **`hn search` indexing lags Firebase** by minutes for new stories. Score and comment counts on the same item may differ between `hn search` (Algolia) and `hn item` (Algolia, slightly different index) and `hn top` (Firebase, real-time). Spec accepts the drift; don't try to reconcile.
- **No persistent cache.** Every invocation hits the API.
