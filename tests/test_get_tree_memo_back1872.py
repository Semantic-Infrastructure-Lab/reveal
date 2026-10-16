"""core.get_tree reuses the last few parses, so per-file rules share one tree (BACK-1872)."""

import pytest

from reveal.core import treesitter_parse as tp
from reveal.core.treesitter_parse import GrammarUnavailable, get_tree


def test_same_source_parses_once(monkeypatch):
    calls = []
    real = tp.ts_parse
    monkeypatch.setattr(tp, "ts_parse", lambda parser, src: calls.append(src) or real(parser, src))
    a = get_tree("python", "x = 1\n")
    b = get_tree("python", "x = 1\n")
    assert a is b and len(calls) == 1
    c = get_tree("python", "x = 2\n")
    assert c is not a and len(calls) == 2  # different source: a real parse, not a stale tree


def test_language_is_part_of_the_key():
    assert get_tree("python", "x = 1\n") is not get_tree("javascript", "x = 1\n")


def test_unavailable_grammar_is_not_cached(monkeypatch):
    def boom(language, announce_fetch=True):
        raise GrammarUnavailable(language, RuntimeError("no grammar"))
    monkeypatch.setattr(tp, "get_parser", boom)
    for _ in range(2):
        with pytest.raises(GrammarUnavailable):
            get_tree("python", "unseen source for this test\n")
