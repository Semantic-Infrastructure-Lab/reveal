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


def test_a_flag_that_differs_from_the_uri_names_both(tree):
    """BACK-2654 rule 1: the conflict is an invalid request naming both (the URI used to win with a note)."""
    err = _stderr(tree, '?sort=name', '--sort', 'complexity')
    assert '--sort conflicts with sort=name in the URI' in err
    assert 'not supported by this adapter' not in err


def test_the_same_holds_for_a_different_flag(tree):
    err = _stderr(tree, '?limit=10', '--limit', '5')
    assert '--limit conflicts with limit=10 in the URI' in err
    assert 'not supported by this adapter' not in err


def test_ast_type_after_the_uri_is_asts_own_legacy_flag(tree):
    """After an AST URI, --type is AST's own flag (the legacy word of kind), as on ``reveal ast`` (BACK-2673): it meets
    the URI's ?type= under rule 1, so two different values name both. It used to be the main parser's file-mode --type,
    noted as having no effect."""
    err = _stderr(tree, '?type=class', '--type', 'function')
    assert '--type conflicts with type=class in the URI' in err, err


def test_a_flag_that_agrees_with_the_uri_prints_no_note(tree):
    assert 'Note:' not in _stderr(tree, '?sort=name', '--sort', 'name')


def test_the_flag_alone_is_supported_and_prints_no_note(tree):
    assert 'Note:' not in _stderr(tree, '', '--sort=-lines')


def test_a_flag_the_adapter_does_not_support_keeps_its_own_note(tree):
    """Control: a flag the noun does not take is rejected naming its controls (BACK-2654 rule 3; was a note)."""
    err = _stderr(tree, '', '--since', '1.day')
    assert "unsupported control '--since'; supported controls: where, " in err
