"""A sibling tree-sitter recovered only by inserting a MISSING token is import-graph loss (BACK-2497).

Reported as "a broken Python sibling does not trigger I002's incomplete-index disclosure, a broken
.ts sibling does". Step 0 at c6f5e187 showed the split is not Python against TypeScript: the
import extractor records loss (``parse_failed``, diagnostics ``parse: partial``) only when the
tree holds an ERROR node (``has_parse_errors``). ``def f(:`` recovers as a well-typed function with
``(MISSING ")")`` and no ERROR node, and so do ``const x = (1;`` in JavaScript/TypeScript/TSX,
``$x = (1;`` in PHP and ``local x = (1`` in Lua. ``check`` already counts each such file as
"did not parse cleanly" (``_has_errors``), but the import graph took it as complete: I002 on the
clean file beside it exited 0 with no disclosure, and ``imports://?circular`` listed no failed file.
BACK-1826 makes a project-wide rule's unparsed index file exit 3 for every sibling.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.core.treesitter_compat import tree_has_recovery_artifacts
from reveal.registry import get_analyzer
from reveal.rules.imports.I002 import _graph_cache


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


# (broken file, clean sibling) per load-order language; each broken file recovers with a MISSING
# token and no ERROR node (asserted below, so a grammar upgrade that changes the shape is caught).
MISSING_ONLY = {
    'python': (('bad.py', 'def f(:\n'), ('good.py', 'import os\n')),
    'javascript': (('bad.js', 'const x = (1;\n'), ('good.js', 'export const y = 1;\n')),
    'typescript': (('bad.ts', 'const x = (1;\n'), ('good.ts', 'export const y = 1;\n')),
    'tsx': (('bad.tsx', 'const x = (1;\n'), ('good.tsx', 'export const y = 1;\n')),
    'php': (('bad.php', '<?php\n$x = (1;\n'), ('good.php', '<?php\n$y = 1;\n')),
    'lua': (('bad.lua', 'local x = (1\n'), ('good.lua', 'local y = 1\n')),
}

PY_ERROR = (('bad.py', 'import os\nx = (1\n'), ('good.py', 'import os\n'))
TS_ERROR = (('bad.ts', 'export const = ;\nimport {\n'), ('good.ts', 'export const x = 1;\n'))
RUST_BROKEN = (('bad.rs', 'fn f( {\n'), ('good.rs', 'fn g() -> i32 { 1 }\n'))


def _tree(root, files):
    root.mkdir()
    root = root.resolve()
    for name, text in files:
        (root / name).write_text(text, encoding='utf-8')
    return root


def _file_check(path):
    run = _run_reveal_direct('check', str(path), '--select', 'I002', '--format', 'json')
    data = json.loads(run.stdout)
    return run.returncode, data.get('scan_disclosures') or []


def _dir_check(root):
    run = _run_reveal_direct('check', str(root), '--select', 'I002', '--format', 'json')
    return run.returncode, json.loads(run.stdout)['summary']


def _circular(root):
    run = _run_reveal_direct(f'imports://{root}?circular', '--format', 'json')
    return run.returncode, json.loads(run.stdout)['metadata']


def _i002_parse_disclosures(disclosures):
    return [d for d in disclosures if d.startswith('I002: ') and 'parsed with errors' in d]


@pytest.mark.parametrize('lang', sorted(MISSING_ONLY))
def test_the_fixture_recovers_with_a_missing_token_and_no_error_node(tmp_path, lang):
    root = _tree(tmp_path / lang, MISSING_ONLY[lang])
    bad = str(root / MISSING_ONLY[lang][0][0])
    analyzer = get_analyzer(bad)(bad)
    assert not analyzer.has_parse_errors()
    assert tree_has_recovery_artifacts(analyzer.tree)


@pytest.mark.parametrize('lang', sorted(MISSING_ONLY))
def test_a_clean_file_beside_a_missing_only_sibling_is_an_incomplete_i002_scan(tmp_path, lang):
    root = _tree(tmp_path / lang, MISSING_ONLY[lang])
    code, disclosures = _file_check(root / MISSING_ONLY[lang][1][0])
    assert len(_i002_parse_disclosures(disclosures)) == 1, disclosures
    assert '1 file(s)' in _i002_parse_disclosures(disclosures)[0]
    assert code == 3


def test_a_directory_check_names_the_missing_only_python_file_in_the_i002_disclosure(tmp_path):
    root = _tree(tmp_path / 'py', MISSING_ONLY['python'])
    code, summary = _dir_check(root)
    assert summary['files_degraded'] == 1
    assert len(_i002_parse_disclosures(summary['scan_disclosures'])) == 1, summary['scan_disclosures']
    assert code == 3


@pytest.mark.parametrize('lang', ['python', 'typescript'])
def test_imports_circular_counts_the_missing_only_file_as_failed(tmp_path, lang):
    root = _tree(tmp_path / lang, MISSING_ONLY[lang])
    code, meta = _circular(root)
    bad = MISSING_ONLY[lang][0][0]
    assert meta['files_failed'] == [bad]
    assert meta['extraction_diagnostics'][bad]['parse']['status'] == 'partial'
    assert code == 3


# Controls: these hold before and after the fix.

def test_control_a_clean_python_directory_is_complete(tmp_path):
    root = _tree(tmp_path / 'clean', [('good.py', 'import os\n'), ('other.py', 'import good\n')])
    code, summary = _dir_check(root)
    assert summary['scan_disclosures'] == [] and summary['files_degraded'] == 0
    assert code == 0
    code, meta = _circular(root)
    assert meta['files_failed'] == [] and code == 0


@pytest.mark.parametrize('files', [PY_ERROR, TS_ERROR], ids=['python', 'typescript'])
def test_control_an_error_node_sibling_already_exits_3(tmp_path, files):
    root = _tree(tmp_path / 'err', files)
    code, disclosures = _file_check(root / files[1][0])
    assert len(_i002_parse_disclosures(disclosures)) == 1, disclosures
    assert code == 3
    code, meta = _circular(root)
    assert meta['files_failed'] == [files[0][0]] and code == 3


def test_control_a_broken_rust_sibling_takes_the_w_cap_3_note_path(tmp_path):
    root = _tree(tmp_path / 'rs', RUST_BROKEN)
    code, disclosures = _file_check(root / 'good.rs')
    assert _i002_parse_disclosures(disclosures) == []
    assert [d for d in disclosures if d.startswith('W-CAP-3') and 'rust (1)' in d], disclosures
    assert code == 0
