"""Data model: Story and Comment dataclasses with normalizers.

A single shape per concept, populated from either the Firebase or Algolia
upstream representations. The dataclasses ARE the JSON schema (`asdict` →
JSON output); the markdown renderer is a separate serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Comment:
    """A single comment, possibly with nested children.

    `text` is HTML as returned by upstream — the renderer decodes it.
    `text == "[deleted]"` and `by is None` indicates a removed comment;
    we keep the node so consumers see structure, not silent gaps.
    `truncated_replies > 0` means descendants beyond the requested
    `--depth` were pruned client-side; consumers can re-fetch.
    """

    id: int
    by: str | None
    time: int
    text: str | None
    children: tuple[Comment, ...] = ()
    truncated_replies: int = 0

    @classmethod
    def from_algolia(cls, d: dict[str, Any]) -> Comment:
        author = d.get("author")
        text = d.get("text")
        # Algolia returns deleted/dead comments with author=None and text=None.
        # Surface as a placeholder so consumers can distinguish "no comment here"
        # from "structure exists but content is gone."
        # Algolia returns deleted/dead comments with author=None and text=None.
        # Surface a placeholder so consumers see structure-with-no-content rather
        # than a silent gap. Otherwise text is stored RAW (HTML with entities);
        # JSON serialization unescapes, the markdown renderer handles entities
        # via the parser. Decoding here would corrupt content like `&lt;div&gt;`
        # because the renderer would then misparse decoded `<` as a tag start.
        if author is None and text is None:
            text = "[deleted]"
        return cls(
            id=int(d["id"]),
            by=author,
            time=int(d.get("created_at_i", 0)),
            text=text,
            children=tuple(cls.from_algolia(c) for c in d.get("children") or ()),
        )


@dataclass(frozen=True)
class Story:
    """A Hacker News story. `children` is the comment tree (only populated
    when fetched via Algolia `items/{id}`); `descendants` is the comment
    count at fetch time.
    """

    id: int
    title: str
    url: str | None
    score: int
    by: str
    time: int
    descendants: int
    text: str | None = None
    children: tuple[Comment, ...] = field(default_factory=tuple)
    truncated_replies: int = 0

    @classmethod
    def from_algolia_item(cls, d: dict[str, Any]) -> Story:
        """Build from Algolia's `items/{id}` response (full thread)."""
        children = tuple(Comment.from_algolia(c) for c in d.get("children") or ())
        return cls(
            id=int(d["id"]),
            title=d.get("title") or "",
            url=d.get("url"),
            score=int(d.get("points") or 0),
            by=d.get("author") or "",
            time=int(d.get("created_at_i", 0)),
            # Algolia items/{id} doesn't return a top-level descendants count;
            # count the tree. May lag Firebase by minutes. Spec accepts the drift.
            descendants=_count_descendants(children),
            text=d.get("text"),
            children=children,
        )

    @classmethod
    def from_algolia_hit(cls, d: dict[str, Any]) -> Story:
        """Build from an Algolia `/search` hit (no comment tree)."""
        return cls(
            id=int(d["objectID"]),
            title=d.get("title") or "",
            url=d.get("url"),
            score=int(d.get("points") or 0),
            by=d.get("author") or "",
            time=int(d.get("created_at_i", 0)),
            descendants=int(d.get("num_comments") or 0),
            text=d.get("story_text"),
            children=(),
        )

    @classmethod
    def from_firebase(cls, d: dict[str, Any]) -> Story:
        """Build from a Firebase `item/{id}.json` response (no inlined tree)."""
        return cls(
            id=int(d["id"]),
            title=d.get("title") or "",
            url=d.get("url"),
            score=int(d.get("score") or 0),
            by=d.get("by") or "",
            time=int(d.get("time") or 0),
            descendants=int(d.get("descendants") or 0),
            text=d.get("text"),
            children=(),
        )


def _count_descendants(children: tuple[Comment, ...]) -> int:
    return sum(1 + _count_descendants(c.children) for c in children)
