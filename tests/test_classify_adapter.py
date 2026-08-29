"""Tests for classify:// -- full-population provenance classification (BACK-1233)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reveal.adapters.classify import ClassifyAdapter

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


def _write(path: Path, text: str = "x = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_classify_tags_every_file_not_just_a_ranked_subset(tmp_path):
    _write(tmp_path / 'app.py')
    _write(tmp_path / 'lib' / 'helper.py')
    _write(tmp_path / 'tests' / 'test_app.py')
    _write(tmp_path / 'vendor' / 'thirdparty.py')
    _write(tmp_path / 'assets' / 'bundle.min.js')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['app.py'] == 'first_party'
    assert by_file['lib/helper.py'] == 'first_party'
    assert by_file['tests/test_app.py'] == 'test'
    assert by_file['vendor/thirdparty.py'] == 'vendor'
    assert by_file['assets/bundle.min.js'] == 'minified'

    # Full population, not a ranked/capped subset (BACK-1195's gap).
    assert len(result['files']) == 5
    assert result['summary']['total'] == 5
    assert result['summary']['by_provenance'] == {
        'first_party': 2,
        'test': 1,
        'vendor': 1,
        'minified': 1,
    }


def test_classify_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ClassifyAdapter(str(tmp_path / 'nope')).get_structure()


def test_classify_help_and_schema_present():
    help_data = ClassifyAdapter.get_help()
    assert help_data['name'] == 'classify'

    schema = ClassifyAdapter.get_schema()
    assert schema['adapter'] == 'classify'
