"""Tests for hn_cli.models — dataclasses and normalizers."""

from __future__ import annotations

import pytest

from hn_cli.models import Comment, Story, _infer_story_type


class TestCommentFromAlgolia:
    def test_simple_comment(self):
        d = {
            "id": 43,
            "created_at_i": 1171869300,
            "type": "comment",
            "author": "bob",
            "text": "<p>Great point!</p>",
            "children": [],
        }
        c = Comment.from_algolia(d)
        assert c.id == 43
        assert c.by == "bob"
        assert c.time == 1171869300
        assert c.text == "<p>Great point!</p>"
        assert c.children == ()
        assert c.truncated_replies == 0

    def test_deleted_comment_renders_placeholder(self):
        d = {
            "id": 45,
            "created_at_i": 1171869500,
            "type": "comment",
            "author": None,
            "text": None,
            "children": [],
        }
        c = Comment.from_algolia(d)
        assert c.id == 45
        assert c.by is None
        assert c.text == "[deleted]"

    def test_recurses_into_children(self):
        d = {
            "id": 43,
            "created_at_i": 1171869300,
            "type": "comment",
            "author": "bob",
            "text": "<p>parent</p>",
            "children": [
                {
                    "id": 44,
                    "created_at_i": 1171869400,
                    "type": "comment",
                    "author": "carol",
                    "text": "<p>child</p>",
                    "children": [],
                }
            ],
        }
        c = Comment.from_algolia(d)
        assert len(c.children) == 1
        child = c.children[0]
        assert child.id == 44
        assert child.by == "carol"
        assert child.children == ()


class TestStoryFromAlgoliaItem:
    def test_full_thread(self, algolia_item_42):
        s = Story.from_algolia_item(algolia_item_42)
        assert s.id == 42
        assert s.title == "A test story"
        assert s.url == "https://example.com/foo"
        assert s.score == 100
        assert s.by == "alice"
        assert s.time == 1171869213
        assert s.text is None
        # Tree has 3 comments total: 43, 44 (child of 43), 45
        assert s.descendants == 3
        assert len(s.children) == 2
        assert s.children[0].id == 43
        assert s.children[1].id == 45

    def test_self_post(self, algolia_item_ask_hn):
        s = Story.from_algolia_item(algolia_item_ask_hn)
        assert s.url is None
        assert s.text == "<p>Curious about your routines.</p>"
        assert s.descendants == 0
        assert s.children == ()


class TestStoryFromAlgoliaHit:
    def test_search_hit_with_url(self, algolia_search_rust):
        hit = algolia_search_rust["hits"][0]
        s = Story.from_algolia_hit(hit)
        assert s.id == 200
        assert s.title == "Rust async runtime comparison"
        assert s.url == "https://example.com/rust"
        assert s.score == 250
        assert s.by == "rustacean"
        assert s.time == 1700000000
        assert s.descendants == 130
        assert s.text is None
        assert s.children == ()

    def test_search_hit_self_post(self, algolia_search_rust):
        hit = algolia_search_rust["hits"][1]
        s = Story.from_algolia_hit(hit)
        assert s.url is None
        assert s.text == "<p>What do you all use?</p>"


class TestStoryFromFirebase:
    def test_link_story(self, firebase_item_42):
        s = Story.from_firebase(firebase_item_42)
        assert s.id == 42
        assert s.title == "A test story"
        assert s.url == "https://example.com/foo"
        assert s.score == 100
        assert s.by == "alice"
        assert s.time == 1171869213
        assert s.descendants == 3
        assert s.text is None
        # Firebase per-item doesn't include the comment tree; we only get kids ids.
        assert s.children == ()

    def test_self_post(self, firebase_item_self_post):
        s = Story.from_firebase(firebase_item_self_post)
        assert s.url is None
        assert s.text == "<p>Curious about your routines.</p>"
        assert s.descendants == 0


class TestRawTextStorage:
    """Library callers see HTML with entities intact; JSON output decodes them.

    Decoding at the model boundary would corrupt text like `<p>x &lt; y</p>`
    by routing decoded `<` back through the markdown renderer's HTMLParser.
    """

    def test_comment_text_kept_raw(self):
        d = {
            "id": 1,
            "type": "comment",
            "author": "x",
            "created_at_i": 0,
            "text": "https:&#x2F;&#x2F;example.com",
            "children": [],
        }
        c = Comment.from_algolia(d)
        assert c.text == "https:&#x2F;&#x2F;example.com"

    def test_story_text_kept_raw(self):
        d = {
            "id": 1,
            "type": "story",
            "author": "x",
            "created_at_i": 0,
            "title": "t",
            "url": None,
            "text": "<p>I&#x27;m here &lt;3</p>",
            "points": 1,
            "children": [],
        }
        s = Story.from_algolia_item(d)
        assert s.text == "<p>I&#x27;m here &lt;3</p>"

    def test_search_hit_story_text_kept_raw(self):
        hit = {
            "objectID": "1",
            "title": "t",
            "url": None,
            "author": "x",
            "points": 1,
            "num_comments": 0,
            "story_text": "<p>don&#x27;t",
            "created_at_i": 0,
        }
        s = Story.from_algolia_hit(hit)
        assert s.text == "<p>don&#x27;t"


class TestStoryType:
    """`type` lets agents triage Ask/Show/Job without a second round trip."""

    @pytest.mark.parametrize(
        "tags, title, fb_type, expected",
        [
            (["story", "ask_hn"], "Ask HN: anything?", None, "ask"),
            (["story", "show_hn"], "Show HN: my thing", None, "show"),
            (["job"], "We're hiring", None, "job"),
            (["story"], "Just a regular link", None, "story"),
            (None, "Ask HN: title prefix only", None, "ask"),
            (None, "Show HN: title prefix only", None, "show"),
            (None, "Senior Engineer at Acme", "job", "job"),
            (None, "Plain story", "story", "story"),
        ],
    )
    def test_inference(self, tags, title, fb_type, expected):
        assert _infer_story_type(tags, title, fb_type) == expected

    def test_algolia_item_picks_up_tags(self, algolia_item_42):
        # Without _tags, falls through to title-prefix and lands on "story".
        s = Story.from_algolia_item(algolia_item_42)
        assert s.type == "story"

    def test_algolia_item_with_ask_hn_tag(self):
        d = {
            "id": 1,
            "type": "story",
            "author": "x",
            "created_at_i": 0,
            "title": "Foo",
            "url": None,
            "text": None,
            "points": 1,
            "_tags": ["story", "ask_hn"],
            "children": [],
        }
        s = Story.from_algolia_item(d)
        assert s.type == "ask"

    def test_algolia_item_ask_hn_via_title(self, algolia_item_ask_hn):
        # Fixture lacks _tags but title starts with "Ask HN".
        s = Story.from_algolia_item(algolia_item_ask_hn)
        assert s.type == "ask"

    def test_algolia_hit_via_title_prefix(self, algolia_search_rust):
        # Second hit's title starts with "Ask HN:".
        hit = algolia_search_rust["hits"][1]
        s = Story.from_algolia_hit(hit)
        assert s.type == "ask"

    def test_firebase_job_type(self):
        d = {
            "id": 1,
            "by": "x",
            "title": "We are hiring",
            "score": 0,
            "time": 0,
            "descendants": 0,
            "type": "job",
        }
        s = Story.from_firebase(d)
        assert s.type == "job"

    def test_firebase_ask_via_title(self, firebase_item_self_post):
        s = Story.from_firebase(firebase_item_self_post)
        assert s.type == "ask"


class TestDepthHistogram:
    """Per-level comment counts for sizing a re-fetch at a different `--depth`."""

    def test_fixture_tree(self, algolia_item_42):
        # Fixture: 2 top-level (43, 45), 1 reply (44 under 43).
        s = Story.from_algolia_item(algolia_item_42)
        assert s.depth_histogram == (2, 1)

    def test_empty_thread(self, algolia_item_ask_hn):
        s = Story.from_algolia_item(algolia_item_ask_hn)
        assert s.depth_histogram == ()

    def test_only_populated_on_algolia_item(self, algolia_search_rust, firebase_item_42):
        # Search hits and Firebase per-item never carry a tree, so histogram is empty.
        hit = Story.from_algolia_hit(algolia_search_rust["hits"][0])
        fb = Story.from_firebase(firebase_item_42)
        assert hit.depth_histogram == ()
        assert fb.depth_histogram == ()

    def test_deeper_tree(self):
        # Build a tree with shape: 3 top-level, 2 replies under one of them,
        # 1 reply under one of those. Expected histogram: (3, 2, 1).
        d = {
            "id": 1,
            "type": "story",
            "author": "x",
            "created_at_i": 0,
            "title": "t",
            "url": None,
            "text": None,
            "points": 0,
            "children": [
                {
                    "id": 10,
                    "type": "comment",
                    "author": "a",
                    "created_at_i": 0,
                    "text": "x",
                    "children": [
                        {
                            "id": 100,
                            "type": "comment",
                            "author": "b",
                            "created_at_i": 0,
                            "text": "x",
                            "children": [
                                {
                                    "id": 1000,
                                    "type": "comment",
                                    "author": "c",
                                    "created_at_i": 0,
                                    "text": "x",
                                    "children": [],
                                }
                            ],
                        },
                        {
                            "id": 101,
                            "type": "comment",
                            "author": "b",
                            "created_at_i": 0,
                            "text": "x",
                            "children": [],
                        },
                    ],
                },
                {
                    "id": 11,
                    "type": "comment",
                    "author": "a",
                    "created_at_i": 0,
                    "text": "x",
                    "children": [],
                },
                {
                    "id": 12,
                    "type": "comment",
                    "author": "a",
                    "created_at_i": 0,
                    "text": "x",
                    "children": [],
                },
            ],
        }
        s = Story.from_algolia_item(d)
        assert s.depth_histogram == (3, 2, 1)


class TestFrozen:
    def test_story_is_frozen(self):
        s = Story(id=1, title="t", url=None, score=0, by="a", time=0, descendants=0)
        try:
            s.id = 2  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("Story should be frozen")
