"""Tests for the markdown renderer."""

from __future__ import annotations

from hn_cli.models import Comment, Story
from hn_cli.render import comment_to_markdown, html_to_markdown, story_to_markdown


class TestHtmlToMarkdown:
    def test_plain_text(self):
        assert html_to_markdown("hello world") == "hello world"

    def test_paragraph_break(self):
        assert html_to_markdown("first<p>second").strip() == "first\n\nsecond"

    def test_two_paragraphs(self):
        assert html_to_markdown("a<p>b<p>c").strip() == "a\n\nb\n\nc"

    def test_link_with_href(self):
        assert html_to_markdown('<a href="http://x">y</a>') == "[y](http://x)"

    def test_link_without_href(self):
        # Algolia/HN sometimes returns <a> without href; we keep the text.
        assert html_to_markdown("<a>y</a>") == "y"

    def test_italics(self):
        assert html_to_markdown("<i>italic</i>") == "_italic_"

    def test_inline_code(self):
        assert html_to_markdown("<code>x = 1</code>") == "`x = 1`"

    def test_pre_code_block(self):
        out = html_to_markdown("<pre><code>x = 1\ny = 2</code></pre>")
        assert "```" in out
        assert "x = 1\ny = 2" in out

    def test_html_entities_decoded(self):
        assert html_to_markdown("a &amp; b") == "a & b"
        assert html_to_markdown("don&#x27;t") == "don't"

    def test_nested_link_in_italic(self):
        out = html_to_markdown('<i>see <a href="x">here</a></i>')
        assert out == "_see [here](x)_"

    def test_unknown_tags_dropped_text_kept(self):
        assert html_to_markdown("<span>kept</span>") == "kept"


class TestCommentToMarkdown:
    def test_simple_comment(self):
        c = Comment(id=1, by="alice", time=1700000000, text="<p>hello")
        out = comment_to_markdown(c, now=1700003600)
        assert "alice" in out
        assert "hello" in out
        assert "1h ago" in out

    def test_deleted_comment_label(self):
        c = Comment(id=1, by=None, time=0, text="[deleted]")
        out = comment_to_markdown(c, now=0)
        assert "[deleted]" in out

    def test_indents_replies(self):
        child = Comment(id=2, by="bob", time=0, text="reply")
        parent = Comment(id=1, by="alice", time=0, text="parent", children=(child,))
        out = comment_to_markdown(parent, now=0)
        lines = out.splitlines()
        # The reply line should start with more indentation than the parent.
        parent_indent = len(lines[0]) - len(lines[0].lstrip())
        reply_lines = [ln for ln in lines if "bob" in ln]
        assert reply_lines, out
        assert len(reply_lines[0]) - len(reply_lines[0].lstrip()) > parent_indent

    def test_truncated_replies_line(self):
        c = Comment(id=1, by="alice", time=0, text="x", children=(), truncated_replies=4)
        out = comment_to_markdown(c, now=0)
        assert "4 replies not shown" in out

    def test_truncated_replies_singular(self):
        c = Comment(id=1, by="alice", time=0, text="x", children=(), truncated_replies=1)
        out = comment_to_markdown(c, now=0)
        assert "1 reply not shown" in out
        assert "1 replies" not in out


class TestStoryToMarkdown:
    def test_link_story_header(self):
        s = Story(
            id=42,
            title="A test story",
            url="https://example.com/foo",
            score=100,
            by="alice",
            time=1700000000,
            descendants=3,
        )
        out = story_to_markdown(s, now=1700000000 + 3600)
        assert "A test story" in out
        assert "100 points" in out
        assert "alice" in out
        assert "3 comments" in out
        assert "https://example.com/foo" in out

    def test_self_post_renders_text(self):
        s = Story(
            id=1,
            title="Ask HN: x",
            url=None,
            score=10,
            by="bob",
            time=0,
            descendants=0,
            text="<p>tell me",
        )
        out = story_to_markdown(s, now=0)
        assert "Ask HN: x" in out
        assert "tell me" in out

    def test_includes_comments_section(self):
        c = Comment(id=2, by="bob", time=0, text="<p>good")
        s = Story(
            id=1,
            title="t",
            url="https://x",
            score=1,
            by="a",
            time=0,
            descendants=1,
            children=(c,),
        )
        out = story_to_markdown(s, now=0)
        assert "## Comments" in out
        assert "bob" in out

    def test_truncated_top_level_message(self):
        s = Story(
            id=1,
            title="t",
            url="https://x",
            score=1,
            by="a",
            time=0,
            descendants=10,
            children=(),
            truncated_replies=10,
        )
        out = story_to_markdown(s, now=0)
        assert "10 replies not shown" in out
