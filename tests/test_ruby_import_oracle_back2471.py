"""Opt-in native relative-loader truth, independent of Reveal parsing/resolution."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_recall_gate import _repo, gate, oracles

pytestmark = pytest.mark.component
RUBY = shutil.which(os.environ.get('REVEAL_RUBY_ORACLE', 'ruby'))
needs_ruby = pytest.mark.skipif(not RUBY, reason='optional native Ruby Ripper required')


def _oracle():
    oracle = oracles.ORACLES.get('ruby-ripper-relative')
    assert oracle is not None, 'bounded native Ruby oracle is not registered'
    assert callable(oracle.lazy_only)
    return oracle


def _scope(root, files, **config):
    root, entry = _repo(root, {'Gemfile': '', **files}, {
        'oracle': 'ruby-ripper-relative', 'importer_dirs': ['.'],
        'ruby_minimum_version': '3.0', **config,
    })
    importers = [root / name for name in files if name != 'target.rb']
    return oracles.Scope(root, root, importers, entry['recall']), entry


def test_ruby_oracle_is_opt_in_without_language_or_scheduled_promotion():
    _oracle()
    from reveal.analyzers.imports.resolution import IMPORT_RECALL_GATED
    assert 'ruby' not in IMPORT_RECALL_GATED
    manifest = (Path(oracles.__file__).parent.parent / 'tests/corpus/manifest.yaml').read_text(encoding='utf-8')
    assert 'ruby-ripper-relative' not in manifest


@needs_ruby
@pytest.mark.parametrize('template,local', [
    ('{call}\n', False),
    ('class Example\n {call}\nend\n', False),
    ('module Example\n {call}\nend\n', False),
    ('class << self\n {call}\nend\n', False),
    ('if false\n {call}\nend\n', False),
    ('def example\n {call}\nend\n', True),
    ('def self.example\n {call}\nend\n', True),
    ('def example\n [1].each do\n {call}\n end\nend\n', True),
    ('def example\n [1].each {{ {call} }}\nend\n', True),
    ('def example\n later = -> {{ {call} }}\nend\n', True),
])
@pytest.mark.parametrize('call', ["require_relative 'target'", 'require_relative("target.rb")'])
def test_native_named_method_and_body_scope(tmp_path, template, local, call):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': template.format(call=call)})
    edges, coverage = _oracle().build(scope)
    assert edges == {'target.rb': ['use.rb']}
    assert _oracle().lazy_only(scope) == ({'target.rb': ['use.rb']} if local else {})
    assert coverage['files'] == coverage['resolved_statements'] == 1
    assert coverage['ruby_version'] and coverage['ruby_description']
    assert coverage['population_digest'] and coverage['oracle_digest'] and coverage['config_digest']
    assert coverage['target_digests']['target.rb']
    [site] = coverage['sites']
    assert site['source'] == 'use.rb' and site['operation'] == 'require_relative'
    assert site['scope'] == ('local' if local else 'module')


@needs_ruby
def test_pair_scope_retains_mixed_and_known_literal_unknown_support(tmp_path):
    scope, _ = _scope(tmp_path, {
        'target.rb': '# target\n',
        'mixed.rb': "require_relative 'target'\ndef work\n require_relative 'target'\nend\n",
        'unknown.rb': "[1].each { require_relative 'target' }\ndef work\n require_relative 'target'\nend\n",
        'local.rb': "def work\n require_relative 'target'\nend\n",
    })
    edges, coverage = _oracle().build(scope)
    assert edges == {'target.rb': ['local.rb', 'mixed.rb', 'unknown.rb']}
    assert _oracle().lazy_only(scope) == {'target.rb': ['local.rb']}
    assert coverage['scope_unknown_statements'] == 1
    assert coverage['resolved_statements'] == 5


@needs_ruby
@pytest.mark.parametrize('source', [
    "[1].each do\n require_relative 'target'\nend\n",
    "define_method(:work) { require_relative 'target' }\n",
    "later = -> { require_relative 'target' }\n",
])
def test_standalone_ambiguous_context_has_static_pair_but_no_local_claim(tmp_path, source):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': source})
    edges, coverage = _oracle().build(scope)
    assert edges == {'target.rb': ['use.rb']}
    assert _oracle().lazy_only(scope) == {}
    assert coverage['scope_unknown_statements'] == 1
    assert coverage['sites'][0]['scope'] is None


@needs_ruby
@pytest.mark.parametrize('opaque', [
    'require_relative feature',
    'require_relative "#{prefix}/target"',
    "require_relative File.join('target', 'other')",
    "Kernel.require_relative 'target'",
    "require_relative 'target', true",
    'require_relative "tar\\x67et"',
    'load feature',
    'require_relative %q{target}',
    "require_relative %q'target'",
    'require_relative <<~PATH\n target\nPATH',
    "require 'target'",
])
def test_opaque_support_cannot_make_a_qualified_pair_local_only(tmp_path, opaque):
    scope, _ = _scope(tmp_path, {
        'target.rb': '# target\n',
        'use.rb': f"def work\n require_relative 'target'\nend\n{opaque}\n",
    })
    with pytest.raises(RuntimeError, match='unqualified loader.*use.rb'):
        _oracle().build(scope)


@needs_ruby
def test_external_loader_names_and_unresolved_relative_sites_stay_disclosed(tmp_path):
    scope, _ = _scope(tmp_path, {
        'target.rb': '# target\n',
        'use.rb': "require 'external_gem'\nload 'another.rb'\nrequire_relative 'missing'\n",
    })
    edges, coverage = _oracle().build(scope)
    assert edges == _oracle().lazy_only(scope) == {}
    assert coverage['import_statements'] == 3
    assert coverage['outside_relative_subset'] == 2
    assert coverage['unresolved_targets'] == 1


@needs_ruby
def test_parse_loss_version_mismatch_and_read_loss_are_not_zero_truth(tmp_path):
    scope, _ = _scope(tmp_path, {'use.rb': 'def broken( {{{'})
    with pytest.raises(RuntimeError, match='Ruby.*oracle failed.*parse failure'):
        _oracle().build(scope)
    (tmp_path / 'use.rb').write_text('# valid\n', encoding='utf-8')
    for config in ({}, {'ruby_minimum_version': '999.0'},
                   {'ruby_minimum_version': '3.0', 'ruby_version': '0.0.0'}):
        with pytest.raises(RuntimeError, match='Ruby.*oracle failed.*version'):
            _oracle().build(scope._replace(config=config))
    (tmp_path / 'use.rb').unlink()
    with pytest.raises(RuntimeError, match='Ruby.*oracle failed.*Importer'):
        _oracle().build(scope)


def test_missing_runtime_and_timeout_fail_measurement(tmp_path, monkeypatch):
    scope = oracles.Scope(tmp_path, tmp_path, [], {'ruby_minimum_version': '3.0'})
    with monkeypatch.context() as patch:
        patch.setattr(oracles.shutil, 'which', lambda name: None)
        with pytest.raises(RuntimeError, match='Ruby.*required'):
            _oracle().build(scope)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(oracles.shutil, 'which', lambda name: 'ruby')
    monkeypatch.setattr(oracles.subprocess, 'run', timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        _oracle().build(scope)


@needs_ruby
def test_native_parser_never_executes_corpus_or_target(tmp_path):
    sentinel = tmp_path / 'executed.txt'
    scope, _ = _scope(tmp_path, {
        'target.rb': 'raise "target must not execute"\n',
        'use.rb': "File.write('executed.txt', 'bad')\nrequire_relative 'target'\n",
    })
    assert _oracle().build(scope)[0] == {'target.rb': ['use.rb']}
    assert not sentinel.exists()


@needs_ruby
def test_ruby_startup_hooks_cannot_execute_corpus_code(tmp_path, monkeypatch):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': "require_relative 'target'\n"})
    hook = tmp_path / 'hook.rb'
    hook.write_text('raise "startup hook must not execute"\n', encoding='utf-8')
    (tmp_path / 'ripper.rb').write_text('raise "shadow parser must not execute"\n', encoding='utf-8')
    monkeypatch.setenv('RUBYOPT', '-r' + hook.as_posix())
    monkeypatch.setenv('RUBYLIB', str(tmp_path))
    monkeypatch.setenv('RUBYGEMS_GEMDEPS', '-')
    assert _oracle().build(scope)[0] == {'target.rb': ['use.rb']}


@needs_ruby
def test_tracked_target_loss_is_not_an_unresolved_clean_site(tmp_path):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': "require_relative 'target'\n"})
    (tmp_path / 'target.rb').unlink()
    with pytest.raises(RuntimeError, match='Target missing'):
        _oracle().build(scope)


@needs_ruby
@pytest.mark.parametrize('name', ['use.rb', 'target.rb'])
def test_native_source_and_target_identity_drift_refuses_measurement(tmp_path, monkeypatch, name):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': "require_relative 'target'\n"})
    real = oracles.subprocess.run
    def changed(command, **kwargs):
        result = real(command, **kwargs)
        if command[-1].endswith('ruby_import_oracle.rb'):
            (tmp_path / name).write_text('# changed after native parse\n', encoding='utf-8')
        return result
    monkeypatch.setattr(oracles.subprocess, 'run', changed)
    with pytest.raises(RuntimeError, match='changed during native measurement'):
        _oracle().build(scope)


@needs_ruby
def test_existing_gate_scores_relative_scope_and_rejects_ignored_filter(tmp_path, monkeypatch):
    scope, entry = _scope(tmp_path, {
        'target.rb': '# target\n',
        'module.rb': "require_relative 'target'\n",
        'local.rb': "def work\n require_relative 'target'\nend\n",
        'mixed.rb': "require_relative 'target'\ndef work\n require_relative 'target'\nend\n",
        'unknown.rb': "[1].each { require_relative 'target' }\ndef work\n require_relative 'target'\nend\n",
    })
    measured = gate.measure(entry, scope.root)
    assert measured['oracle_edges'] == measured['hit_edges'] == 4
    assert measured['lazy']['exclude']['oracle_edges'] == measured['lazy']['exclude']['hit_edges'] == 3
    assert measured['lazy']['only']['oracle_edges'] == measured['lazy']['only']['hit_edges'] == 1
    assert all(r['extra_edges'] == 0 for r in measured['lazy'].values())
    raw = gate._importers_request(scope.root, scope.scan, None)
    assert 'ruby' in raw['edge_rule']['ungated_languages']
    assert raw['edge_rule']['unclassified_edges'] == 1
    edges, _ = _oracle().build(scope)
    def ignored(scan, cap, mode):
        return {'by_target': {scope.root / 'target.rb': set(scope.importers)},
                'partial_files': 0, 'edge_rule': {'lazy': mode}}
    monkeypatch.setattr(gate, 'rendered_reverse_graph', ignored)
    wrong = gate._measure_lazy(_oracle(), scope, edges, scope.root, scope.scan, None, set(scope.importers))
    assert wrong['only']['extra_edges'] == 3
    assert wrong['exclude']['extra_edges'] == 1


@needs_ruby
def test_oracle_source_and_config_digests_change_without_mutating_other_oracles(tmp_path):
    scope, _ = _scope(tmp_path, {'target.rb': '# target\n', 'use.rb': "require_relative 'target'\n"})
    before = _oracle().build(scope)[1]
    (tmp_path / 'use.rb').write_text("def work\n require_relative 'target'\nend\n", encoding='utf-8')
    after = _oracle().build(scope._replace(config={**scope.config, 'declared_cohort': 'control'}))[1]
    assert before['population_digest'] != after['population_digest']
    assert before['config_digest'] != after['config_digest']
    assert before['oracle_digest'] == after['oracle_digest']
    assert oracles.ORACLES['python-ast'].build is oracles.build_python_oracle
    assert oracles.ORACLES['php-token-static'].build is oracles.build_php_oracle
