"""Tests for parsing.truncate_story — depth-pruning the comment tree."""

from __future__ import annotations

from hn_cli.models import Comment, Story
from hn_cli.parsing import truncate_story


def _comment(id: int, *children: Comment) -> Comment:
    return Comment(id=id, by="x", time=0, text=f"c{id}", children=tuple(children))


def _story(*children: Comment) -> Story:
    return Story(
        id=1, title="t", url=None, score=0, by="a", time=0, descendants=0, children=children
    )


def test_depth_zero_strips_all_comments():
    s = _story(_comment(2, _comment(3, _comment(4))), _comment(5))
    out = truncate_story(s, 0)
    assert out.children == ()
    # Total descendants in original tree: 2,3,4,5 → 4
    assert out.truncated_replies == 4


def test_depth_one_keeps_top_level_only():
    s = _story(_comment(2, _comment(3), _comment(4)), _comment(5))
    out = truncate_story(s, 1)
    assert out.truncated_replies == 0
    assert len(out.children) == 2
    assert out.children[0].id == 2
    assert out.children[0].children == ()
    assert out.children[0].truncated_replies == 2  # comments 3, 4 hidden
    assert out.children[1].id == 5
    assert out.children[1].truncated_replies == 0  # nothing under it


def test_depth_two_keeps_two_levels():
    s = _story(_comment(2, _comment(3, _comment(4, _comment(5)))))
    out = truncate_story(s, 2)
    assert out.children[0].id == 2
    assert out.children[0].truncated_replies == 0
    grand = out.children[0].children[0]
    assert grand.id == 3
    assert grand.children == ()
    assert grand.truncated_replies == 2  # 4 and 5 hidden


def test_depth_larger_than_tree_is_noop():
    s = _story(_comment(2, _comment(3)), _comment(4))
    out = truncate_story(s, 99)
    # Same shape, no truncation flags set anywhere.
    assert len(out.children) == 2
    assert out.children[0].truncated_replies == 0
    assert out.children[0].children[0].id == 3
    assert out.children[0].children[0].truncated_replies == 0


def test_returns_new_story_instance():
    s = _story(_comment(2))
    out = truncate_story(s, 1)
    assert out is not s


def test_story_with_no_comments_unchanged():
    s = _story()
    out = truncate_story(s, 0)
    assert out.children == ()
    assert out.truncated_replies == 0


def test_negative_depth_treated_as_zero():
    s = _story(_comment(2, _comment(3)))
    out = truncate_story(s, -5)
    assert out.children == ()
    assert out.truncated_replies == 2


class TestTruncatedTotal:
    """Aggregated count across the whole tree — answers 'is there more out
    there I'm not seeing?' without requiring callers to walk the tree."""

    def test_zero_when_nothing_pruned(self):
        s = _story(_comment(2, _comment(3)), _comment(4))
        out = truncate_story(s, 99)
        assert out.truncated_total == 0

    def test_equals_descendant_count_at_depth_zero(self):
        s = _story(_comment(2, _comment(3, _comment(4))), _comment(5))
        out = truncate_story(s, 0)
        # 4 descendants total; total == story-level truncated_replies here.
        assert out.truncated_total == 4
        assert out.truncated_replies == 4

    def test_aggregates_across_multiple_parents(self):
        # Two top-level comments, each with one pruned child. Per-parent
        # `truncated_replies` is 1 each; aggregated total should be 2.
        s = _story(_comment(2, _comment(3)), _comment(4, _comment(5)))
        out = truncate_story(s, 1)
        assert out.children[0].truncated_replies == 1
        assert out.children[1].truncated_replies == 1
        assert out.truncated_total == 2
        assert out.truncated_replies == 0

    def test_aggregates_deeper_pruning(self):
        # depth=2 keeps 2 levels; the third level (one node) is pruned.
        s = _story(_comment(2, _comment(3, _comment(4, _comment(5)))))
        out = truncate_story(s, 2)
        # `4` and its child `5` are gone — that's 2 pruned descendants.
        assert out.truncated_total == 2
