"""A census that could not be taken is not "a census that counted no source file" (BACK-2248).

``language_census`` turns an OSError that is not a directory-walk error into ``{}``. The confidence was
rightly withheld, but W-CALLS-12 then said the census *counted no source file in scope*, which a healthy
walk of an empty scope also says, and the failure was nowhere in the answer. It now says the census
could not be taken and why (the class and reason, no host path). A failed census stays what BACK-2027
decided: not a lost directory, so ``parse_mode`` is unchanged.
"""
import json

import pytest

from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import confidence

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _decline(meta):
    return next(w for w in meta['warnings'] if w.get('code') == 'W-CALLS-12')


@pytest.fixture
def broken_census(monkeypatch):
    def fail(path, *args, **kwargs):
        raise PermissionError(13, 'controlled non-walk census failure', str(path))
    monkeypatch.setattr(confidence, 'census_for_path', fail)


def test_the_cause_names_the_failure_not_an_empty_scope(tmp_path, broken_census):
    file = _write(tmp_path / 'single.py', 'VALUE = 1\n')
    meta = confidence.build_meta(str(file))
    message = _decline(meta)['message']
    assert 'could not be taken' in message and 'PermissionError: controlled non-walk census failure' in message
    assert 'counted no source file' not in message
    assert meta['confidence'] is None


def test_the_cause_carries_no_host_path(tmp_path, broken_census):
    file = _write(tmp_path / 'single.py', 'VALUE = 1\n')
    assert str(tmp_path) not in json.dumps(confidence.build_meta(str(file)))


def test_a_failed_census_is_still_not_a_directory_loss(tmp_path, broken_census):
    """BACK-2027's contract, kept: no directories warning and the parse mode of a complete parse."""
    file = _write(tmp_path / 'single.py', 'VALUE = 1\n')
    meta = confidence.build_meta(str(file))
    assert meta['parse_mode'] == 'tree_sitter_full'
    assert not any(w.get('unit') == 'directories' for w in meta['warnings'])


@pytest.mark.parametrize('query', ['rank=callers', 'callers=leaf', 'callees=leaf'])
def test_every_public_mode_says_so(tmp_path, broken_census, query):
    file = _write(tmp_path / 'single.py', 'def leaf():\n    pass\n')
    meta = CallsAdapter(str(file), query).get_structure()['meta']
    assert 'could not be taken' in _decline(meta)['message']
    assert 'confidence' not in meta


def test_a_healthy_empty_scope_keeps_its_own_wording(tmp_path):
    """Control: nothing failed and nothing was counted."""
    empty = tmp_path / 'empty'
    empty.mkdir()
    message = _decline(confidence.build_meta(str(empty)))['message']
    assert 'counted no source file' in message and 'could not be taken' not in message


def test_a_healthy_census_has_no_decline(tmp_path):
    root = tmp_path / 'ok'
    _write(root / 'm.py', 'def f():\n    pass\n')
    assert 'W-CALLS-12' not in [w.get('code') for w in confidence.build_meta(str(root))['warnings']]
