"""BACK-1261/BACK-1262: caveats documented in JSON must reach the text render.

"The JSON is honest; the .md is where caveats go missing. And the .md is what
humans and LLM readers actually read." Rendering was a per-template choice, so
it was uneven -- overview://'s Hotspots section printed "... and N more" while
its complex_functions section, in the same file, silently showed 5 of 97.
"""

import json
import subprocess
import sys

import pytest

_win_stdout_none = pytest.mark.skipif(
    sys.platform == 'win32',
    reason="BACK-1271: subprocess.run(capture_output=True).stdout comes back None "
           "on Windows CI for this call (clean returncode, empty/benign stderr -- "
           "not a reveal crash, root cause unconfirmed without Windows repro access)",
)

pytestmark = pytest.mark.component


def _run(cwd, *args):
    proc = subprocess.run(
        [sys.executable, '-m', 'reveal', *args],
        capture_output=True, text=True, cwd=str(cwd), timeout=600,
    )
    return proc


def _text(cwd, *args):
    """Like _run(...).stdout, but with a diagnosable failure instead of a bare
    TypeError when stdout comes back None (BACK-1271: seen on Windows CI only,
    root cause unconfirmed -- this surfaces returncode/stderr on the next hit)."""
    proc = _run(cwd, *args)
    assert proc.stdout is not None, (
        f'stdout was None (BACK-1271); returncode={proc.returncode!r} '
        f'stderr={proc.stderr!r}'
    )
    return proc.stdout


@pytest.fixture
def wide_tree(tmp_path):
    """Enough complex functions to trip overview's complex_functions cap."""
    src = tmp_path / 'src'
    src.mkdir()
    body = '\n'.join(f'    if x == {i}: return {i}' for i in range(15))
    for i in range(40):
        (src / f'mod_{i}.py').write_text(f'def fn{i}(x):\n{body}\n    return None\n')
    return tmp_path


@_win_stdout_none
def test_overview_text_discloses_truncation_the_json_reports(wide_tree):
    """The section rendered N rows with no indicator while meta.warnings said
    'showing 5 of 97'."""
    as_json = json.loads(_run(wide_tree, 'overview://.', '--format', 'json').stdout)
    warned = [
        w for w in as_json.get('meta', {}).get('warnings', [])
        if w.get('type') == 'truncated'
    ]
    if not warned:
        pytest.skip('fixture did not trigger truncation')

    text = _text(wide_tree, 'overview://.')
    assert 'Caveats' in text
    assert warned[0]['message'] in text


def test_ast_text_discloses_the_unfiltered_ranking_warning(tmp_path):
    """BACK-1266: ast:// gained an 'unfiltered_ranking' meta.warnings entry
    (BACK-1258, same session as this file's original fix) but the text
    renderer never called render_meta_warnings -- the JSON had the caveat,
    the default/human output silently dropped it. Same defect class this
    file exists to close, reintroduced in the same batch that closed it."""
    vendor = tmp_path / 'vendor'
    vendor.mkdir()
    (vendor / 'app.min.js').write_text(
        'function f(a,b,c,d,e,f){'
        'if(a){if(b){if(c){if(d){if(e){return f}}}}}return 0}\n'
    )
    as_json = json.loads(
        _run(tmp_path, 'ast://.?complexity>1', '--format', 'json').stdout
    )
    warned = [
        w for w in as_json.get('meta', {}).get('warnings', [])
        if w.get('type') == 'unfiltered_ranking'
    ]
    if not warned:
        pytest.skip('fixture did not trigger the unfiltered_ranking warning')

    text = _run(tmp_path, 'ast://.?complexity>1').stdout
    assert warned[0]['message'] in text


def test_ast_complexity_query_discloses_unweighted_metric(tmp_path):
    """B8-8 cheap fallback (2026-09-02): complexity is pure McCabe (decision-
    point count), not nesting-depth-weighted, so many flat branches score the
    same as one deeply nested branch at the same count. Only surfaced on a
    query that actually filters by complexity -- unfiltered browsing
    shouldn't repeat the caveat on every result."""
    (tmp_path / 'flat.py').write_text(
        'def f(x):\n' + '\n'.join(f'    if x == {i}: return {i}' for i in range(6)) + '\n'
    )
    as_json = json.loads(
        _run(tmp_path, 'ast://.?complexity>1', '--format', 'json').stdout
    )
    codes = [w.get('type') for w in as_json.get('meta', {}).get('warnings', [])]
    assert 'complexity_is_unweighted' in codes, as_json.get('meta')

    text = _run(tmp_path, 'ast://.?complexity>1').stdout
    assert 'nesting depth' in text

    unfiltered = json.loads(
        _run(tmp_path, 'ast://.?type=function', '--format', 'json').stdout
    )
    unfiltered_codes = [w.get('type') for w in unfiltered.get('meta', {}).get('warnings', [])]
    assert 'complexity_is_unweighted' not in unfiltered_codes


def test_patches_says_not_measured_rather_than_clean(tmp_path):
    """Patch detection is Python + jest/vitest only, so on a Ruby tree
    'No patch pressure groups found.' alone reads as a clean result for a
    question that was never asked."""
    (tmp_path / 'app.rb').write_text("class Foo\n  def bar\n    1\n  end\nend\n")
    text = _run(tmp_path, 'patches://.').stdout
    assert 'No patch pressure groups found' in text
    assert 'not measured' in text


def test_patches_prints_its_own_advisory_warning(tmp_path):
    """W-PATCHES-1 was in the JSON from the start and never rendered."""
    (tmp_path / 'app.rb').write_text("class Foo\nend\n")
    as_json = json.loads(_run(tmp_path, 'patches://.', '--format', 'json').stdout)
    codes = [w.get('code') for w in as_json.get('meta', {}).get('warnings', [])]
    assert 'W-PATCHES-1' in codes, as_json.get('meta')
    assert 'advisory' in _run(tmp_path, 'patches://.').stdout


@_win_stdout_none
def test_deps_text_carries_the_autoload_disclosure(tmp_path):
    """deps.json had autoload_regime from the start; all three sibling
    import-graph adapters printed it and deps:// alone did not."""
    (tmp_path / 'Gemfile').write_text("source 'https://rubygems.org'\ngem 'rails'\n")
    app = tmp_path / 'app' / 'models'
    app.mkdir(parents=True)
    (app / 'user.rb').write_text("class User\n  def name\n    'x'\n  end\nend\n")

    as_json = json.loads(_run(tmp_path, 'deps://.', '--format', 'json').stdout)
    regime = (as_json.get('base', {}).get('metadata', {}) or {}).get('autoload_regime')
    if not regime:
        pytest.skip('Rails autoload regime not detected on this fixture')

    text = _text(tmp_path, 'deps://.')
    assert regime['framework'] in text
    assert 'naming convention' in text


@_win_stdout_none
def test_deps_labels_ecosystem_only_on_a_mixed_stack(tmp_path):
    """BACK-1262: Python and npm packages interleaved in one usage-sorted list
    with nothing saying which is which. Single-stack output is unchanged."""
    api = tmp_path / 'api'
    web = tmp_path / 'web'
    api.mkdir()
    web.mkdir()
    (api / 'app.py').write_text('import pydantic\nimport fastapi\n')
    (web / 'App.tsx').write_text(
        "import React from 'react';\n"
        "import { Button } from '@mui/material';\n"
        "export const A = () => <Button/>;\n"
    )
    mixed = _text(tmp_path, 'deps://.')
    assert '[python]' in mixed and '[tsx]' in mixed, mixed

    single = _text(tmp_path, 'deps://api')
    assert '[python]' not in single, single


class TestEntrypointsTestFanIn:
    """BACK-1263: imports://?entrypoints defines an entry point as fan-in=0,
    which an ordinary pytest layout inverts — a production entry point imported
    by its own tests drops off the list, while leaf test files nothing imports
    flood the top sorted by fan-out, looking like a confident answer."""

    @pytest.fixture
    def tree(self, tmp_path):
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n')
        app = tmp_path / 'myapp'
        tests = tmp_path / 'tests'
        app.mkdir()
        tests.mkdir()
        (app / '__init__.py').write_text('')
        (app / 'worker.py').write_text(
            'def main():\n    return 1\n\n\n'
            'if __name__ == "__main__":\n    main()\n'
        )
        (tests / 'test_worker.py').write_text(
            'from myapp.worker import main\n\n\n'
            'def test_main():\n    assert main() == 1\n'
        )
        return tmp_path

    def _entries(self, tree):
        out = _run(tree, 'imports://.?entrypoints', '--format', 'json')
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)['entries']

    def test_real_entry_point_is_not_excluded_by_its_own_test(self, tree):
        entries = self._entries(tree)
        files = [e['file'] for e in entries]
        assert any(f.endswith('myapp/worker.py') for f in files), files

    def test_test_files_are_labelled_and_sorted_last(self, tree):
        entries = self._entries(tree)
        assert all('is_test' in e for e in entries)
        non_test = [i for i, e in enumerate(entries) if not e['is_test']]
        test = [i for i, e in enumerate(entries) if e['is_test']]
        if non_test and test:
            assert max(non_test) < min(test), entries

    def test_test_share_is_disclosed(self, tree):
        out = _run(tree, 'imports://.?entrypoints', '--format', 'json')
        meta = json.loads(out.stdout).get('metadata', {})
        types = {w.get('type') for w in meta.get('warnings', [])}
        assert 'test_files_in_entrypoints' in types, meta
