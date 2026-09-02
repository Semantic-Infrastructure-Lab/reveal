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


class TestAiVendorSdkDetection:
    """BACK-1260: surface://'s sdk catalog missed every Google AI SDK, and its
    matcher only ever compared the ROOT path segment — so the multi-segment
    'google.cloud' entry that had been in the catalog all along was dead
    config, since the root of any google import is always 'google'."""

    @pytest.mark.parametrize('source,expected', [
        ('from google import genai\n', 'google.genai'),
        ('import vertexai\n', 'vertexai'),
        ('from google.generativeai import GenerativeModel\n',
         'google.generativeai.GenerativeModel'),
        ('from google.cloud import storage\n', 'google.cloud.storage'),
    ])
    def test_ai_vendor_sdks_are_detected(self, tmp_path, source, expected):
        from reveal.adapters.ast.nav_surface import scan_file_surface
        f = tmp_path / 'client.py'
        f.write_text(source)
        names = [e['name'] for e in scan_file_surface(str(f))['sdk']]
        assert expected in names, names

    @pytest.mark.parametrize('source', [
        'from google import protobuf\n',
        'from googleapiclient import discovery\n',
    ])
    def test_unrelated_google_packages_are_not_claimed(self, tmp_path, source):
        """A bare 'google' catalog entry would over-claim these."""
        from reveal.adapters.ast.nav_surface import scan_file_surface
        f = tmp_path / 'client.py'
        f.write_text(source)
        assert scan_file_surface(str(f))['sdk'] == []


class TestSpecDirIsAmbiguousForDocuments:
    """BACK-1264: 'spec'/'specs' names two different things — an RSpec test
    tree and a directory of specification documents. BACK-1251 made that call
    for the filename ('spec.md' is a requirements doc); the directory kept the
    test reading, so an openspec/ tree read as 205 test files on camaleon-cms.
    You cannot write an RSpec example in Markdown."""

    @pytest.mark.parametrize('parts,filename,expected', [
        # Specification documents — not tests.
        (('openspec', 'changes', 'x', 'specs', 'cap'), 'spec.md', None),
        (('openspec', 'specs'), 'spec.md', None),
        (('docs', 'specs'), 'api.md', None),
        # Real test trees — still tests, including their support documents.
        (('spec', 'support', 'fixtures'), 'plan.md', 'test'),
        (('specs', 'feature-x'), 'spec.md', 'test'),
        (('packages', 'web', 'spec'), 'notes.md', 'test'),   # monorepo
        (('tests', 'docs'), 'plan.md', 'test'),              # 'tests' is unambiguous
        # Code is unaffected at any depth — only documents are ambiguous.
        (('spec',), 'user_spec.rb', 'test'),
        (('openspec', 'changes', 'x', 'specs'), 'helper_spec.rb', 'test'),
    ])
    def test_classification(self, parts, filename, expected):
        from reveal.utils.path_utils import classify_path_provenance
        assert classify_path_provenance(parts, filename) == expected


class TestUncalledPrecision:
    """BACK-1265: calls://?uncalled measured at 10% precision on an external
    random sample (2 true positives in 20). Each fixture below is one of the
    reported mechanisms; all six were false positives before the fix."""

    @pytest.fixture
    def tree(self, tmp_path):
        (tmp_path / 'app.py').write_text(
            'import threading\n'
            '\n'
            '\n'
            'class App:\n'
            '    def get(self, path):\n'
            '        def deco(fn):\n'
            '            return fn\n'
            '        return deco\n'
            '\n'
            '\n'
            'app = App()\n'
            '\n'
            '\n'
            'def main_entry():\n'
            '    return 1\n'
            '\n'
            '\n'
            'def thread_body():\n'
            '    return 2\n'
            '\n'
            '\n'
            'def kwarg_cb():\n'
            '    return 3\n'
            '\n'
            '\n'
            'def attr_cb():\n'
            '    return 4\n'
            '\n'
            '\n'
            'def really_dead():\n'
            '    return 99\n'
            '\n'
            '\n'
            '@app.get("/items")\n'
            'def list_items():\n'
            '    return []\n'
            '\n'
            '\n'
            'def start(sink):\n'
            '    threading.Thread(target=thread_body).start()\n'
            '    sink(func=kwarg_cb)\n'
            '    sink.side_effect = attr_cb\n'
            '\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    main_entry()\n'
        )
        return tmp_path

    def _uncalled(self, tree):
        from reveal.adapters.calls.index import find_uncalled
        return {e['name'] for e in find_uncalled(str(tree))['entries']}

    @pytest.mark.parametrize('name,mechanism', [
        ('main_entry', 'called at module level under an __main__ guard'),
        ('thread_body', 'passed by reference as Thread(target=...)'),
        ('kwarg_cb', 'passed by reference as a keyword argument'),
        ('attr_cb', 'assigned to an attribute'),
        ('list_items', 'registered by a framework route decorator'),
    ])
    def test_referenced_functions_are_not_reported_dead(self, tree, name, mechanism):
        assert name not in self._uncalled(tree), mechanism

    def test_genuinely_dead_code_is_still_reported(self, tree):
        """The fix errs toward 'referenced', so this guards the other side."""
        assert 'really_dead' in self._uncalled(tree)
