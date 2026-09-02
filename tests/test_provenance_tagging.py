"""BACK-1258: provenance tagging — reach, accuracy, and the locale false positive.

Three defects reported together, all about the `provenance` field (BACK-1195):

1. ast:// and calls://?uncalled carried no provenance field at all, so a reader
   had no way to discount vendored noise in the two rankings most likely to be
   dominated by it.
2. is_minified_filename was a case-sensitive endswith() over five literal
   suffixes, so content-hashed build output and .mjs/.cjs bundles classified as
   first_party — which is how a vendored bundle reached #1 in a ranking.
3. classify://'s locale fan-out checked only the immediate parent directory for
   the first-party-i18n exemption, so a Rails app's own nested translations were
   labelled vendor (56 files, 74% of all vendor verdicts on camaleon-cms).
"""

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.component


class TestMinifiedDetection:
    """Defect 2 — every case here returned False before the fix except the
    three plain lowercase ones."""

    @pytest.mark.parametrize('filename', [
        'a.min.js', 'a.min.css', 'a-min.js', 'jquery-3.6.0.min.js',
        'a.min.mjs', 'a.min.cjs',            # ESM/CJS bundles
        'app.min.1a2b3c.js',                 # webpack/vite/sprockets digest
        'a.MIN.JS',                          # capitalization
        'a.bundle.css',
    ])
    def test_recognizes_minified(self, filename):
        from reveal.utils.path_utils import is_minified_filename
        assert is_minified_filename(filename), filename

    @pytest.mark.parametrize('filename', [
        'main.js', 'admin.js', 'determine.css',
        'mindmap.js',        # contains 'min' but not as a marker
        'runtime.abc123.js',  # hashed, but no min/bundle marker
    ])
    def test_does_not_over_match(self, filename):
        from reveal.utils.path_utils import is_minified_filename
        assert not is_minified_filename(filename), filename


class TestLocaleFanoutExemption:
    """Defect 3 — the exemption must survive nesting below the i18n root."""

    def _rows(self, paths):
        from reveal.adapters.classify import _apply_locale_fanout
        rows = [{'file': p, 'provenance': 'first_party'} for p in paths]
        _apply_locale_fanout(rows)
        return {r['file']: r['provenance'] for r in rows}

    def test_nested_first_party_locales_stay_first_party(self):
        """Rails nests as config/locales/<engine>/<area>/en.yml, so the
        immediate parent is 'admin', not 'locales'."""
        langs = ['en', 'fr', 'es', 'de', 'ru', 'ar', 'it', 'ja']
        paths = [f'config/locales/myapp/admin/{l}.yml' for l in langs]
        assert set(self._rows(paths).values()) == {'first_party'}

    def test_flat_first_party_locales_still_exempt(self):
        """The case that already worked must not regress."""
        langs = ['en', 'fr', 'es', 'de', 'ru', 'ar', 'it', 'ja']
        paths = [f'config/locales/{l}.yml' for l in langs]
        assert set(self._rows(paths).values()) == {'first_party'}

    def test_vendored_locales_are_still_reclassified(self):
        """The exemption must not swallow genuinely vendored translations."""
        langs = ['en', 'fr', 'es', 'de', 'ru', 'ar', 'it', 'ja']
        paths = [f'vendor/gem/locales/{l}.yml' for l in langs]
        assert set(self._rows(paths).values()) == {'vendor'}


class TestRankingAdaptersCarryProvenance:
    """Defect 1 — the field was absent entirely from both adapters."""

    @pytest.fixture
    def tree(self, tmp_path):
        vendor = tmp_path / 'app' / 'assets'
        vendor.mkdir(parents=True)
        core = tmp_path / 'app' / 'models'
        core.mkdir(parents=True)
        body = '\n'.join(f'    if x == {i}: return {i}' for i in range(30))
        (vendor / 'lib.min.js').write_text(
            'function v(x) {\n' + '\n'.join(
                f'  if (x === {i}) return {i};' for i in range(30)
            ) + '\n  return null;\n}\n'
        )
        (vendor / 'helper.py').write_text(f'def vendorfn(x):\n{body}\n    return None\n')
        (core / 'model.py').write_text(f'def corefn(x):\n{body}\n    return None\n')
        return tmp_path

    def _run(self, tree, uri):
        proc = subprocess.run(
            [sys.executable, '-m', 'reveal', uri, '--format', 'json'],
            capture_output=True, text=True, cwd=str(tree), timeout=600,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def test_ast_results_carry_provenance(self, tree):
        result = self._run(tree, 'ast://.?complexity>3')
        assert result['results'], 'fixture produced no results'
        assert all('provenance' in r for r in result['results'])
        assert 'minified' in {r['provenance'] for r in result['results']}

    def test_ast_discloses_that_ranking_is_unfiltered(self, tree):
        """Their fallback ask: if the tag isn't consulted for ranking, at
        least say so, with a count."""
        result = self._run(tree, 'ast://.?complexity>3')
        types = {w['type'] for w in result.get('meta', {}).get('warnings', [])}
        assert 'unfiltered_ranking' in types

    def test_calls_uncalled_entries_carry_provenance(self, tree):
        result = self._run(tree, 'calls://.?uncalled=true&type=function')
        assert result['entries'], 'fixture produced no uncalled entries'
        assert all('provenance' in e for e in result['entries'])
