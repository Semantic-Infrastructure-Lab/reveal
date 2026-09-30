"""BACK-1516: markdown:// walked on its own and honored neither --exclude nor REVEAL_IGNORE.

It now walks through the shared walker (path_utils._walk_code_files, BACK-1223) with
prune_noise=False: the exclusions apply, and docs under build/ or vendor/ are still found.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def docs(tmp_path, monkeypatch):
    for rel in ('keep/a.md', 'skipme/b.md', 'build/c.md'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('# T\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _listed(*args):
    result = _run_reveal_direct('markdown://.', '--format', 'json', *args)
    assert result.returncode == 0, result.stderr
    return sorted(r['relative_path'] for r in json.loads(result.stdout)['results'])


def test_exclude_applies(docs):
    assert _listed('--exclude', 'skipme/') == ['build/c.md', 'keep/a.md']


def test_reveal_ignore_applies(docs, monkeypatch):
    from reveal.config import RevealConfig
    monkeypatch.setenv('REVEAL_IGNORE', 'skipme/**')
    monkeypatch.setattr(RevealConfig, '_cache', {})  # a config built before the env var
    assert _listed() == ['build/c.md', 'keep/a.md']


def test_docs_under_code_noise_dirs_are_still_found(docs):
    """The code walkers' skip list (build/, vendor/, ...) is not a docs policy."""
    assert _listed() == ['build/c.md', 'keep/a.md', 'skipme/b.md']
