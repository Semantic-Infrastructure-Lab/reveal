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


def test_classify_detects_in_tree_vendored_banner(tmp_path):
    # In-tree vendoring (BACK-1238): a bundled library dropped straight into
    # app source, not under a directory literally named vendor/. Real
    # moment.js/jQuery-plugin banners look like this.
    _write(tmp_path / 'app.js', 'const x = 1;\n')
    _write(
        tmp_path / 'app' / 'assets' / 'javascripts' / 'moment.js',
        '/*! moment.js v2.29.4 */\n(function (global, factory) {\n})();\n',
    )

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['app.js'] == 'first_party'
    assert by_file['app/assets/javascripts/moment.js'] == 'vendor'


def test_classify_ignores_bang_comment_without_version_token(tmp_path):
    # A bang-comment alone isn't enough -- gated on a version-looking token
    # so first-party code using `/*!` for an unrelated reason doesn't
    # false-positive.
    _write(tmp_path / 'important.js', '/*! keep this comment */\nconst x = 1;\n')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['important.js'] == 'first_party'


def test_classify_detects_locale_file_fanout(tmp_path):
    # jQuery Validate/moment.js-style vendored i18n bundle: many
    # same-extension siblings named after language codes, not under
    # vendor/, no banner (plain locale data files often have none).
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        _write(tmp_path / 'app' / 'assets' / 'i18n' / f'{code}.js')
    _write(tmp_path / 'app' / 'assets' / 'i18n' / 'index.js')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        assert by_file[f'app/assets/i18n/{code}.js'] == 'vendor'
    # index.js doesn't match the locale-stem pattern -- untouched.
    assert by_file['app/assets/i18n/index.js'] == 'first_party'


def test_classify_locale_fanout_below_threshold_stays_first_party(tmp_path):
    # A couple of genuinely per-language first-party fixtures shouldn't
    # false-positive -- only a fan-out above the threshold trips it.
    for code in ('en', 'fr'):
        _write(tmp_path / 'fixtures' / f'{code}.js')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['fixtures/en.js'] == 'first_party'
    assert by_file['fixtures/fr.js'] == 'first_party'


def test_classify_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ClassifyAdapter(str(tmp_path / 'nope')).get_structure()


def test_classify_help_and_schema_present():
    help_data = ClassifyAdapter.get_help()
    assert help_data['name'] == 'classify'

    schema = ClassifyAdapter.get_schema()
    assert schema['adapter'] == 'classify'
