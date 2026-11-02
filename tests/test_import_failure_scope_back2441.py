"""Qualify local unused-name verdicts and target-scoped completeness (BACK-2441)."""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


CASES = {
    'python': ('a.py', 'import os\nimport sys\nprint(sys.argv)\n', ['os'], 'broken.py', 'import os\nx = (\n'),
    'javascript': ('a.js', "import { used, spare } from '../lib.js';\nconsole.log(used);\n", ['spare'],
                   'broken.js', 'import { x ;\n const = ;;; }{\n'),
    'go': ('a.go', 'package app\nimport "fmt"\nimport "os"\nfunc Main() { fmt.Println("ok") }\n',
           ['os'], 'broken.go', 'package broken\nfunc Broken( {\n'),
    'typescript': ('a.ts', "import { used, spare } from '../lib.js';\nconsole.log(used);\n", ['spare'],
                   'broken.ts', 'import { x ;\n const = ;;; }{\n'),
    'rust': ('a.rs', 'use std::fmt;\nuse std::io;\nfn main() { io::stdin(); }\n', ['fmt'],
             'broken.rs', 'fn broken( {\n'),
}


def _write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _query(path, query='unused'):
    response = _run_reveal_direct(f'imports://{path}?{query}', '--format', 'json')
    return response.returncode, json.loads(response.stdout)


def _verdicts(result):
    return sorted((row['line'], row['module'], tuple(row['unused_names'])) for row in result['unused'])


@pytest.mark.parametrize('language', CASES)
def test_outside_parse_loss_does_not_change_local_unused_answer(tmp_path, language):
    filename, source, names, broken_name, broken_source = CASES[language]
    (tmp_path / '.git').mkdir()
    _write(tmp_path, 'go.mod', 'module example.invalid/project\ngo 1.21\n')
    _write(tmp_path, 'package.json', '{"name":"project"}\n')
    target = tmp_path / 'app'
    _write(target, filename, source)
    _write(tmp_path, 'lib.js', 'export const used = 1; export const spare = 2;\n')
    good_code, good = _query(target)
    assert good_code == 0
    assert good['metadata']['has_cycles'] is False
    assert [name for row in good['unused'] for name in row['unused_names']] == names
    _write(tmp_path, broken_name, broken_source)
    bad_code, bad = _query(target)
    assert bad_code == 0
    assert bad['metadata']['files_failed_count'] == 0
    assert bad['metadata']['files_failed_outside_target_count'] == 1
    assert bad['unused'] == good['unused']
    listing_code, listing = _query(target, '')
    assert listing_code == 0
    assert listing['metadata']['files_failed_outside_target_count'] == 1


def test_python_reexports_and_package_initializer_are_local_decisions(tmp_path):
    (tmp_path / '.git').mkdir()
    target = tmp_path / 'api'
    _write(target, '__init__.py', 'from outside import public\n')
    _write(target, 'exports.py', "from outside import public as public\nfrom outside import named\n__all__ = ['named']\nimport os\n")
    outside = _write(tmp_path, 'outside.py', 'public = 1\nnamed = 2\n')
    code, before = _query(target)
    assert code == 0
    assert [(r['file'], r['unused_names']) for r in before['unused']] == [('exports.py', ['os'])]
    outside.write_text('import os\nx = (\n', encoding='utf-8')
    code, after = _query(target)
    assert code == 0
    assert after['metadata']['files_failed_outside_target_count'] == 1
    assert _verdicts(after) == _verdicts(before)


def test_javascript_barrel_export_is_not_unused_even_if_outside_target_fails(tmp_path):
    (tmp_path / '.git').mkdir()
    target = tmp_path / 'api'
    _write(target, 'index.js', "export { publicName } from '../outside.js';\nimport spare from '../outside.js';\n")
    outside = _write(tmp_path, 'outside.js', 'export const publicName = 1; export default 2;\n')
    code, before = _query(target)
    assert code == 0
    assert [r['unused_names'] for r in before['unused']] == [['spare']]
    outside.write_text('import { x ;\n const = ;;; }{\n', encoding='utf-8')
    code, after = _query(target)
    assert code == 0
    assert after['metadata']['files_failed_outside_target_count'] == 1
    assert _verdicts(after) == _verdicts(before)


def test_in_target_parse_loss_remains_incomplete(tmp_path):
    (tmp_path / '.git').mkdir()
    target = tmp_path / 'app'
    _write(target, 'a.py', 'import os\n')
    _write(target, 'broken.py', 'import os\nx = (\n')
    code, result = _query(target)
    assert code == 3
    assert result['metadata']['files_failed_count'] == 1
    assert sorted((r['file'], r['unused_names']) for r in result['unused']) == [
        ('a.py', ['os']), ('broken.py', ['os'])]


def test_unsupported_unused_language_is_disclosed(tmp_path):
    (tmp_path / '.git').mkdir()
    _write(tmp_path, 'Example.java', 'import java.util.List;\nclass Example {}\n')
    code, result = _query(tmp_path)
    assert code == 0
    assert result['unused'] == []
    assert result['metadata']['unused_not_checked_extensions'] == {'.java': 1}


@pytest.mark.parametrize('location', ['outside', 'inside'])
def test_injected_source_read_loss_keeps_scoped_failure_visible(tmp_path, monkeypatch, location):
    """Synthetic PermissionError at the actual reader, distinct from real parse controls."""
    from pathlib import Path
    from reveal.base import FileAnalyzer

    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    (tmp_path / '.git').mkdir()
    target = tmp_path / 'app'
    _write(target, 'a.py', 'import os\n')
    denied = _write(target if location == 'inside' else tmp_path, 'other.py', 'import sys\n')
    original = FileAnalyzer._read_file

    def read(analyzer):
        if Path(analyzer.path).resolve() == denied.resolve():
            raise PermissionError(13, 'Permission denied', str(analyzer.path))
        return original(analyzer)

    monkeypatch.setattr(FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    code, result = _query(target)
    assert code == (3 if location == 'inside' else 0)
    assert result['metadata']['files_failed_count'] == int(location == 'inside')
    assert result['metadata']['files_failed_outside_target_count'] == int(location == 'outside')
    assert [r['unused_names'] for r in result['unused']] == [['os']]
    assert any(detail['parse']['status'] == 'unavailable'
               and 'Permission denied' in detail['parse']['reason']
               for detail in result['metadata']['extraction_diagnostics'].values())
    listing_code, listing = _query(target, '')
    assert listing_code == (3 if location == 'inside' else 0)
    assert listing['metadata']['files_failed_outside_target_count'] == (0 if location == 'inside' else 1)
