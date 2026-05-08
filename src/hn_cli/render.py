"""Markdown rendering for stories and comment trees.

Two layers:
  - `html_to_markdown` decodes HN comment HTML (a narrow subset: <p>, <a>,
    <i>, <b>, <code>, <pre>) into markdown.
  - `story_to_markdown` / `comment_to_markdown` build the final output —
    story header, optional self-post body, then nested comments.

We deliberately do not pull in `html2text`: HN's HTML is small and well-known,
and `html2text` brings reflow heuristics that fight us.
"""

from __future__ import annotations

import time
from html.parser import HTMLParser

from hn_cli.models import Comment, Story


def html_to_markdown(html: str) -> str:
    """Convert HN comment HTML to markdown. Returns empty string on empty input."""
    if not html:
        return ""
    p = _HNHTMLParser()
    p.feed(html)
    p.close()
    return "".join(p.parts).strip()


class _HNHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._in_pre = False
        self._href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self.parts.append("\n\n")
        elif tag == "a":
            href = dict(attrs).get("href")
            self._href_stack.append(href)
            if href:
                self.parts.append("[")
        elif tag == "i" or tag == "em":
            self.parts.append("_")
        elif tag == "b" or tag == "strong":
            self.parts.append("**")
        elif tag == "pre":
            self._in_pre = True
            self.parts.append("\n\n```\n")
        elif tag == "code" and not self._in_pre:
            self.parts.append("`")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            href = self._href_stack.pop() if self._href_stack else None
            if href:
                self.parts.append(f"]({href})")
            # else: anchor text already emitted as data; nothing to close.
        elif tag == "i" or tag == "em":
            self.parts.append("_")
        elif tag == "b" or tag == "strong":
            self.parts.append("**")
        elif tag == "pre":
            self._in_pre = False
            self.parts.append("\n```\n\n")
        elif tag == "code" and not self._in_pre:
            self.parts.append("`")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


_INDENT = "  "


def _replies(n: int) -> str:
    return f"{n} reply" if n == 1 else f"{n} replies"


def story_to_markdown(s: Story, *, now: int | None = None) -> str:
    """Render a Story (with optional comment tree) to markdown."""
    n = _now(now)
    lines: list[str] = []
    lines.append(f"# {s.title}")
    lines.append("")
    meta = (
        f"**{s.score} points** · {s.by} · {_time_ago(s.time, n)} · "
        f"{s.descendants} comments · id {s.id}"
    )
    lines.append(meta)
    if s.url:
        lines.append("")
        lines.append(s.url)
    if s.text:
        body = html_to_markdown(s.text)
        if body:
            lines.append("")
            lines.append(body)
    if s.children or s.truncated_replies:
        lines.append("")
        lines.append("## Comments")
        lines.append("")
        for c in s.children:
            lines.append(comment_to_markdown(c, depth=0, now=n))
        if s.truncated_replies:
            lines.append(f"_[{_replies(s.truncated_replies)} not shown]_")
    return "\n".join(lines).rstrip() + "\n"


def comment_to_markdown(c: Comment, *, depth: int = 0, now: int | None = None) -> str:
    """Render a single comment (and its descendants) as a nested markdown bullet."""
    n = _now(now)
    pad = _INDENT * depth
    lines: list[str] = []
    if c.by is None and c.text == "[deleted]":
        lines.append(f"{pad}- _[deleted]_")
    else:
        header = f"{pad}- **{c.by or '[deleted]'}** · {_time_ago(c.time, n)}"
        lines.append(header)
        body = html_to_markdown(c.text or "")
        if body:
            for body_line in body.splitlines() or [""]:
                if body_line.strip():
                    lines.append(f"{pad}{_INDENT}> {body_line}")
                else:
                    lines.append(f"{pad}{_INDENT}>")
    for child in c.children:
        lines.append(comment_to_markdown(child, depth=depth + 1, now=n))
    if c.truncated_replies:
        lines.append(f"{pad}{_INDENT}- _[{_replies(c.truncated_replies)} not shown]_")
    return "\n".join(lines)


def _now(now: int | None) -> int:
    return int(time.time()) if now is None else now


def _time_ago(t: int, now: int) -> str:
    delta = max(0, now - t)
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    if delta < 365 * 86400:
        return f"{delta // 86400}d ago"
    return f"{delta // (365 * 86400)}y ago"
