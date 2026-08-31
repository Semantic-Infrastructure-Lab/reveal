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
    # vendor/, no banner (plain locale data files often have none). Uses a
    # library-named directory (momentjs/), matching BACK-1238's real cited
    # evidence -- not a generic 'i18n'/'locale' directory name, which
    # BACK-1242 carved out as a first-party convention (see the two tests
    # below).
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        _write(tmp_path / 'app' / 'assets' / 'momentjs' / f'{code}.js')
    _write(tmp_path / 'app' / 'assets' / 'momentjs' / 'index.js')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        assert by_file[f'app/assets/momentjs/{code}.js'] == 'vendor'
    # index.js doesn't match the locale-stem pattern -- untouched.
    assert by_file['app/assets/momentjs/index.js'] == 'first_party'


def test_classify_locale_fanout_spares_first_party_i18n_directory(tmp_path):
    # BACK-1242: a directory literally named after a first-party i18n
    # convention (Rails' config/locales/, generically locale/i18n/lang/...)
    # is where a PROJECT keeps ITS OWN translations -- fan-out there alone
    # must not flip these to vendor. Confirmed false positive on a real
    # Rails corpus (config/locales/*.yml) and a real TypeScript corpus
    # (src/renderer/i18n/*.ts).
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        _write(tmp_path / 'config' / 'locales' / f'{code}.yml')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        assert by_file[f'config/locales/{code}.yml'] == 'first_party'


def test_classify_locale_fanout_still_fires_under_real_vendor_dir(tmp_path):
    # The first-party i18n carve-out doesn't apply once actually nested
    # under a recognized vendor directory (e.g. a vendored gem's own
    # config/locales/) -- still a real fan-out, still vendored.
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        _write(tmp_path / 'vendor' / 'gems' / 'somegem' / 'config' / 'locales' / f'{code}.yml')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    for code in ('en', 'fr', 'de', 'es', 'it', 'nl'):
        assert by_file[f'vendor/gems/somegem/config/locales/{code}.yml'] == 'vendor'


def test_classify_discloses_excluded_files_with_no_analyzer(tmp_path):
    """BACK-1241: classify:// (and overview://, sharing the same walker)
    silently excludes extensions with no registered analyzer (.erb/.vue/
    .scss/.css confirmed real) from both the population and the count --
    summary.excluded/excluded_by_extension must disclose the gap."""
    _write(tmp_path / 'main.py')
    _write(tmp_path / 'README.md', '# readme\n')
    _write(tmp_path / 'show.html.erb', '<div><%= @user.name %></div>\n')
    _write(tmp_path / 'component.vue', '<template><div/></template>\n')
    _write(tmp_path / 'style.css', 'body { color: red; }\n')
    _write(tmp_path / 'style.scss', '.foo { color: blue; }\n')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    # Only the 2 analyzable files are in the population/count, as before.
    assert result['summary']['total'] == 2
    files = {row['file'] for row in result['files']}
    assert files == {'main.py', 'README.md'}
    # The 4 excluded files are now disclosed, not silently dropped.
    assert result['summary']['excluded'] == 4
    assert result['summary']['excluded_by_extension'] == {
        '.erb': 1, '.vue': 1, '.css': 1, '.scss': 1,
    }


def test_classify_locale_fanout_below_threshold_stays_first_party(tmp_path):
    # A couple of genuinely per-language first-party fixtures shouldn't
    # false-positive -- only a fan-out above the threshold trips it.
    for code in ('en', 'fr'):
        _write(tmp_path / 'fixtures' / f'{code}.js')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['fixtures/en.js'] == 'first_party'
    assert by_file['fixtures/fr.js'] == 'first_party'


def test_classify_spec_md_is_not_tagged_test(tmp_path):
    # BACK-1251: a file literally named spec.md is a common
    # spec-driven-development requirements doc (e.g. openspec/), not a test
    # -- TEST_DIR_NAMES' bare 'spec' stem match previously fired on any .md
    # file with that stem regardless of directory. Confirmed on a real
    # corpus: 145 of 414 test-tagged files were openspec/ requirements docs.
    _write(tmp_path / 'openspec' / 'feature-x' / 'spec.md')
    # A real spec FILE (code extension) under an actual test directory
    # should still classify as test -- the fix narrows the bare-stem match
    # for doc extensions only, it doesn't touch directory-based detection.
    _write(tmp_path / 'spec' / 'user_spec.rb')

    result = ClassifyAdapter(str(tmp_path)).get_structure()

    by_file = {row['file']: row['provenance'] for row in result['files']}
    assert by_file['openspec/feature-x/spec.md'] == 'first_party'
    assert by_file['spec/user_spec.rb'] == 'test'


def test_classify_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ClassifyAdapter(str(tmp_path / 'nope')).get_structure()


def test_classify_help_and_schema_present():
    help_data = ClassifyAdapter.get_help()
    assert help_data['name'] == 'classify'

    schema = ClassifyAdapter.get_schema()
    assert schema['adapter'] == 'classify'
