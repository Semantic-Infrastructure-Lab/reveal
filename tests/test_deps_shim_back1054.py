"""deps:// as a shim over the one imports:// engine (BACK-1054 item 2, slice S4).

deps composed imports:// three times per request (the default view, ?circular, ?unused), and
each child built the whole import graph again: three builds for one dashboard. Its package
table (unresolved and stdlib packages by use) was computed in the text renderer only, so JSON
had none of it, and imports:// had no findings gate. Now deps reads the three views from one
build, imports:// answers ``?external`` with the package table as JSON, ``--fail-on findings``
gates the imports views that report findings, and both deps spellings keep their old shapes and
exit codes while printing the note that names the replacement (decision Q8, D5).
"""
import json
import re
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.deps import DepsAdapter
from reveal.adapters.imports import ImportsAdapter

pytestmark = [pytest.mark.component]


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


# a and b import each other at load time (one cycle); b's imports are unused; c uses two
# third-party packages; os and json are stdlib.
PROJECT = {
    'pyproject.toml': '[project]\nname = "fx"\nversion = "0"\n',
    'pkg/__init__.py': '',
    'pkg/a.py': 'import os\nfrom pkg import b\n\n\ndef f():\n    return b.X, os.sep\n',
    'pkg/b.py': 'import json\nfrom pkg import a\n\nX = 1\n',
    'pkg/c.py': 'import requests\nimport yaml\nfrom pkg import a\n\nrequests.get(a.f, yaml)\n',
}
# The same project with the cycle and the unused imports removed: nothing for a gate to match.
NO_FINDINGS = {
    **PROJECT,
    'pkg/b.py': 'X = 1\n',
}


@pytest.fixture
def proj(tmp_path):
    return _write(tmp_path / 'proj', PROJECT)


@pytest.fixture
def no_findings(tmp_path):
    return _write(tmp_path / 'quiet', NO_FINDINGS)


@pytest.fixture
def builds(monkeypatch):
    """Every ImportsAdapter._build_graph call (one per graph build), by target."""
    calls = []
    original = ImportsAdapter._build_graph

    def counting(self, target_path, *args, **kwargs):
        calls.append(Path(target_path))
        return original(self, target_path, *args, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_build_graph', counting)
    return calls


# ── one build ─────────────────────────────────────────────────────────────────────────────────

def test_deps_builds_the_import_graph_once(proj, builds):
    result = DepsAdapter(str(proj)).get_structure()
    assert len(builds) == 1, builds  # was 3: the default view, ?circular and ?unused each built it
    assert result['analysis']['findings'] == {'circular': 1, 'unused': 2}


def test_the_deps_command_builds_the_import_graph_once(proj, builds):
    result = _run_reveal_direct('deps', str(proj), '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert len(builds) == 1, builds


@pytest.mark.parametrize('flags', [('--no-circular',), ('--no-unused',), ('--no-circular', '--no-unused')])
def test_a_skipped_component_does_not_change_the_one_build(proj, builds, flags):
    result = _run_reveal_direct('deps', str(proj), '--format', 'json', *flags)
    assert result.returncode == 0, result.stderr
    assert len(builds) == 1, builds


def _names(paths) -> list:
    return sorted(Path(p).name for p in paths)


def test_each_deps_component_is_the_imports_view_it_names(proj):
    """Negative control: one build answers what three did. Each component equals the imports://
    view it was composed from (scope=path), file for file."""
    deps = DepsAdapter(str(proj)).get_structure()
    base = ImportsAdapter(str(proj), 'scope=path').get_structure()
    circular = ImportsAdapter(str(proj), 'circular&scope=path').get_structure()
    unused = ImportsAdapter(str(proj), 'unused&scope=path').get_structure()
    assert {Path(f).name: len(v) for f, v in deps['base']['files'].items()} == \
        {Path(f).name: len(v) for f, v in base['files'].items()}
    assert [_names(group) for group in deps['circular']['cycles']] == [_names(group) for group in circular['cycles']]
    assert [(Path(u['file']).name, u['line'], u['module']) for u in deps['unused']] == \
        [(Path(u['file']).name, u['line'], u['module']) for u in unused['unused']]
    assert deps['base']['metadata']['total_imports'] == base['metadata']['total_imports'] == 7


def test_get_view_answers_like_a_fresh_adapter(proj):
    built = ImportsAdapter(str(proj), 'scope=path')
    built.get_structure()
    for view in ('circular', 'unused', 'rank=fan-in'):
        fresh = ImportsAdapter(str(proj), f'{view}&scope=path').get_structure()
        assert built.get_view(f'{view}&scope=path') == fresh, view


@pytest.mark.parametrize('query', ['circular', 'circular&scope=root', 'circular&scope=path&max_files=5',
                                   'circular&scope=path&root=.'])
def test_get_view_refuses_a_parameter_that_changes_the_build(proj, query):
    built = ImportsAdapter(str(proj), 'scope=path')
    built.get_structure()
    with pytest.raises(ValueError, match='cannot change the build'):
        built.get_view(query)


def test_get_view_needs_a_build(proj):
    with pytest.raises(ValueError, match='none was built'):
        ImportsAdapter(str(proj), 'scope=path').get_view('circular&scope=path')


def test_a_failed_build_fails_every_component_with_its_cause(proj, monkeypatch):
    def broken(self, target_path, *args, **kwargs):
        raise OSError('the tree went away')
    monkeypatch.setattr(ImportsAdapter, '_build_graph', broken)
    result = DepsAdapter(str(proj)).get_structure()
    assert {name: c['completeness'] for name, c in result['analysis']['components'].items()} == \
        {'base': 'failed', 'circular': 'failed', 'unused': 'failed'}
    messages = [e['message'] for e in result['meta']['errors']]
    assert any('the tree went away' in m for m in messages), messages
    assert _run_reveal_direct('deps', str(proj)).returncode == 3


# ── imports ?external: the package table as JSON ──────────────────────────────────────────────

def _packages(entries) -> dict:
    return {entry['package']: entry['uses'] for entry in entries}


def test_imports_external_answers_the_package_table_as_json(proj):
    result = _run_reveal_direct(f'imports://{proj}?external', '--format', 'json')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['type'] == 'external_packages'  # was 'imports': ?external was an unknown parameter
    assert _packages(doc['external_packages']) == {'requests': 1, 'yaml': 1}
    assert _packages(doc['stdlib_packages']) == {'os': 1, 'json': 1}
    assert [entry['languages'] for entry in doc['external_packages']] == [['python'], ['python']]
    assert doc['total_imports'] == 7 and doc['total_files'] == 3
    assert doc['internal_imports'] == 3  # from pkg import b / a / a: resolved in the tree


def test_the_imports_command_takes_external(proj):
    result = _run_reveal_direct('imports', str(proj), '--external', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['type'] == 'external_packages'


_PACKAGE_LINE = re.compile(r'^  (\S+)\s+(\d+) use\(s\)', re.M)


def test_external_json_holds_the_numbers_the_deps_text_prints(proj):
    """The deps dashboard printed its package table in text only; ?external at the same scan root
    (scope=path, as deps reads) gives the same numbers as JSON."""
    text = _run_reveal_direct('deps', str(proj)).stdout
    printed = {name: int(count) for name, count in _PACKAGE_LINE.findall(text)}
    doc = json.loads(_run_reveal_direct(f'imports://{proj}?external&scope=path', '--format', 'json').stdout)
    assert printed == _packages(doc['external_packages']) == {'requests': 1, 'yaml': 1}
    summary = re.search(r'(\d+) unresolved packages · (\d+) stdlib packages', text)
    assert summary and (int(summary[1]), int(summary[2])) == (len(doc['external_packages']),
                                                                len(doc['stdlib_packages']))


def test_imports_external_text_lists_the_packages(proj):
    result = _run_reveal_direct(f'imports://{proj}?external')
    assert result.returncode == 0, result.stderr
    assert 'requests' in result.stdout and 'yaml' in result.stdout and 'os' in result.stdout


# ── --fail-on on the imports views ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('view', ['--circular', '--unused'])
def test_imports_fail_on_findings_exits_1_on_a_view_with_findings(proj, view):
    result = _run_reveal_direct('imports', str(proj), view, '--scope', 'path', '--fail-on', 'findings')
    assert result.returncode == 1, result.stderr  # was 2: --fail-on findings was not supported


def test_imports_uri_takes_fail_on_findings(proj):
    result = _run_reveal_direct(f'imports://{proj}?circular&scope=path', '--fail-on', 'findings', '--format', 'json')
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)['count'] == 1


@pytest.mark.parametrize('argv', [
    ('--circular', '--fail-on', 'none'),          # the gate is off
    ('--circular',),                              # off by default
    ('--rank', 'fan-in', '--fail-on', 'findings'),  # a view with no findings to gate
    ('--external', '--fail-on', 'findings'),
])
def test_imports_exits_0_when_no_gate_matches(proj, argv):
    result = _run_reveal_direct('imports', str(proj), '--scope', 'path', *argv)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('view', ['--circular', '--unused'])
def test_imports_fail_on_findings_exits_0_without_findings(no_findings, view):
    result = _run_reveal_direct('imports', str(no_findings), view, '--scope', 'path', '--fail-on', 'findings')
    assert result.returncode == 0, result.stderr


def test_an_incomplete_answer_exits_3_before_a_findings_gate(tmp_path):
    """D6: incomplete beats findings, as deps' gate always did (a file that does not parse)."""
    proj = _write(tmp_path / 'partial', {**PROJECT, 'pkg/bad.py': 'from pkg import a\ndef broken(\n'})
    for command in (['imports', str(proj), '--circular', '--scope', 'path'], ['deps', str(proj)]):
        result = _run_reveal_direct(*command, '--fail-on', 'findings')
        assert result.returncode == 3, (command, result.stderr)


# ── the old spellings: same shapes and exit codes, plus the note ─────────────────────────────

def _retired(doc: dict) -> list:
    return [w['field'] for w in (doc.get('meta') or {}).get('warnings', []) if w.get('code') == 'retired_spelling']


@pytest.mark.parametrize('argv, key', [
    (lambda p: ['deps', str(p)], 'subcommand:deps'),
    (lambda p: [f'deps://{p}'], 'scheme:deps'),
])
def test_both_deps_spellings_print_the_note_naming_the_replacement(proj, argv, key):
    text = _run_reveal_direct(*argv(proj))
    assert text.returncode == 0, text.stderr
    notes = [line for line in text.stderr.splitlines() if 'deprecated' in line]
    assert len(notes) == 1 and 'external' in notes[0] and 'imports' in notes[0], notes
    assert 'Dependencies:' in text.stdout  # the old dashboard still answers
    doc = _run_reveal_direct(*argv(proj), '--format', 'json')
    assert doc.returncode == 0
    data = json.loads(doc.stdout)
    assert data['type'] == 'deps_scan' and _retired(data) == [key]
