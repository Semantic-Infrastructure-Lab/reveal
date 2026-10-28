"""depends:// is a retired spelling over the one imports:// engine (BACK-1054 slice S6, Q8).

The graph depends answers from is the imports:// engine's build (``ImportsAdapter``: its walk,
per-file extraction, cascade and caches), under depends' own scan root, file cap and extension
family, and the answer keeps depends' shapes, warnings and exit code until the cut. The exit code
contract itself (0 where imports exits 3, BACK-2181) is pinned in
tests/test_dd_call_exit_contract_back2181.py.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path, PureWindowsPath

import pytest

from reveal.analyzers.imports import service as import_service

from reveal.analyzers.imports import extraction as import_extraction

from conftest import _run_reveal_direct
from reveal.adapters.depends import DependsAdapter
from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.resolution import ProjectResolution
from reveal.analyzers.imports.types import ImportAnalysis, ImportExtraction, ImportGraph, ImportStatement
from reveal.utils import path_utils

pytestmark = [pytest.mark.component]

NOTE = 'note: depends:// is deprecated; use imports://<path>?importers'


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


# A Python package with two importers of core.py, one of them inside a function, plus JavaScript
# beside it (another extension family: a .py target's walk leaves it out, BACK-525 layer 4).
MIXED = {
    'pyproject.toml': '[project]\nname = "fx"\n',
    'pkg/__init__.py': '',
    'pkg/core.py': 'VALUE = 1\n',
    'pkg/a.py': 'from pkg import core\n',
    'pkg/b.py': 'def f():\n    from pkg.core import VALUE\n    return VALUE\n',
    'web/one.js': "import { x } from './two';\n",
    'web/two.js': 'export const x = 1;\n',
    'web/three.js': "import { x } from './two';\n",
    'web/four.js': "import { x } from './two';\n",
}


@pytest.fixture
def mixed(tmp_path):
    return _write(tmp_path / 'mixed', MIXED)


@pytest.fixture
def builds(monkeypatch):
    """Every imports:// engine build: (target, parse_extensions) per ``_build_graph`` call."""
    calls = []
    real = ImportsAdapter._build_graph

    def counting(self, target_path, *args, **kwargs):
        calls.append((target_path, self._parse_extensions))
        return real(self, target_path, *args, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_build_graph', counting)
    return calls


@pytest.mark.parametrize('rel', ['pkg/core.py', 'pkg', ''])
def test_depends_builds_through_the_imports_engine_once(mixed, builds, rel):
    """One request, one engine build (the pre-S6 adapter walked and resolved on its own: 0 here)."""
    result = DependsAdapter(str(mixed / rel) if rel else str(mixed)).get_structure()
    assert 'error' not in result, result
    assert len(builds) == 1, builds


def test_a_file_target_builds_over_its_own_extension_family(mixed, builds):
    """BACK-525 layer 4 is kept: a .py target's engine build parses the Python family only."""
    DependsAdapter(str(mixed / 'pkg' / 'core.py')).get_structure()
    [(_target, family)] = builds
    assert '.py' in family and '.js' not in family


def test_a_directory_target_builds_over_every_supported_extension(mixed, builds):
    DependsAdapter(str(mixed)).get_structure()
    [(_target, family)] = builds
    assert {'.py', '.js'} <= family


def test_the_cap_counts_only_the_targets_family(mixed, monkeypatch):
    """depends' cap counts the files its walk keeps: 4 .py files under a cap of 4 do not cap,
    though the tree holds 8 source files (positive control: imports:// itself, which keeps every
    family, caps at 4)."""
    monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 4)
    result = DependsAdapter(str(mixed / 'pkg' / 'core.py')).get_structure()
    assert result['metadata']['scan_capped'] is False
    assert sorted(d['file'] for d in result['dependents']) == ['pkg/a.py', 'pkg/b.py']
    capped = ImportsAdapter(str(mixed / 'pkg' / 'core.py'), params={'importers': True, 'max_files': 4}).get_structure()
    assert capped['metadata']['scan_budget']['capped'] is True


def test_the_dependents_are_the_imports_importers(mixed):
    """depends' file answer lists the rows imports://?importers=FILE lists (one listing,
    resolution.file_importers), each with the same import line, names and type."""
    depends = DependsAdapter(str(mixed / 'pkg' / 'core.py')).get_structure()
    imports = ImportsAdapter(str(mixed), params={'importers': 'pkg/core.py'}).get_structure()
    fields = ('line', 'module', 'names', 'type', 'is_relative', 'alias')
    assert [(Path(d['file']).name, *(d[f] for f in fields)) for d in depends['dependents']] == \
        [(Path(r['file']).name, *(r[f] for f in fields)) for r in imports['importers']]
    assert depends['count'] == imports['count'] == 2


@pytest.mark.parametrize('rel', ['pkg/core.py', 'pkg'])
def test_each_spelling_prints_one_note_and_carries_the_warning(mixed, rel):
    text = _run_reveal_direct(f'depends://{mixed}/{rel}')
    assert text.returncode == 0, text.stderr
    assert text.stderr.count(NOTE) == 1, text.stderr
    out = _run_reveal_direct(f'depends://{mixed}/{rel}', '--format', 'json')
    assert out.returncode == 0, out.stderr
    doc = json.loads(out.stdout)
    retired = [w for w in doc['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert [(w['field'], w['old']) for w in retired] == [('scheme:depends', 'depends://')]
    assert 'imports://<path>?importers' in retired[0]['replacement']
    assert doc['type'] == ('module_dependents' if rel.endswith('.py') else 'dependency_summary')


def test_imports_prints_no_depends_note(mixed):
    """Negative control: the replacement spelling is not retired."""
    result = _run_reveal_direct(f'imports://{mixed}?importers=pkg/core.py')
    assert 'deprecated' not in result.stderr


def test_a_file_a_dead_worker_lost_is_disclosed(mixed, monkeypatch):
    """The engine extracts in a process pool on a large tree, and a file a dead worker took down has
    no imports, so its edges are missing: depends says so (the pre-S6 serial walk had no pool)."""
    real = import_extraction.extract_files

    def losing(candidates, want_structure, inputs=None):
        for row in real(candidates, want_structure, inputs):
            if row[0].name == 'a.py':
                lost = ImportExtraction(parse_failed=True, worker_lost=True)
                row = (row[0], None, None, None, lost, None, None)
            yield row

    monkeypatch.setattr(import_extraction, 'extract_files', losing)
    result = DependsAdapter(str(mixed / 'pkg' / 'core.py')).get_structure()
    assert [d['file'] for d in result['dependents']] == ['pkg/b.py']
    lost = [w for w in result.get('meta', {}).get('warnings', []) if 'worker' in w.get('message', '')]
    assert len(lost) == 1 and lost[0]['type'] == 'worker_lost', result.get('meta', {}).get('warnings', [])
    assert 'pkg/a.py' in json.dumps(lost[0])
    assert result['undercount_possible'] is True
    assert 'worker' in result['warning']


def test_without_a_lost_file_nothing_is_disclosed(mixed):
    """Negative control for the test above."""
    result = DependsAdapter(str(mixed / 'pkg' / 'core.py')).get_structure()
    assert not [w for w in result.get('meta', {}).get('warnings', []) if 'worker' in w.get('message', '')]
    assert result['undercount_possible'] is False and 'warning' not in result


@pytest.mark.disk_cache
@pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')
def test_a_cached_build_does_not_carry_another_requests_hidden_scope(tmp_path, monkeypatch):
    """The engine's graph cache is keyed by the walk, not the request's focus: a directory request
    whose target is all ignored, then one whose target is not, share one cached build. What the
    walk hid is judged by each request's own walk (BACK-2065/2075), never read from the cache."""
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True, timeout=60)
    _write(root, {'.gitignore': 'gen/\n', 'app/main.py': 'from app import util\n',
                  'app/util.py': 'def run():\n    return 1\n', 'gen/pkg/a.py': 'import os\n'})
    resolves = []
    real = import_service._process_extracted_files

    def counting(self, *args, **kwargs):
        resolves.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(import_service, '_process_extracted_files', counting)

    def hidden(result):
        return [w for w in result.get('meta', {}).get('warnings', []) if w.get('type') == 'scope_hidden']

    ignored = DependsAdapter(str(root / 'gen' / 'pkg')).get_structure()
    visible = DependsAdapter(str(root / 'app')).get_structure()
    assert len(resolves) == 1  # the second request was a cache hit
    assert len(hidden(ignored)) == 1
    assert hidden(visible) == [] and 'warning' not in visible
    assert {'module': 'app/util.py', 'dependent_count': 1, 'dependents': ['app/main.py']} in visible['modules']
    # Positive control: the same answer from a cold build.
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    cold = DependsAdapter(str(root / 'app')).get_structure()
    assert cold['modules'] == visible['modules'] and hidden(cold) == []


class _WindowsPath(PureWindowsPath):
    """A Windows spelling the shared serializer (path_utils.to_relative_display) can resolve on any
    OS: Linux cannot produce a backslash-separated path from a real tree (BACK-2188)."""

    def expanduser(self):
        return self

    def resolve(self):
        return self

    def is_file(self):
        return False


def test_every_record_and_warning_names_its_file_with_forward_slashes(monkeypatch):
    """Each place a path leaves depends' answer (dependents, target, source, the directory rows,
    the parse-failure and lost-file warnings) serializes it, here from Windows spellings."""
    monkeypatch.setattr(path_utils, 'Path', _WindowsPath)
    root = PureWindowsPath('C:/repo')
    target, importer = root / 'pkg' / 'core.py', root / 'pkg' / 'a.py'
    stmt = ImportStatement(file_path=importer, line_number=1, module_name='pkg.core', imported_names=['core'],
                           is_relative=False, import_type='from_import')
    graph = ImportGraph()
    graph.files[importer] = [stmt]
    graph.add_dependency(importer, target, None, via='direct')
    record = ProjectResolution(scan_root=root, graph=graph, edge_statements={(importer, target): stmt},
                               files_failed=[str(importer)])
    adapter = DependsAdapter('.')
    adapter._resolution, adapter._scan_root, adapter._target_path = record, root, target
    adapter._analysis = ImportAnalysis(graph=graph, resolution=record, files_lost=[importer])

    file_answer = adapter._format_file_dependents(target)
    assert [d['file'] for d in file_answer['dependents']] == ['pkg/a.py']
    assert (file_answer['target'], file_answer['source']) == ('pkg/core.py', 'pkg/core.py')
    adapter._target_path = root / 'pkg'
    dir_answer = adapter._format_directory_summary(root / 'pkg', None, 'text')
    assert dir_answer['modules'] == [{'module': 'pkg/core.py', 'dependent_count': 1, 'dependents': ['pkg/a.py']}]
    for answer in (file_answer, dir_answer):
        files = [w['files'] for w in answer['meta']['warnings'] if w.get('type') in ('partial_parse', 'worker_lost')]
        assert files == [['pkg/a.py'], ['pkg/a.py']]
        assert '\\' not in answer['warning']
