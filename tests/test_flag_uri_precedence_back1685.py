"""BACK-1685: a flag the URI overrides says so, instead of "not supported by this adapter".

`reveal "ast://DIR?sort=name" --sort complexity` printed "--sort has no effect on ast:// queries --
not supported by this adapter", yet `--sort` works on ast:// when the URI has no `sort=`. The flag is
supported; the URI's own value wins, and the note now names it.
"""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'm.py').write_text(
        'def a():\n    pass\n\n\ndef b(x):\n    if x:\n        return 1\n    return 0\n', encoding='utf-8')
    return tmp_path


def _stderr(tree, uri_query, *flags):
    """stderr of `reveal ast://.<query> <flags>` run inside *tree* (a relative URI: no drive letter)."""
    proc = subprocess.run([sys.executable, '-m', 'reveal', f'ast://.{uri_query}', *flags],
                          capture_output=True, text=True, encoding='utf-8', cwd=tree)
    return proc.stderr


def test_a_flag_the_uri_overrides_names_the_uri_value(tree):
    err = _stderr(tree, '?sort=name', '--sort', 'complexity')
    assert '--sort ignored on ast:// -- the URI already sets sort=name.' in err
    assert 'not supported by this adapter' not in err


def test_the_same_holds_for_a_different_overridden_flag(tree):
    err = _stderr(tree, '?limit=10', '--limit', '5')
    assert '--limit ignored on ast:// -- the URI already sets limit=10.' in err
    assert 'not supported by this adapter' not in err


def test_a_flag_with_no_query_form_keeps_its_own_note(tree):
    """--type is not an injectable ast:// flag (it has ?type= and a bare-path scan), so 'not supported'
    is the true reason there and the hint to use ?type= or a bare path stays."""
    err = _stderr(tree, '?type=class', '--type', 'function')
    assert '--type has no effect on ast:// queries' in err


def test_a_flag_that_agrees_with_the_uri_prints_no_note(tree):
    assert 'Note:' not in _stderr(tree, '?sort=name', '--sort', 'name')


def test_the_flag_alone_is_supported_and_prints_no_note(tree):
    assert 'Note:' not in _stderr(tree, '', '--sort=-lines')


def test_a_flag_the_adapter_does_not_support_keeps_its_own_note(tree):
    """Control: the 'not supported' wording is still right where it is true."""
    err = _stderr(tree, '', '--since', '1.day')
    assert '--since has no effect on ast://' in err
