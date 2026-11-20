"""An equal repeated term is one term (Scott 2026-11-19, BACK-2715).

A repeatable control (``where``, ``match``, ``exclude``) combines its terms; the same term given twice, by the URI and a
flag, by one flag twice or by one key twice, is that term once: the answer and its echo are the single-term request's.
It parallels "Conflicting values": a scalar given twice with equal values is accepted once. Claude ``match`` already
deduplicated; AST and Markdown echoed ``A AND A``.
"""
import json

import pytest

import test_vocabulary_conformance_back2654 as C
from test_vocabulary_conformance_back2654 import workspace  # noqa: F401  (fixture)


def _answer(*argv):
    run = C._run(*argv, '--format', 'json')
    assert run.rc == 0, run.brief()
    doc = json.loads(run.out)
    doc.pop('meta', None)
    return doc


ONCE_AND_TWICE = [
    ('ast where', ['ast://proj?where=lines>1'],
     [['ast://proj?where=lines>1', '--where', 'lines>1'], ['ast', 'proj', '--where', 'lines>1', '--where', 'lines>1'],
      ['ast://proj?where=lines>1&where=lines>1']]),
    ('markdown match', ['markdown://proj?match=a'],
     [['markdown://proj?match=a', '--match', 'a'], ['markdown', 'proj', '--match', 'a', '--match', 'a'],
      ['markdown://proj?match=a&match=a']]),
    ('markdown where', ['markdown://proj?where=title~=a'],
     [['markdown://proj?where=title~=a', '--where', 'title~=a'],
      ['markdown', 'proj', '--where', 'title~=a', '--where', 'title~=a']]),
    ('metrics exclude', ['metrics://proj?exclude=docs'],
     [['metrics://proj?exclude=docs', '--exclude', 'docs'], ['metrics', 'proj', '--exclude', 'docs', '--exclude', 'docs']]),
]


@pytest.mark.parametrize('label,once,twice', ONCE_AND_TWICE, ids=[case[0] for case in ONCE_AND_TWICE])
def test_an_equal_repeated_term_answers_as_the_term_once(workspace, label, once, twice):  # noqa: F811
    expected = _answer(*once)
    for argv in twice:
        assert _answer(*argv) == expected, (label, argv)


def test_different_terms_still_combine(workspace):  # noqa: F811  (negative control)
    both = _answer('ast', 'proj', '--where', 'lines>1', '--where', 'lines<1000')
    assert 'lines>1' in json.dumps(both) and 'lines<1000' in json.dumps(both)
    assert both != _answer('ast://proj?where=lines>1')
