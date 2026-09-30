"""BACK-1568: config's resolve cache keyed a relative path by its spelling.

_cached_resolve(Path('.')) pinned the cwd of its first caller for the life of the process.
A pytest worker starts in the repo root, whose .reveal.yaml ignores build/**, so a later
test that chdir'd into a tmp dir and walked '.' got the repo's ignore patterns:
tests/test_markdown_walk_back1516.py lost build/c.md about 1 run in 4 under -n auto.
"""
import json
from pathlib import Path

from conftest import _run_reveal_direct
from reveal import config
from reveal.config import RevealConfig, _cached_resolve


def test_a_relative_path_resolves_against_the_current_cwd(tmp_path, monkeypatch):
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    assert _cached_resolve(Path('.')) == first.resolve()
    monkeypatch.chdir(second)
    assert _cached_resolve(Path('.')) == second.resolve()


def test_a_walk_of_dot_uses_the_config_of_the_cwd_it_runs_in(tmp_path, monkeypatch):
    seeded = tmp_path / 'seeded'
    seeded.mkdir()
    (seeded / '.reveal.yaml').write_text("root: true\nignore: ['build/**']\n", encoding='utf-8')
    monkeypatch.chdir(seeded)
    monkeypatch.setattr(config, '_path_resolve_cache', {})  # '.' first resolved in seeded/
    monkeypatch.setattr(RevealConfig, '_cache', {})
    RevealConfig.get(Path('.'))  # an earlier caller, in a directory that ignores build/

    docs = tmp_path / 'docs'
    (docs / 'build').mkdir(parents=True)
    (docs / 'build' / 'c.md').write_text('# T\n', encoding='utf-8')
    monkeypatch.chdir(docs)
    RevealConfig._cache.clear()
    result = _run_reveal_direct('markdown://.', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert [r['relative_path'] for r in json.loads(result.stdout)['results']] == ['build/c.md']
