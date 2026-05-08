# hn-cli

A small CLI and Python library for fetching and searching Hacker News. Reads stories and comment threads from the official Firebase API and Algolia HN Search; emits markdown by default and JSON on demand.

## Install

```sh
uv tool install /Users/ravila/Projects/hn-cli
```

## Usage

```sh
# Fetch a story and its comment tree
hn item https://news.ycombinator.com/item?id=48052537
hn item 48052537 --depth 2

# Search HN with score and comment thresholds
hn search "rust async" --min-score 100 --min-comments 30 --since 7d

# Front-page scan
hn top --limit 30 --min-score 50
```

Add `--json` to any command for structured output suitable for piping to `jq` or another program.

## Library use

```python
from hn_cli import get_item, search, get_top

story = get_item(48052537)
hits = search("rust async", min_score=100, min_comments=30)
front = get_top(limit=30, min_score=50)
```

## Status

Specification only. See `CLAUDE.md` for the contract; implementation lands in a follow-up pass.
