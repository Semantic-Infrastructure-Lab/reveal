"""Independent static PHP include truth; production scope enablement is separate."""
import shutil
import subprocess
from pathlib import Path

import pytest

from test_recall_gate import _repo, gate, oracles

pytestmark = pytest.mark.component
needs_php = pytest.mark.skipif(not shutil.which('php'), reason='optional native PHP tokenizer required')


def _oracle():
    oracle = oracles.ORACLES.get('php-token-static')
    assert oracle is not None, 'independent PHP import oracle is not registered'
    assert callable(oracle.lazy_only), 'PHP scope truth must score both lazy modes'
    return oracle


def _scope(root, files, **config):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return oracles.Scope(root.resolve(), root.resolve(),
                         [root / name for name in files if name != 'target.php'], config)


def test_php_oracle_is_opt_in_without_scheduled_population_or_product_promotion():
    _oracle()
    from reveal.analyzers.imports.resolution import IMPORT_RECALL_GATED
    assert 'php' not in IMPORT_RECALL_GATED


@needs_php
@pytest.mark.parametrize('body,local', [
    ("require_once __DIR__ . '/target.php';", False),
    ("if (false) { include(__DIR__ . '/target.php'); }", False),
    ("function f() { require __DIR__ . '/target.php'; }", True),
    ("class K { function m() { include_once __DIR__ . '/target.php'; } }", True),
    ("$v = 1; $f = function () use ($v) { require __DIR__ . '/target.php'; };", True),
    ("$f = fn() => include(__DIR__ . '/target.php');", True),
    ("$f = fn() => fn() => require __DIR__ . '/target.php';", True),
    ("function outer() { $f = function () { require __DIR__ . '/target.php'; }; }", True),
    ("$a = [fn() => 1, include __DIR__ . '/target.php'];", False),
    ("function f() {} require __DIR__ . '/target.php';", False),
    ("$f = fn() => 1; require __DIR__ . '/target.php';", False),
    ("$f = true ? fn() => 1 : include __DIR__ . '/target.php';", False),
    ("$f = fn() => true ? include __DIR__ . '/target.php' : null;", True),
    ("require (__DIR__ . ('/target.php'));", False),
    ('require __DIR__ . "/target.php";', False),
])
def test_native_lexical_scope_and_loader_forms(tmp_path, body, local):
    scope = _scope(tmp_path, {'target.php': '<?php\n', 'use.php': '<?php\n' + body})
    oracle = _oracle()
    edges, coverage = oracle.build(scope)
    assert edges == {'target.php': ['use.php']}
    assert oracle.lazy_only(scope) == ({'target.php': ['use.php']} if local else {})
    assert coverage['files'] == coverage['resolved_statements'] == 1
    assert coverage['php_version'] and coverage['oracle_digest'] and coverage['population_digest']


@needs_php
def test_mixed_pair_is_module_and_dirname_is_importer_anchored(tmp_path):
    scope = _scope(tmp_path, {
        'target.php': '<?php\n',
        'mixed.php': "<?php require __DIR__.'/target.php'; function f(){require __DIR__.'/target.php';}",
        'sub/local.php': "<?php function f(){require_once dirname(__DIR__).'/target.php';}",
    })
    oracle = _oracle()
    assert oracle.build(scope)[0] == {'target.php': ['mixed.php', 'sub/local.php']}
    assert oracle.lazy_only(scope) == {'target.php': ['sub/local.php']}


@needs_php
def test_fake_loaders_and_unsupported_targets_are_disclosed(tmp_path):
    scope = _scope(tmp_path, {
        'target.php': '<?php\n',
        'use.php': r'''<p>require 'target.php'</p><?php
// require 'target.php';
$s = "require 'target.php'";
$h = <<<'TEXT'
require 'target.php';
TEXT;
use Vendor\Thing;
require $runtime;
require __DIR__ . '/target.php' . $suffix;
require unknown(__DIR__) . '/target.php';
require UNKNOWN_CONSTANT . '/target.php';
require __DIR__ . '/missing.php';
require __DIR__ . '/../outside.php';
''',
    })
    oracle = _oracle()
    edges, coverage = oracle.build(scope)
    assert edges == oracle.lazy_only(scope) == {}
    assert coverage['import_statements'] == 6
    assert coverage['unsupported_expressions'] == 4
    assert coverage['unresolved_targets'] == 2


@needs_php
def test_plain_relative_literals_require_explicit_importer_relative_policy(tmp_path):
    scope = _scope(tmp_path, {'target.php': '<?php\n', 'use.php': "<?php require 'target.php';"})
    oracle = _oracle()
    assert oracle.build(scope)[0] == {}
    explicit = scope._replace(config={'literal_base': 'importer'})
    assert oracle.build(explicit)[0] == {'target.php': ['use.php']}


@needs_php
def test_namespaced_dirname_override_cannot_invent_an_edge(tmp_path):
    scope = _scope(tmp_path, {
        'target.php': '<?php\n',
        'sub/use.php': "<?php namespace N; function dirname($x) { return '/runtime'; } "
                       "require dirname(__DIR__).'/target.php';",
    })
    edges, coverage = _oracle().build(scope)
    assert edges == {}
    assert coverage['unsupported_expressions'] == 1


@needs_php
def test_imported_dirname_cannot_be_assumed_to_be_the_builtin(tmp_path):
    scope = _scope(tmp_path, {
        'target.php': '<?php\n',
        'sub/use.php': r"<?php use function Other\dirname; require dirname(__DIR__).'/target.php';",
    })
    edges, coverage = _oracle().build(scope)
    assert edges == {}
    assert coverage['unsupported_expressions'] == 1


@needs_php
def test_native_parse_failure_and_toolchain_mismatch_are_not_empty_answers(tmp_path):
    scope = _scope(tmp_path, {'use.php': '<?php function broken( {'})
    oracle = _oracle()
    with pytest.raises(RuntimeError, match='PHP.*oracle failed'):
        oracle.build(scope)
    with pytest.raises(RuntimeError, match='PHP.*oracle failed'):
        oracle.lazy_only(scope)
    (tmp_path / 'use.php').write_text('<?php\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='version mismatch'):
        oracle.build(scope._replace(config={'php_version': '0.0.0'}))


def test_missing_runtime_and_timeout_are_measurement_failures(tmp_path, monkeypatch):
    oracle = _oracle()
    scope = oracles.Scope(tmp_path, tmp_path, [], {})
    with monkeypatch.context() as patch:
        patch.setattr(oracles.shutil, 'which', lambda name: None)
        with pytest.raises(RuntimeError, match='PHP.*required'):
            oracle.build(scope)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(oracles.shutil, 'which', lambda name: 'php')
    monkeypatch.setattr(oracles.subprocess, 'run', timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        oracle.build(scope)


@needs_php
def test_existing_gate_scores_qualified_php_scope_and_requires_mode_review(tmp_path, monkeypatch):
    oracle = _oracle()
    root, entry = _repo(tmp_path, {
        'target.php': '<?php\n',
        'module.php': "<?php require __DIR__.'/target.php';",
        'local.php': "<?php function f(){require __DIR__.'/target.php';}",
        'mixed.php': "<?php require __DIR__.'/target.php'; function f(){require __DIR__.'/target.php';}",
    }, {'oracle': 'php-token-static', 'importer_dirs': ['.']})
    # Qualify union separately, then restore the scope callback to expose the gap.
    with monkeypatch.context() as patch:
        patch.setitem(oracles.ORACLES, 'php-token-static', oracle._replace(lazy_only=None))
        measured = gate.measure(entry, root)
    assert measured['oracle_edges'] == measured['hit_edges'] == 3
    assert measured['recall'] == measured['precision'] == 1
    scoped = gate.measure(entry, root)
    assert scoped['lazy']['only']['oracle_edges'] == scoped['lazy']['only']['hit_edges'] == 1
    assert scoped['lazy']['exclude']['oracle_edges'] == scoped['lazy']['exclude']['hit_edges'] == 2
    assert all(row['recall'] == row['precision'] == 1 for row in scoped['lazy'].values())
    failures = []
    gate._compare_modes('php', 'lazy', {'only': {'oracle_edges': 1}, 'exclude': {'oracle_edges': 2}}, {}, failures)
    assert failures == [
        'php: lazy=exclude baseline missing; review required',
        'php: lazy=only baseline missing; review required',
    ]
    scope = oracles.Scope(root, root, [root / name for name in ('module.php', 'local.php', 'mixed.php')], entry['recall'])
    edges, _ = oracle.build(scope)
    population = set(scope.importers)

    def rendered(mode, selected):
        return {'by_target': {root / 'target.php': {root / name for name in selected}},
                'partial_files': 0, 'edge_rule': {'scope': mode}}

    # Scoring-boundary controls, not a claim that production PHP has these facts.
    monkeypatch.setattr(gate, 'rendered_reverse_graph', lambda scan, cap, mode:
                        rendered(mode, ['local.php'] if mode == 'only' else ['module.php', 'mixed.php']))
    baseline = gate._measure_lazy(oracle, scope, edges, root, root, None, population)
    assert all(row['precision'] == row['recall'] == 1 for row in baseline.values())
    monkeypatch.setattr(gate, 'rendered_reverse_graph', lambda scan, cap, mode:
                        rendered(mode, ['module.php', 'local.php', 'mixed.php']))
    ignored = gate._measure_lazy(oracle, scope, edges, root, root, None, population)
    assert ignored['only']['extra_edges'] == 2
    assert ignored['exclude']['extra_edges'] == 1
    failures = []
    gate._compare_modes('php', 'lazy', ignored, baseline, failures)
    assert any('lazy=only precision dropped' in failure for failure in failures)
    assert any('lazy=exclude precision dropped' in failure for failure in failures)


@needs_php
def test_lost_importer_cannot_become_an_empty_clean_answer(tmp_path):
    scope = _scope(tmp_path, {'use.php': '<?php\n'})
    (tmp_path / 'use.php').unlink()
    with pytest.raises(RuntimeError, match='Importer missing'):
        _oracle().build(scope)


@needs_php
def test_native_oracle_does_not_load_or_execute_external_code():
    # Native tokens also guard oracle independence; comments/string mentions are harmless.
    probe = r'''
$tokens = token_get_all(stream_get_contents(STDIN));
$bad = [];
foreach ($tokens as $i => $t) {
    if (is_array($t) && in_array($t[0], [T_REQUIRE,T_REQUIRE_ONCE,T_INCLUDE,T_INCLUDE_ONCE,T_EVAL], true)) $bad[] = $t[1];
    if ($t === '`') $bad[] = 'backtick execution';
    if (is_array($t) && $t[0] === T_STRING && in_array(strtolower($t[1]),
        ['exec','shell_exec','system','passthru','popen','proc_open','call_user_func','call_user_func_array'], true)) $bad[] = $t[1];
    if (is_array($t) && $t[0] === T_VARIABLE) {
        $j = $i + 1;
        while (isset($tokens[$j]) && is_array($tokens[$j]) && $tokens[$j][0] === T_WHITESPACE) $j++;
        if (($tokens[$j] ?? null) === '(') $bad[] = 'variable call';
    }
}
echo json_encode($bad);
'''
    def violations(source):
        return subprocess.run(['php', '-r', probe], input=source, capture_output=True,
                              text=True, encoding='utf-8', check=True, timeout=30).stdout.strip()
    source = (Path(oracles.__file__).parent / 'oracles/php_import_oracle.php').read_text(encoding='utf-8')
    assert violations(source) == '[]'
    assert violations("<?php // require 'reveal';\n$s = 'reveal';") == '[]'
    for planted in ("require 'reveal';", "shell_exec('python -m reveal');", 'eval($source);', "$run('reveal');"):
        assert violations('<?php ' + planted) != '[]', planted
