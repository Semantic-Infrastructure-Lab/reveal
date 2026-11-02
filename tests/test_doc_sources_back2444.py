"""Canonical source inventory and answer controls for the bounded docs cohort."""

import pytest

from test_example_recipes_run import _documented_commands


def test_collector_includes_canonical_sources_with_distinct_provenance(tmp_path):
    docs = tmp_path / 'reveal' / 'docs'
    examples = {
        tmp_path / 'README.md': 'reveal overview .',
        docs / 'AGENT_HELP.md': 'reveal help://quick',
        docs / 'guides' / 'SAME.md': 'reveal env://',
        docs / 'adapters' / 'SAME.md': 'reveal imports .',
        docs / 'QUICK_START.md': 'reveal src/',
        docs / 'WHY_REVEAL.md': 'reveal app.py',
        docs / 'INDEX.md': 'reveal help://adapters',
    }
    for source, command in examples.items():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f'```bash\n{command}\n```\n', encoding='utf-8')
    rows = list(_documented_commands(docs))
    assert {row[0] for row in rows} == {
        '../../README.md', 'AGENT_HELP.md', 'guides/SAME.md', 'adapters/SAME.md',
        'QUICK_START.md', 'WHY_REVEAL.md', 'INDEX.md',
    }
    assert {row[1] for row in rows} == set(examples.values())


def test_legacy_guide_remains_collected(tmp_path):
    (tmp_path / 'guides').mkdir()
    (tmp_path / 'AGENT_HELP.md').write_text('```bash\nreveal help://quick\n```', encoding='utf-8')
    (tmp_path / 'guides' / 'EXAMPLE.md').write_text('```bash\nreveal app.py\n```', encoding='utf-8')
    assert {row[1] for row in _documented_commands(tmp_path)} == {'reveal help://quick', 'reveal app.py'}
