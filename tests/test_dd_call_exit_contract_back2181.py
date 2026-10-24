"""The exit codes and JSON shape of the two calls a due-diligence scan script makes (BACK-2181).

The script runs exactly ``reveal deps "$TARGET" --format json --provenance`` (its output piped
through ``jq 'del(.base.files)'``) and ``reveal "depends://${TARGET}/${MODULE}"`` (the module is
optional, so the directory form too), and logs any non-zero exit as FAILED. While deps://,
depends:// and calls?modules fold into imports:// (BACK-1054) the old spellings are shims that keep
their old shapes (decision Q8), and the exit code is part of that shape. The two commands do NOT
share one rule today, and these tests pin each as it is, measured on the pre-shim build:

- ``deps`` exits 3 when a required component is incomplete (a file parsed with errors) and 0 when
  it is complete; ``--fail-on`` defaults to none, so cycles and unused imports alone exit 0.
- ``depends://`` exits 0 on the same partial input, where ``imports://`` exits 3 (D6): its
  partial verdict is a warning, never the exit code. The depends shim (slice S6) must keep that.

The partial input is a JavaScript file tree-sitter cannot parse; ``imports://`` exiting 3 on it is
the positive control that the fixture really is partial.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = [pytest.mark.component]


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


# a.js and b.js import each other (one cycle); bad.js imports a.js and does not parse.
PARTIAL = {
    'package.json': '{"name": "fx"}\n',
    'src/a.js': "import { b } from './b';\nexport const a = () => b;\n",
    'src/b.js': "import { a } from './a';\nimport fs from 'fs';\nexport const b = 1;\n",
    'src/bad.js': "import { a } from './a';\nfunction broken( {\n  return a;\n",
}
CLEAN = {name: text for name, text in PARTIAL.items() if name != 'src/bad.js'}


@pytest.fixture
def partial(tmp_path):
    return _write(tmp_path / 'partial', PARTIAL)


@pytest.fixture
def clean(tmp_path):
    return _write(tmp_path / 'clean', CLEAN)


def _deps(target: Path):
    """The script's first call, as typed."""
    return _run_reveal_direct('deps', str(target), '--format', 'json', '--provenance')


def _depends(target: Path, module: str = ''):
    """The script's second call, as typed (text output)."""
    return _run_reveal_direct(f'depends://{target}/{module}')


def _without_base_files(doc: dict) -> dict:
    """``jq 'del(.base.files)'``: fails when ``base`` is not an object."""
    assert isinstance(doc['base'], dict) and isinstance(doc['base']['files'], dict)
    return {**doc, 'base': {k: v for k, v in doc['base'].items() if k != 'files'}}


def test_imports_exits_3_on_the_partial_fixture(partial):
    """Positive control: the fixture is partial for the one engine (D6)."""
    result = _run_reveal_direct(f'imports://{partial}/src/a.js?importers', '--format', 'json')
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['metadata']['files_failed_count'] == 1


def test_deps_exits_3_on_partial_input_with_its_json_shape(partial):
    result = _deps(partial / 'src')
    assert result.returncode == 3, result.stderr
    doc = _without_base_files(json.loads(result.stdout))
    assert doc['type'] == 'deps_scan'
    assert {'path', 'base', 'circular', 'unused', 'skipped', 'analysis', 'execution'} <= set(doc)
    assert doc['analysis']['complete'] is False
    assert doc['analysis']['components']['base']['files_failed_count'] == 1
    assert doc['execution']['reveal_version']  # --provenance


def test_deps_exits_0_on_complete_input_with_findings(clean):
    """Cycles and unused imports alone are not a failure: --fail-on defaults to none."""
    result = _deps(clean / 'src')
    assert result.returncode == 0, result.stderr
    doc = _without_base_files(json.loads(result.stdout))
    assert doc['analysis']['complete'] is True
    assert doc['analysis']['findings']['circular'] == 1


@pytest.mark.parametrize('module', ['src/a.js', 'src', ''])
def test_depends_exits_0_on_partial_input(partial, module):
    """The partial verdict is not depends' exit code (the S6 shim must keep this)."""
    result = _depends(partial, module)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_depends_still_lists_the_importer_that_did_not_parse(partial):
    """Exit 0 is not an empty answer: bad.js's import of a.js precedes its parse error."""
    result = _depends(partial, 'src/a.js')
    assert 'src/b.js' in result.stdout and 'src/bad.js' in result.stdout


def test_depends_exits_0_on_complete_input(clean):
    assert _depends(clean, 'src/a.js').returncode == 0


# --- the depends shim (BACK-1054 slice S6): depends answers from the imports:// engine's build ---
# The engine's own verdict on the same input is exit 3 (test_imports_exits_3_on_the_partial_fixture);
# depends keeps exit 0 and puts the partial verdict in meta.warnings, its `warning` string and the
# text, with its old JSON shape and the one retired-spelling note.

DEPENDENT_KEYS = {'file', 'line', 'module', 'names', 'type', 'is_relative', 'alias'}
NOTE = 'note: depends:// is deprecated; use imports://<path>?importers'


def _depends_json(target: Path, module: str = ''):
    return _run_reveal_direct(f'depends://{target}/{module}', '--format', 'json')


def _warning_types(doc: dict) -> set:
    return {w.get('type') or w.get('code') for w in (doc.get('meta') or {}).get('warnings', [])}


def test_depends_json_exits_0_with_the_partial_verdict_in_meta_warnings(partial):
    result = _depends_json(partial, 'src/a.js')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['type'] == 'module_dependents'
    assert {'target', 'dependents', 'count', 'edge_rule', 'metadata', '_meta', 'undercount_possible'} <= set(doc)
    assert all(set(d) == DEPENDENT_KEYS for d in doc['dependents'])  # no imports-only row field leaks in
    assert sorted(d['file'] for d in doc['dependents']) == ['src/b.js', 'src/bad.js']
    assert {'partial_parse', 'retired_spelling'} <= _warning_types(doc)
    assert 'parsed with errors' in doc['warning']
    assert result.stderr.count(NOTE) == 1


def test_depends_directory_json_exits_0_with_its_shape(partial):
    result = _depends_json(partial, 'src')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['type'] == 'dependency_summary'
    assert {'modules', 'total_modules', '_format', 'edge_rule', 'metadata', '_meta'} <= set(doc)
    assert all(set(m) == {'module', 'dependent_count', 'dependents'} for m in doc['modules'])
    assert 'partial_parse' in _warning_types(doc)


def test_depends_text_names_the_partial_verdict(partial):
    result = _depends(partial, 'src/a.js')
    assert 'parsed with errors' in result.stdout
    assert result.stderr.count(NOTE) == 1


def test_depends_exits_0_on_a_capped_walk_where_imports_exits_3(clean, monkeypatch):
    """A walk its file cap cut short is partial too: imports exits 3 (D6), depends 0 with
    scan_capped and its cap warning."""
    from reveal.adapters.depends import DependsAdapter
    monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 1)
    engine = _run_reveal_direct(f'imports://{clean}/src/a.js?importers&max_files=1', '--format', 'json')
    assert engine.returncode == 3, engine.stderr
    result = _depends_json(clean, 'src/a.js')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['metadata']['scan_capped'] is True
    assert 'Scan capped at 1 files' in doc['warning']


def test_mcp_depends_answers_with_the_note(partial):
    """The MCP spelling: the answer, not a failure, with the note in the result."""
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    out = reveal_query(f'depends://{partial}/src/a.js')
    assert 'src/bad.js' in out and 'parsed with errors' in out
    assert out.count('depends:// is deprecated; use imports://<path>?importers') == 1
    doc = json.loads(reveal_query(f'depends://{partial}/src/a.js', provenance=True))
    assert doc['type'] == 'module_dependents' and 'retired_spelling' in _warning_types(doc)
