"""calls ?modules as a shim over imports ?importers (BACK-1054 item 2, slice S5; decisions Q4 and Q8).

calls ?modules built its module graph from call resolution: an edge existed only where a call in one
file resolved, through that file's imports, to a definition in another. An import whose names were
used without a call (a constant, an attribute, a class passed along) made no edge, so the graph was a
subset of the import edges (79 of 1,453 on celery, every one an import edge) and every edge carried a
call_count. Decision Q4 retires the mode to imports ?importers and drops call_count; Q8 keeps the old
answer shape until the cut. So the edges are now imports' edges: one per (importer, imported file)
under the requested directory, resolved there (``imports://<dir>?importers&scope=path``);
``&external`` widens it to importers from the whole project root (``scope=root``, the imports
default). Both spellings (``calls://P?modules``, ``reveal calls P --modules``) print the note naming
the replacement, and keep calls ?modules' exit codes: 0 complete (a file parsed with errors is
disclosed, not a loss, as before), 3 when a directory or file could not be read, 2 for a missing path.
"""
import json
import ntpath
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import index as calls_index
from reveal.adapters.calls.renderer import render_calls_structure
from reveal.adapters.imports import ImportsAdapter

pytestmark = [pytest.mark.component]


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


# The design's fx2 control: three relative imports of core.py, and only a.py calls into it. b.py
# reads a constant and c.py an attribute of the module, so call resolution saw one edge of three.
FX2 = {
    'pyproject.toml': '[project]\nname = "fx2"\n',
    'pkg/__init__.py': '',
    'pkg/core.py': 'def helper():\n    return 1\n\n\nVALUE = 2\n',
    'pkg/a.py': 'from .core import helper\n\n\ndef run():\n    return helper()\n',
    'pkg/b.py': 'from .core import VALUE\n\n\ndef show():\n    return VALUE\n',
    'pkg/c.py': 'from . import core\n\n\ndef go():\n    return core.VALUE\n',
}

# pkg/a.py imports core relatively; scripts/run.py, outside pkg, imports it absolutely: an importer
# from elsewhere in the project, which only &external (scope=root) counts.
OUTSIDE = {
    'pyproject.toml': '[project]\nname = "fx"\n',
    'pkg/__init__.py': '',
    'pkg/core.py': 'def helper():\n    return 1\n',
    'pkg/a.py': 'from .core import helper\n\n\ndef run():\n    return helper()\n',
    'scripts/run.py': 'from pkg.core import helper\n\nhelper()\n',
}

# bad.js imports a.js and does not parse (the fixture tests/test_dd_call_exit_contract_back2181.py uses).
PARTIAL = {
    'package.json': '{"name": "fx"}\n',
    'src/a.js': "import { b } from './b';\nexport const a = () => b;\n",
    'src/b.js': "import { a } from './a';\nimport fs from 'fs';\nexport const b = 1;\n",
    'src/bad.js': "import { a } from './a';\nfunction broken( {\n  return a;\n",
}


@pytest.fixture
def fx2(tmp_path):
    return _write(tmp_path / 'fx2', FX2)


def _edges(result, root: Path) -> set:
    """The answer's edges as (importer, imported) paths relative to *root*, '/'-spelled."""
    return {(Path(e['from']).relative_to(root).as_posix(), Path(e['to']).relative_to(root).as_posix())
            for e in result['edges']}


def _import_edges(directory: Path, query: str = 'importers&scope=path') -> set:
    """The edges imports ?importers counts under *directory*: (importer, imported), relative to it."""
    answer = ImportsAdapter(str(directory), query).get_structure()
    return {(os.path.normpath(src).replace(os.sep, '/'), entry['file'])
            for entry in answer['entries'] for src in entry['importers']}


def _json(*argv):
    result = _run_reveal_direct(*argv, '--format', 'json')
    return result, json.loads(result.stdout)


def _retired(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


# --- the edges are imports' edges ------------------------------------------------------------

def test_fx2_reports_every_import_edge_not_only_the_called_one(fx2):
    """Red on the old engine: one edge (a.py, the only file that calls into core.py), not three."""
    result = CallsAdapter(str(fx2), 'modules').get_structure()
    assert _edges(result, fx2) == {('pkg/a.py', 'pkg/core.py'), ('pkg/b.py', 'pkg/core.py'),
                                   ('pkg/c.py', 'pkg/core.py')}
    assert result['total_edges'] == 3 and result['total_nodes'] == 4


def test_the_edges_equal_imports_importers_under_the_requested_directory(fx2):
    """Every edge is an import edge and every import edge under the path is an edge, at the root and in a
    subdirectory; the comparison detects one dropped edge (positive control)."""
    for directory in (fx2, fx2 / 'pkg'):
        result = CallsAdapter(str(directory), 'modules').get_structure()
        edges = _edges(result, directory)
        expected = _import_edges(directory)
        assert edges == expected and len(expected) == 3
        assert edges - {sorted(expected)[0]} != expected


def test_the_answer_keeps_the_old_shape_without_call_count(fx2):
    """Q8 keeps the old fields; Q4 drops call_count (an import edge has no call count); the rule says
    what was counted."""
    result = CallsAdapter(str(fx2), 'modules').get_structure()
    assert result['type'] == 'calls_module_graph' and result['query'] == 'module_graph'
    assert result['path'] == fx2.as_posix()
    assert result['nodes'] == sorted({f for e in result['edges'] for f in (e['from'], e['to'])})
    assert all(set(edge) == {'from', 'to'} for edge in result['edges'])
    assert result['edges'] == sorted(result['edges'], key=lambda e: (e['from'], e['to']))
    rule = result['edge_rule']
    assert rule['lazy'] == 'include' and rule['scope'] == 'scanned_path'
    assert rule['text'].startswith('Rule: importers are files whose static imports resolve here')


def test_a_file_path_answers_for_its_directory_as_before(fx2):
    """calls ?modules on a file scanned the file's directory: the shim asks imports about the directory."""
    result = CallsAdapter(str(fx2 / 'pkg' / 'a.py'), 'modules').get_structure()
    assert result['path'] == (fx2 / 'pkg').as_posix()
    assert _edges(result, fx2 / 'pkg') == _import_edges(fx2 / 'pkg')


def test_no_self_edges(tmp_path):
    root = _write(tmp_path / 'p', {'app.py': 'from app import helper\n\n\ndef main():\n    helper()\n\n\n'
                                             'def helper():\n    pass\n'})
    result = CallsAdapter(str(root), 'modules').get_structure()
    assert [e for e in result['edges'] if e['from'] == e['to']] == []


def test_external_counts_importers_from_the_whole_project_root(tmp_path):
    """&external is scope=root: scripts/run.py imports pkg/core.py from outside the path. Without it,
    and with the old engine (which only read files under the path), that importer is not an edge."""
    root = _write(tmp_path / 'proj', OUTSIDE)
    inside = {('pkg/a.py', 'pkg/core.py')}
    plain = CallsAdapter(str(root / 'pkg'), 'modules').get_structure()
    assert _edges(plain, root) == inside
    wide = CallsAdapter(str(root / 'pkg'), 'modules&external').get_structure()
    assert _edges(wide, root) == inside | {('scripts/run.py', 'pkg/core.py')}
    assert wide['edge_rule']['scope'] == 'scan_root'
    assert _edges(wide, root) == {(f'pkg/{a}' if not a.startswith('..') else a[3:], f'pkg/{b}')
                                  for a, b in _import_edges(root / 'pkg', 'importers')}


def test_one_import_build_and_no_structure_walk(fx2, monkeypatch):
    """The shim builds the import graph once and never collects call structures (the old engine
    collected every file's structure and resolved every call)."""
    builds, walks = [], []
    real_build, real_collect = ImportsAdapter._build_graph, calls_index.collect_structures

    def build(self, *args, **kwargs):
        builds.append(args)
        return real_build(self, *args, **kwargs)

    def collect(*args, **kwargs):
        walks.append(args)
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_build_graph', build)
    monkeypatch.setattr(calls_index, 'collect_structures', collect)
    CallsAdapter(str(fx2), 'modules').get_structure()
    assert len(builds) == 1 and walks == []


# --- spellings, notes and exit codes ---------------------------------------------------------

def test_both_spellings_answer_the_same_and_print_the_note(fx2):
    uri, uri_doc = _json(f'calls://{fx2.as_posix()}?modules')
    cli, cli_doc = _json('calls', str(fx2), '--modules')
    for run, doc in ((uri, uri_doc), (cli, cli_doc)):
        assert run.returncode == 0, run.stderr
        assert run.stderr.count('deprecated') == 1, run.stderr
        assert 'imports://<path>?importers' in run.stderr
        assert [w['field'] for w in _retired(doc)] == ['param:calls.modules']
    strip = lambda doc: {k: v for k, v in doc.items() if k != 'meta'}  # noqa: E731
    assert strip(uri_doc) == {**strip(cli_doc), 'source': uri_doc['source']}
    assert len(uri_doc['edges']) == 3


def test_external_prints_its_own_note(tmp_path):
    root = _write(tmp_path / 'proj', OUTSIDE)
    run, doc = _json(f'calls://{(root / "pkg").as_posix()}?modules&external')
    assert run.returncode == 0, run.stderr
    assert run.stderr.count('deprecated') == 2
    assert [w['field'] for w in _retired(doc)] == ['param:calls.modules', 'param:calls.external']
    assert 'scope=root' in run.stderr


def test_other_calls_modes_print_no_note_and_keep_their_answer(fx2):
    """Negative control on a sibling path through the same adapter."""
    run, doc = _json(f'calls://{fx2.as_posix()}?callers=helper')
    assert run.returncode == 0 and 'deprecated' not in run.stderr and not _retired(doc)
    assert doc['type'] == 'calls_query' and doc['total_callers'] == 1


def test_a_file_parsed_with_errors_is_disclosed_and_still_exits_0(tmp_path):
    """calls ?modules exited 0 here (calls never treated a partial parse as loss), while imports exits 3
    (D6). The shim keeps 0 and discloses the file under the warning imports builds for it."""
    root = _write(tmp_path / 'partial', PARTIAL)
    run, doc = _json(f'calls://{(root / "src").as_posix()}?modules')
    assert run.returncode == 0, run.stderr
    (warning,) = [w for w in doc['meta']['warnings'] if w.get('type') == 'partial_parse']
    assert warning['files'] == ['bad.js'] and warning['count'] == 1
    assert ('a.js', 'b.js') in {(Path(e['from']).name, Path(e['to']).name) for e in doc['edges']}
    imports = _run_reveal_direct(f'imports://{(root / "src").as_posix()}?importers&scope=path', '--format', 'json')
    assert imports.returncode == 3  # positive control: the fixture is partial for imports


def test_an_unreadable_directory_exits_3_and_names_it(tmp_path, monkeypatch):
    root = _write(tmp_path / 'affected', {'entry.py': 'from leaf import leaf\n\nleaf()\n',
                                          'leaf.py': 'def leaf():\n    return 1\n',
                                          'included_child/hidden.py': 'from leaf import leaf\n'})
    child = root / 'included_child'
    real = os.scandir

    def scandir(directory):
        if Path(directory) == child:
            raise PermissionError(13, 'controlled included child loss', str(child))
        return real(directory)

    monkeypatch.setattr(os, 'scandir', scandir)
    run, doc = _json(f'calls://{root.as_posix()}?modules')
    assert run.returncode == 3, run.stderr
    (warning,) = [w for w in doc['meta']['warnings'] if w.get('type') == 'analysis_incomplete']
    assert warning['directories'] == ['included_child'] and warning['unit'] == 'directories'
    assert _edges(doc, root) == {('entry.py', 'leaf.py')}


def test_a_missing_path_exits_2(tmp_path):
    run = _run_reveal_direct(f'calls://{(tmp_path / "nope").as_posix()}?modules', '--format', 'json')
    assert run.returncode == 2


def test_mcp_reveal_query_carries_the_note(fx2):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    out = reveal_query(f'calls://{fx2.as_posix()}?modules')
    assert out.count('calls ?modules (--modules) is deprecated') == 1
    doc = json.loads(reveal_query(f'calls://{fx2.as_posix()}?modules', provenance=True))
    assert [w['field'] for w in _retired(doc)] == ['param:calls.modules'] and len(doc['edges']) == 3


# --- Windows output paths (BACK-2188) --------------------------------------------------------

def test_a_backslash_spelling_from_the_engine_is_written_with_slashes():
    """Every path the module graph writes (path, nodes, from, to) is '/'-spelled, whatever separator the
    importer answer and the directory carry (a Windows spelling, handed to the builder directly)."""
    answer = {'entries': [{'file': 'pkg\\core.py', 'fan_in': 2, 'importers': ['pkg\\a.py', '..\\scripts\\run.py']}],
              'edge_rule': {'text': 'Rule: x'}}
    data = calls_index.module_graph_from_importers(answer, 'C:\\proj\\src')
    written = [data['path'], *data['nodes'], *(f for e in data['edges'] for f in (e['from'], e['to']))]
    assert written and all('\\' not in f for f in written), written
    assert {(e['from'], e['to']) for e in data['edges']} == {
        ('C:/proj/src/pkg/a.py', 'C:/proj/src/pkg/core.py'), ('C:/proj/scripts/run.py', 'C:/proj/src/pkg/core.py')}


def test_dot_names_nodes_relative_to_the_path_with_slashes(monkeypatch, capsys):
    """The dot view shortens each node against the path; on Windows os.path.relpath answered
    'pkg\\a.py' (simulated with ntpath). The edge carries the old call_count, which the renderer now
    ignores, so the record renders on the old code too."""
    monkeypatch.setattr(os.path, 'relpath', ntpath.relpath)
    data = {'query': 'module_graph', 'path': 'C:/proj', 'nodes': ['C:/proj/pkg/a.py', 'C:/proj/pkg/b.py'],
            'edges': [{'from': 'C:/proj/pkg/a.py', 'to': 'C:/proj/pkg/b.py', 'call_count': 1}],
            'total_nodes': 2, 'total_edges': 1}
    render_calls_structure(data, 'dot')
    out = capsys.readouterr().out
    assert '"pkg/a.py" -> "pkg/b.py";' in out, out
