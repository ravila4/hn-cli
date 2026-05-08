"""Shared pytest fixtures for hn-cli tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict | list:
    """Load a JSON fixture by relative path, e.g. 'algolia/items_42.json'."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def algolia_item_42() -> dict:
    return load("algolia/items_42.json")


@pytest.fixture
def algolia_item_ask_hn() -> dict:
    return load("algolia/items_ask_hn.json")


@pytest.fixture
def algolia_search_rust() -> dict:
    return load("algolia/search_rust.json")


@pytest.fixture
def firebase_item_42() -> dict:
    return load("firebase/item_42.json")


@pytest.fixture
def firebase_item_self_post() -> dict:
    return load("firebase/item_self_post.json")


@pytest.fixture
def firebase_topstories() -> list[int]:
    return load("firebase/topstories.json")
