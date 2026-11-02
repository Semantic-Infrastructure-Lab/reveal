"""Bounded literal Ruby loaders retain their graph and gain qualified lexical scope."""
import json
from dataclasses import asdict

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports import generic
from reveal.analyzers.imports.generic import LuaImportExtractor, RubyImportExtractor
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component


@pytest.mark.parametrize('loader', ['require', 'require_relative', 'load'])
@pytest.mark.parametrize('template,scope', [
    ('{call}\n', 'module'),
    ('class Example\n  {call}\nend\n', 'module'),
    ('module Example\n  {call}\nend\n', 'module'),
    ('class << self\n  {call}\nend\n', 'module'),
    ('def example\n  {call}\nend\n', 'local'),
    ('def self.example\n  {call}\nend\n', 'local'),
    ('def example\n  [1].each do\n    {call}\n  end\nend\n', 'local'),
    ('def example\n  [1].each {{ {call} }}\nend\n', 'local'),
])
def test_literal_loader_scope(tmp_path, loader, template, scope):
    path = tmp_path / 'source.rb'
    path.write_text(template.format(call=f"{loader} 'target'"), encoding='utf-8')
    [statement] = RubyImportExtractor().extract_imports(path)
    assert statement.scope == scope
    assert statement.dynamic is True
    assert statement.module_name == 'target'
    assert statement.skip_unused and statement.import_type == 'import'


@pytest.mark.parametrize('body', [
    "[1].each do\n  require_relative 'target'\nend\n",
    "[1].each { require_relative 'target' }\n",
    "define_method(:example) { require_relative 'target' }\n",
    "later = -> { require_relative 'target' }\n",
    'require "#{prefix}/suffix"\n',
    "require File.join('target', 'other')\n",
    "Kernel.require 'target'\n",
    "load 'target', true\n",
])
def test_unqualified_forms_keep_unknown_metadata(tmp_path, body):
    path = tmp_path / 'source.rb'
    path.write_text(body, encoding='utf-8')
    statements = RubyImportExtractor().extract_imports(path)
    assert statements  # preserve existing extraction rather than deleting unsupported evidence
    assert all(s.scope is None and s.dynamic is None for s in statements)


def test_scope_annotation_preserves_every_other_extracted_field(tmp_path, monkeypatch):
    path = tmp_path / 'source.rb'
    path.write_text("require_relative 'target'\ndef example\n  require('second')\nend\n", encoding='utf-8')
    extractor = RubyImportExtractor()
    actual = extractor.extract_imports(path)
    monkeypatch.setattr(RubyImportExtractor, '_call_to_import', generic._GenericTreeSitterImportExtractor._call_to_import)
    generic._IMPORTS_CACHE.clear()
    before = RubyImportExtractor().extract_imports(path)
    for old, new in zip(before, actual, strict=True):
        old_fields, new_fields = asdict(old), asdict(new)
        for field in ['scope', 'dynamic']:
            old_fields.pop(field)
            new_fields.pop(field)
        assert old_fields == new_fields


def test_generic_sibling_keeps_unknown_metadata(tmp_path):
    path = tmp_path / 'source.lua'
    path.write_text("local x = require('target')\n", encoding='utf-8')
    [statement] = LuaImportExtractor().extract_imports(path)
    assert statement.scope is None and statement.dynamic is None


def _tree(root, files):
    root.mkdir()
    root = root.resolve()
    for name, source in {'Gemfile': '', **files}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
    return root


def _query(root, query):
    out = _run_reveal_direct(f'imports://{to_posix(root)}?{query}&scope=path', '--format', 'json')
    return out, json.loads(out.stdout)


@pytest.mark.parametrize('mode,expected', [
    ('include', {'module.rb', 'local.rb', 'mixed.rb', 'unknown.rb'}),
    ('exclude', {'module.rb', 'mixed.rb', 'unknown.rb'}),
    ('only', {'local.rb'}),
])
def test_public_modes_preserve_mixed_and_unknown_pairs(tmp_path, mode, expected):
    root = _tree(tmp_path / 'project', {
        'target.rb': '# target\n',
        'module.rb': "require_relative 'target'\n",
        'local.rb': "def example\n  require_relative 'target'\nend\n",
        'mixed.rb': "require_relative 'target'\ndef example\n  require_relative 'target'\nend\n",
        'unknown.rb': "[1].each { require_relative 'target' }\ndef example\n require_relative 'target'\nend\n",
    })
    out, answer = _query(root, f'importers=target.rb&lazy={mode}')
    assert out.returncode == 0, out.stderr
    assert {row['file'] for row in answer['importers']} == expected
    assert answer['edge_rule']['unclassified_edges'] == 1
    assert answer['edge_rule']['unclassified_languages'] == ['ruby']


def test_convention_plus_local_pair_stays_unknown_and_not_local_only(tmp_path):
    root = _tree(tmp_path / 'project', {
        'app/models/widget.rb': 'class Widget\nend\n',
        'source.rb': "def example\n require_relative 'app/models/widget'\n Widget\nend\n",
    })
    out, include = _query(root, 'importers=app/models/widget.rb&lazy=include')
    assert out.returncode == 0, out.stderr
    assert len(include['importers']) == 1
    assert include['edge_rule']['unclassified_edges'] == 1
    out, only = _query(root, 'importers=app/models/widget.rb&lazy=only')
    assert out.returncode == 0 and only['importers'] == []
    out, exclude = _query(root, 'importers=app/models/widget.rb&lazy=exclude')
    assert out.returncode == 0 and len(exclude['importers']) == 1


@pytest.mark.parametrize('local_back_edge,default_count', [(True, 0), (False, 1)])
def test_cycle_default_and_explicit_union(tmp_path, local_back_edge, default_count):
    back = "require_relative 'a'\n"
    if local_back_edge:
        back = 'def example\n' + back + 'end\n'
    root = _tree(tmp_path / 'project', {'a.rb': "require_relative 'b'\n", 'b.rb': back})
    out, default = _query(root, 'circular')
    assert out.returncode == 0, out.stderr
    assert default['count'] == default_count
    out, union = _query(root, 'circular&lazy=include')
    assert out.returncode == 0 and union['count'] == 1


@pytest.mark.parametrize('mode', ['include', 'exclude', 'only'])
def test_partial_no_match_and_cap_disclosures_survive(tmp_path, mode):
    root = _tree(tmp_path / 'project', {
        'target.rb': '# target\n', 'unused.rb': '# unused\n',
        'source.rb': "def example\n require_relative 'target'\nend\n",
        'broken.rb': 'def broken( {{{',
    })
    out, partial = _query(root, f'importers&lazy={mode}')
    assert out.returncode == 3, out.stderr
    assert partial['metadata']['files_failed_count'] == 1
    out, empty = _query(root, f'importers=unused.rb&lazy={mode}')
    assert out.returncode == 3 and empty['count'] == 0 and empty['importers'] == []
    out = _run_reveal_direct(f'imports://{to_posix(root)}?importers=missing.rb&scope=path&lazy={mode}', '--format', 'json')
    assert out.returncode == 2
    out, capped = _query(root, f'importers&lazy={mode}&max_files=1')
    assert out.returncode == 3 and capped['metadata']['scan_budget']['capped']
    assert any(row['type'] == 'scan_capped' for row in capped['meta']['warnings'])


@pytest.mark.disk_cache
def test_scope_survives_cache_layers_and_file_edit(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    path = tmp_path / 'source.rb'
    path.write_text("def example\n require_relative 'target'\nend\n", encoding='utf-8')
    real = RubyImportExtractor._extract_imports_uncached
    calls = []
    def counted(self, *args):
        calls.append(1)
        return real(self, *args)
    monkeypatch.setattr(RubyImportExtractor, '_extract_imports_uncached', counted)
    cold = RubyImportExtractor().extract_imports(path)
    cold[0].scope = 'poison'
    warm = RubyImportExtractor().extract_imports(path)
    generic._IMPORTS_CACHE.clear()
    disk = RubyImportExtractor().extract_imports(path)
    assert len(calls) == 1
    assert warm[0].scope == disk[0].scope == 'local'
    assert warm[0].dynamic is disk[0].dynamic is True
    generic._IMPORTS_CACHE.clear()
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    cache_off = RubyImportExtractor().extract_imports(path)
    assert len(calls) == 2 and asdict(cache_off[0]) == asdict(warm[0])
    path.write_text("module Example\n require_relative 'target'\nend\n", encoding='utf-8')
    edited = RubyImportExtractor().extract_imports(path)
    assert len(calls) == 3 and edited[0].scope == 'module'
