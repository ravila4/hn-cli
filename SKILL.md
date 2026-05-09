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
| `hn open <id-or-url>` | Open in the default browser. `--story` opens the linked article instead of the HN comment page. | none (no fetch unless `--story`) |
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
- `--min-score N` — drop low-scoring results (search and feeds).
- `--min-comments N` (search only) — drop hits below this comment count (`descendants >= N`).
- `-d / --depth N` (item only) — max comment nesting depth (default 3). `--depth 0` returns story metadata + total descendant count without rendering or transferring the comment tree — use it to probe a thread's size before drilling in. The `depth_histogram` field (and its `Comments per depth: ...` markdown line) gives per-level counts so you can size the next fetch precisely. Replies beyond `--depth` are pruned and reported via `truncated_replies` (per-parent) and `truncated_total` (aggregated) in JSON, and `[N replies not shown]` in markdown.
- `--since DURATION` (search only) — filter to recent items. Duration strings: `30s`, `30m`, `24h`, `7d`, `2w`, `1y`. Case-insensitive. Strings — not integers.
- `--sort relevance|date` (search only) — Algolia ranking strategy.
- `--type story|ask|show|job` (search only) — filter by submission kind. Default `story` matches all non-job posts (including Ask/Show HN). `ask`/`show` narrow to those subtypes; `job` switches to the jobs tag.
- `--print-url` (open only) — print the URL to stdout instead of opening a browser. Pairs with `--story` to print the linked article URL.
- `--concurrency N` (feeds only) — bound parallel item fetches (default 10).

## Examples

```sh
# Triage the front page
hn top --limit 10
hn top --limit 30 --json | jq -c '{id, title, score, type}'

# Pull a thread by URL or ID (quote URLs in zsh — `?id=` is a glob)
hn item "https://news.ycombinator.com/item?id=48052537" --depth 2
hn item 48052537 --json > thread.json

# Probe a thread's size before pulling the full tree
hn item 48052537 --depth 0 --json | jq '.descendants'

# Search with filters
hn search "rust async" --min-score 100 --min-comments 50 --since 7d --limit 5
hn search "AI safety" --sort date --json
hn search "tokio" --type show --limit 10        # Show HN posts only

# Get the canonical HN URL for an item (no browser)
hn open 48052537 --print-url

# Strip HTML tags from any `text` field in a thread
hn item 48052537 --json | jq '.. | .text? // empty | gsub("<[^>]+>"; "")'

# Rank top-level threads by total subtree size (engagement proxy — see Quirks)
hn item 48052537 --json | jq '.children
  | map({id, by, replies: ([.. | objects | select(has("text"))] | length)})
  | sort_by(-.replies)
  | .[:5]'
```

## Library use

```python
from hn_cli import get_item, search, get_top, Story, Comment, HNAPIError

story  = get_item(48052537, depth=2)
hits   = search("rust async", min_score=100, min_comments=50, since="7d", limit=5)
shows  = search("tokio", type_="show")  # CLI `--type` maps to kwarg `type_`
front  = get_top(limit=30, min_score=50, feed="top")  # also: "new"|"best"|"ask"|"show"|"job"
```

Library kwargs match CLI flag names one-to-one (snake_case where flags use kebab-case). `--type` is `type_=` in Python — `type` is a builtin, so the kwarg gets a trailing underscore. `since` is a duration string, never an integer day count. The library exposes `get_top(feed=…)` for all six feeds rather than separate functions; the CLI splits them into named subcommands purely for ergonomics.

## Output schema (when `--json`)

Story / search-hit / item objects always include:

| field | type | notes |
|---|---|---|
| `id` | int | HN canonical item ID |
| `title` | string | |
| `url` | string \| null | null for self-posts (Ask/Show/job posts may also be null) |
| `score` | int | upvote score at fetch time |
| `by` | string | author handle |
| `time` | int | Unix epoch seconds |
| `descendants` | int | comment count at fetch time |
| `type` | string | one of `story`, `ask`, `show`, `job` |

Self-post-only field (present when upstream provides it; absent on link posts and Firebase-feed listings):

| field | type | notes |
|---|---|---|
| `text` | string | HTML body. JSON output entity-decodes (e.g. `&#x27;` → `'`) but preserves tags. |

`hn item` additionally includes (these are NEVER present in feed/search output, since those commands don't fetch the tree):

| field | type | notes |
|---|---|---|
| `children` | array | each child: `id`, `by`, `time`, `text`, `children`, `truncated_replies` |
| `truncated_replies` | int | `>0` only when `--depth` pruned descendants directly at the root (i.e. `--depth 0`) |
| `truncated_total` | int | count of descendants pruned by `--depth`. Pure depth accounting — does **not** include comments Algolia simply didn't return. To check for upstream gaps, compare `descendants` to `returned + truncated_total` where `returned = [.. \| objects \| select(has("text"))] \| length`; a gap larger than ±2 means Algolia returned a sparse tree and bumping `--depth` won't help (refetch instead). |
| `depth_histogram` | array of int | per-level comment counts in the *full* tree (`[0]` = top-level, `[1]` = direct replies, etc.). Survives `--depth` truncation, so a cheap `--depth 0` probe tells you exactly how many comments a re-fetch at depth N would render — sum the first N entries. |

`hn top|new|best|ask|show|jobs` and `hn search` **omit** `children`, `truncated_replies`, `truncated_total`, and `depth_histogram`. Detect a missing `children` key as "thread not fetched, call `hn item <id>` to drill in."

In **JSON output**, `text` fields have HTML entities decoded (`&#x2F;` → `/`, `&#x27;` → `'`, `&amp;` → `&`) but tags are preserved as-is — strip or render to taste. Library callers reading `Story.text` / `Comment.text` directly see **raw HTML** with entities intact; decode with `html.unescape()` if needed. The split is deliberate: decoding before passing through the markdown renderer corrupts content that legitimately contains escaped HTML special chars (`&lt;div&gt;`).

Deleted/dead comments appear in the tree with `text: "[deleted]"` and `by: null`, never silently dropped.

## Exit codes and errors

- **0** — success, including "no results matching filters" (which writes a hint to **stderr**; stdout stays clean for `| jq`).
- **1** — error. Bad input (`hn item not_a_number`, empty search query, malformed `--since`), HTTP non-2xx (`HNAPIError`), or a network failure. Message goes to stderr; no traceback.
- **2** — usage error (typer/click parse failure, e.g. unknown subcommand).

The library raises `ValueError` for parse errors and `hn_cli.HNAPIError` for HTTP failures. `HNAPIError` exposes `.status_code` and `.url` for branching (e.g. backoff on 429/503). The library does **not** retry — that decision belongs to the caller.

## Quirks

- **Empty results go to stderr, not stdout.** When a query/filter yields zero hits, exit code is `0` and stdout is empty (so `| jq` doesn't choke on garbage). The "no results" hint is on **stderr**. Pipelines that pipe straight to `jq` will silently see zero JSON lines on empty — check the exit code or merge streams (`2>&1 | …`) if you need to disambiguate from a network truncation.
- **Empty search query is rejected.** Algolia returns all-time top stories on empty query, which is almost never what a caller wants.
- **No per-comment scores.** Algolia's `items/{id}` payload omits per-comment points. Reply count and text length are the available proxies for engagement; don't treat them as quality signals. To rank top-level threads by engagement, count the *whole subtree* (`[.. | objects | select(has("text"))] | length`) — `.children | length` only counts direct replies and will mis-rank long single-thread debates as low-engagement. Note: subtree size measures **controversy / engagement**, not agreement — a comment everyone silently upvotes looks identical to one that triggered a 50-reply argument. Per-comment scores would require N+1 Firebase fetches, which defeats the killer single-call thread fetch.
- **`descendants` is HN's count, ±1–2 from actual.** HN's reported `descendants` may differ slightly from the comment objects Algolia returns — likely deleted/dead-comment accounting. Treat `descendants` as approximate; for exact in-payload counts use `[.. | objects | select(has("text"))] | length`.
- **Algolia sparse-tree on cold fetches.** Algolia occasionally returns a partial comment tree (e.g. 30 of 281 comments) on the first call to a popular thread; `descendants` still reports the true count, so the tree is shorter than it claims. Cross-check `descendants` against actual comment count (`[.. | objects | select(has("text"))] | length`); refetch if they disagree. The library does not auto-retry — caller decides.
- **Search matches title + body + url.** Algolia full-text-searches all three fields, so `hn search "rust"` will surface posts whose URL or body mentions Rust even if the title doesn't. Filter client-side with `jq 'select(.title | test("rust"; "i"))'` if you need title-only matches.
- **Quote URLs in zsh.** `news.ycombinator.com/item?id=…` contains `?` which zsh treats as a glob — quote the URL or it'll fail with "no matches found" before `hn` ever runs.
- **Feed ordering is HN's native ranking, unbounded.** `hn new` / `hn ask` / `hn show` / `hn jobs` are recency-ordered (newest first). `hn top` / `hn best` use HN's score+age decay. There's no `--since` flag on feeds — narrow the window with `--limit`, or use `hn search --type ask|show --since 7d` if you need a time-bounded subset.
- **`hn search` indexing lags Firebase** by minutes for new stories. Score and comment counts on the same item may differ between `hn search` (Algolia) and `hn item` (Algolia, slightly different index) and `hn top` (Firebase, real-time). Spec accepts the drift; don't try to reconcile.
- **No persistent cache.** Every invocation hits the API.
- **Sync-only library.** `get_item`, `search`, and `get_top` use `asyncio.run` internally. Calling them from inside a running event loop (Jupyter, FastAPI handlers, async agent frameworks like LangChain/CrewAI) raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. Workaround: subprocess the CLI (`hn item …`) instead of importing the library, or run the call in a worker thread.
