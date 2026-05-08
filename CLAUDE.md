# CLAUDE.md

Specification for `hn-cli`. This file is the contract; implementation must conform.

## What this is

A standalone Python package shipping (a) a CLI for fetching and searching Hacker News content and (b) a library API exposing the same functionality to other Python projects. Output is human-readable markdown by default, structured JSON when requested. Read-only, no auth, no persistent cache.

## Output requirements

- **Default**: markdown to stdout. Story metadata as a header block, body as prose, comments as nested sections or bullets.
- **`--json` flag**: structured JSON. Single object for `hn item`; JSONL (one object per line) for `hn search` and `hn top`.
- All commands MUST support both formats.

## API endpoints

Two upstream APIs, used in different roles:

- **Firebase** — `https://hacker-news.firebaseio.com/v0/` — canonical, real-time, public, no auth.
  - `topstories.json` — array of up to 500 ranked story IDs
  - `item/{id}.json` — single story or comment by ID
  - Alt feeds: `newstories.json`, `beststories.json`, `askstories.json`, `showstories.json`, `jobstories.json`
  - `maxitem.json` — highest current item ID
- **Algolia HN Search** — `https://hn.algolia.com/api/v1/` — search + full-thread fetch, public, no auth, slight indexing lag.
  - `search?query=…&tags=story` — full-text search, ranked by relevance
  - `search_by_date?…` — same, ranked by recency
  - `items/{id}` — story plus the entire comment tree inlined in one response (the killer endpoint vs Firebase's per-item walk)

**Routing rule**: Firebase for the canonical front-page feed; Algolia for everything else (search, full-thread fetch).

## Features

- **`hn item <url-or-id>`** — fetch a story plus its comment tree.
  - Accepts an integer ID or a full `news.ycombinator.com/item?id=…` URL.
  - Uses Algolia `items/{id}` for the one-shot thread fetch (one HTTP call instead of N+1 against Firebase).
  - `--depth N` truncates nested replies (default 3). Replies beyond the depth are replaced with a single `[N replies not shown]` line per parent — never silently dropped.

- **`hn search <query>`** — Algolia search.
  - Flags: `--min-score`, `--min-comments`, `--since <duration>` (e.g. `7d`, `24h`), `--limit`.
  - Returns ranked story metadata. No comments — call `hn item <id>` on a hit if you want the thread.

- **`hn top`** — Firebase `topstories.json` followed by parallel item fetches.
  - Flags: `--limit` (default 30), `--min-score` (post-fetch filter).
  - Implementation MUST bound concurrency (semaphore or batched gather). Naive `asyncio.gather` over 500 IDs will get rate-limited.

## Error handling

- **Library layer**: invalid input to `get_item` (unparseable ID/URL) raises `ValueError`. Non-200 from either Firebase or Algolia raises `HNAPIError(status_code, url)`.
- **CLI layer**: catches both, prints to stderr, exits 1. No tracebacks bubble to the user.
- **No automatic retry.** Both APIs are public and stable enough that a silent retry loop costs more (mid-session hangs in agent contexts) than it saves. Caller decides whether to retry.

## JSON output schema

When `--json` is set, story-item objects MUST include at minimum:

| Field | Type | Source |
|---|---|---|
| `id` | int | HN canonical item ID |
| `title` | string | story title |
| `url` | string \| null | external URL; null for self-posts (Ask HN, etc.) |
| `score` | int | upvote score at fetch time |
| `by` | string | author handle |
| `time` | int | Unix epoch seconds (HN's native format) |
| `descendants` | int | comment count at fetch time |

The comment tree, when present, is nested under `children`. Each child carries at minimum `id`, `by`, `time`, `text`, and its own `children`.

Implementation MAY add fields. It MUST NOT remove these — they are the floor for any consumer.

## Library API

`hn-cli` ships as a Python package, not just a script. The CLI is a thin wrapper around a library API so other projects can `pip install` and call it directly.

- **Importable name**: `hn_cli` (hyphen converts to underscore by Python convention).
- **Public surface**: `get_item`, `search`, `get_top`. Signatures should mirror the CLI flags one-to-one.
- The dataclasses returned by these functions MUST be the same objects that the JSON schema above describes — one source of truth, two serializations.

Exact dataclass shapes and function signatures are deferred to the implementation session, but they are bound by this spec.

## Non-requirements

Explicit YAGNI list. Do not add these without revisiting the spec.

- No persistent cache. Each invocation hits the API fresh.
- No authentication. Both APIs are public.
- No write operations (commenting, voting, posting). Read-only.
- No comment-by-author indexing or other secondary queries beyond what Algolia exposes natively.
- Algolia indexing may lag Firebase by minutes to hours for new stories and comment counts. This drift is acceptable; do not paper over it with reconciliation logic.
