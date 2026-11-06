"""PHP tags and rendered lazy views share the independently qualified scope rule."""
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports import generic
from reveal.analyzers.imports.generic import DartImportExtractor, PhpImportExtractor
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component


@pytest.mark.parametrize('body,scope', [
    ("require 'target.php';", 'module'),
    ("require_once __DIR__.'/target.php';", 'module'),
    ("if (false) { include_once __DIR__.'/target.php'; }", 'module'),
    ("function f() { require 'target.php'; }", 'local'),
    ("class K { function m() { include(__DIR__.'/target.php'); } }", 'local'),
    ("$f = function() { require_once __DIR__.'/target.php'; };", 'local'),
    ("$v = 1; $f = function() use ($v) { include_once __DIR__.'/target.php'; };", 'local'),
    ("$f = fn() => include __DIR__.'/target.php';", 'local'),
    ("function outer() { $f = function() { require __DIR__.'/target.php'; }; }", 'local'),
    ("$f = function() {}; require __DIR__.'/target.php';", 'module'),
    ("$f = fn() => 1; require __DIR__.'/target.php';", 'module'),
])
def test_loader_scope_and_dynamic_meaning(tmp_path, body, scope):
    path = tmp_path / 'use.php'
    path.write_text('<?php\n' + body, encoding='utf-8')
    [statement] = PhpImportExtractor().extract_imports(path)
    assert statement.scope == scope
    assert statement.dynamic is True  # loader expression, regardless of static path resolution
    assert statement.import_type == 'include' and statement.skip_unused


def test_namespace_declaration_is_not_a_dynamic_loader(tmp_path):
    path = tmp_path / 'use.php'
    path.write_text('<?php namespace N; use Vendor\\Thing;', encoding='utf-8')
    [statement] = PhpImportExtractor().extract_imports(path)
    assert statement.scope == 'module'
    assert statement.dynamic is False


def test_constant_concatenation_keeps_resolution_and_receives_scope(tmp_path):
    path = tmp_path / 'use.php'
    path.write_text("<?php function f() { require BASE . '/target.php'; }", encoding='utf-8')
    [statement] = PhpImportExtractor().extract_imports(path, {'BASE': ('absolute', to_posix(tmp_path))})
    assert statement.scope == 'local' and statement.dynamic is True
    assert Path(statement.module_name) == tmp_path / 'target.php'
    assert statement.through_constant


def test_unmigrated_generic_language_keeps_unknown_scope(tmp_path):
    path = tmp_path / 'use.dart'  # Lua records scope since BACK-2079; Dart does not
    path.write_text("import 'target.dart';\n", encoding='utf-8')
    [statement] = DartImportExtractor().extract_imports(path)
    assert statement.scope is None and statement.dynamic is None


@pytest.mark.disk_cache
def test_scope_is_part_of_the_cached_extraction_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    path = tmp_path / 'use.php'
    path.write_text("<?php $f = function() { require 'target.php'; };", encoding='utf-8')
    real = PhpImportExtractor._extract_imports_uncached
    calls = []

    def counted(self, *args):
        calls.append(1)
        return real(self, *args)

    monkeypatch.setattr(PhpImportExtractor, '_extract_imports_uncached', counted)
    cold = PhpImportExtractor().extract_imports(path)
    warm = PhpImportExtractor().extract_imports(path)
    generic._IMPORTS_CACHE.clear()
    disk = PhpImportExtractor().extract_imports(path)
    assert len(calls) == 1
    assert [asdict(s) for s in cold] == [asdict(s) for s in warm] == [asdict(s) for s in disk]
    assert cold[0].scope == 'local' and cold[0].dynamic is True


def _tree(root, files):
    root.mkdir()
    for name, text in {'composer.json': '{}', **files}.items():
        (root / name).write_text(text, encoding='utf-8')
    return root.resolve()


@pytest.mark.parametrize('mode,expected', [('include', 3), ('exclude', 2), ('only', 1)])
def test_mixed_pair_and_mode_counts_are_rendered_honestly(tmp_path, mode, expected):
    root = _tree(tmp_path / 'project', {
        'target.php': '<?php\n',
        'module.php': "<?php require __DIR__.'/target.php';",
        'local.php': "<?php $f = function() { require __DIR__.'/target.php'; };",
        'mixed.php': "<?php require __DIR__.'/target.php'; function f(){require __DIR__.'/target.php';}",
    })
    result = _run_reveal_direct(f'imports://{to_posix(root)}?rank=fan-in&lazy={mode}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['edge_rule'].get('unclassified_edges', 0) == 0
    assert 'php' not in answer['edge_rule'].get('unclassified_languages', [])
    assert next(row['fan_in'] for row in answer['entries'] if row['file'] == 'target.php') == expected


def test_local_back_edge_does_not_create_a_load_time_cycle(tmp_path):
    root = _tree(tmp_path / 'project', {
        'a.php': "<?php require __DIR__.'/b.php';",
        'b.php': "<?php $f = function() { require __DIR__.'/a.php'; };",
    })
    base = f'imports://{to_posix(root)}?circular'
    default = _run_reveal_direct(base, '--format', 'json')
    all_edges = _run_reveal_direct(base + '&lazy=include', '--format', 'json')
    assert default.returncode == all_edges.returncode == 0
    assert json.loads(default.stdout)['count'] == 0
    assert json.loads(all_edges.stdout)['count'] == 1


@pytest.mark.parametrize('mode', ['include', 'exclude', 'only'])
def test_partial_input_stays_incomplete_and_no_match_stays_invalid(tmp_path, mode):
    root = _tree(tmp_path / 'project', {
        'target.php': '<?php\n',
        'use.php': "<?php function f() { require __DIR__.'/target.php'; }",
        'broken.php': '<?php function broken( {{{',
    })
    result = _run_reveal_direct(f'imports://{to_posix(root)}?rank=fan-in&lazy={mode}', '--format', 'json')
    assert result.returncode == 3, result.stderr
    answer = json.loads(result.stdout)
    assert answer['metadata']['files_failed_count'] == 1
    missing = _run_reveal_direct(f'imports://{to_posix(root)}?importers=missing.php&lazy={mode}', '--format', 'json')
    assert missing.returncode == 2


@pytest.mark.skipif(not shutil.which('php'), reason='independent native PHP oracle required')
@pytest.mark.parametrize('wrong_scope,failed_mode', [('module', 'only'), ('local', 'exclude')])
def test_wrong_scope_fails_independent_modes_without_changing_union(tmp_path, monkeypatch, wrong_scope, failed_mode):
    from test_recall_gate import _repo, gate, oracles
    root, entry = _repo(tmp_path, {
        'target.php': '<?php\n',
        'module.php': "<?php require __DIR__.'/target.php';",
        'local.php': "<?php $f = function(){require __DIR__.'/target.php';};",
        'mixed.php': "<?php require __DIR__.'/target.php'; function f(){require __DIR__.'/target.php';}",
    }, {'oracle': 'php-token-static', 'importer_dirs': ['.']})
    baseline = gate.measure(entry, root)
    assert baseline['hit_edges'] == baseline['oracle_edges'] == 3
    assert all(row['recall'] == row['precision'] == 1 for row in baseline['lazy'].values())
    monkeypatch.setattr(generic, 'edge_scope', lambda node: wrong_scope)
    oracle = oracles.ORACLES['php-token-static']
    with monkeypatch.context() as patch:
        patch.setitem(oracles.ORACLES, 'php-token-static', oracle._replace(lazy_only=None))
        union = gate.measure(entry, root)
    assert union['hit_edges'] == union['oracle_edges'] == 3
    assert union['recall'] == union['precision'] == 1
    with pytest.raises(RuntimeError, match=f'lazy={failed_mode}: reveal found zero oracle edges'):
        gate.measure(entry, root)
