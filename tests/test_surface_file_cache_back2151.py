"""BACK-2151: the persisted raw result of one surface scanner on one file.

Unit tests for ``reveal.adapters.surface_file_cache``: what is stored, what is served, what is
never stored. The integration tests (invocation counts through ``reveal surface``) sit below.
"""

import os
import sys

import pytest

from reveal.adapters import surface_file_cache as sfc
from reveal.adapters.ast.surface_matrix import RECOVERED_KEY, UNPARSED_KEY
from reveal.adapters.surface import ROUTE_CLASSES_KEY, _validate_requested_surface
from reveal.core import disk_cache

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


def _row(path, name='X'):
    return {'type': 'env_var', 'name': name, 'file': path, 'line': 1}


class Scanner:
    """A scanner double that counts invocations and returns a configurable result."""

    def __init__(self, result=None, raises=None):
        self.calls = 0
        self.result = result
        self.raises = raises

    def __call__(self, path):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        if self.result is not None:
            return self.result(path) if callable(self.result) else self.result
        return {'env': [_row(path)], 'cli': [], ROUTE_CLASSES_KEY: [{'name': 'C'}], RECOVERED_KEY: [path]}


def _scan(scanner, path, scanner_id='m.f', language='go'):
    return sfc.scan_file_cached(scanner, scanner_id, language, str(path), _validate_requested_surface)


def _src(tmp_path, name='a.go', text='package a\n'):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return p


def _touch(path, delta_ns=1_000_000):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + delta_ns))


def test_second_scan_is_served_and_equal(tmp_path):
    src = _src(tmp_path)
    scanner = Scanner()
    first = _scan(scanner, src)
    second = _scan(scanner, src)
    assert scanner.calls == 1
    assert second == first
    # the three keys the caller pops travel inside the entry
    assert second[RECOVERED_KEY] == [str(src)] and second[ROUTE_CLASSES_KEY] == [{'name': 'C'}]


def test_each_hit_is_a_fresh_object(tmp_path):
    src = _src(tmp_path)
    scanner = Scanner()
    _scan(scanner, src)
    one = _scan(scanner, src)
    one.pop(RECOVERED_KEY)
    one['env'][0]['name'] = 'MUTATED'
    two = _scan(scanner, src)
    assert two[RECOVERED_KEY] == [str(src)] and two['env'][0]['name'] == 'X'


def test_edit_misses_and_recomputes_only_that_file(tmp_path):
    a, b = _src(tmp_path, 'a.go'), _src(tmp_path, 'b.go')
    scanner = Scanner()
    _scan(scanner, a)
    _scan(scanner, b)
    assert scanner.calls == 2
    a.write_text('package a\n// edited\n', encoding='utf-8')
    _scan(scanner, a)
    _scan(scanner, b)
    assert scanner.calls == 3


def test_same_size_edit_with_new_mtime_misses(tmp_path):
    src = _src(tmp_path, text='aaaa\n')
    scanner = Scanner()
    _scan(scanner, src)
    src.write_text('bbbb\n', encoding='utf-8')
    _touch(src)
    _scan(scanner, src)
    assert scanner.calls == 2


def test_same_mtime_same_size_edit_is_the_documented_hole(tmp_path):
    """The key is a stat stamp, not a content hash: this is the inherited hole, pinned so a
    change to content-hash semantics is a deliberate one."""
    src = _src(tmp_path, text='aaaa\n')
    stamp = os.stat(src)
    scanner = Scanner()
    _scan(scanner, src)
    src.write_text('bbbb\n', encoding='utf-8')
    os.utime(src, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    _scan(scanner, src)
    assert scanner.calls == 1


@pytest.mark.parametrize('field', ['scanner_id', 'path_spelling'])
def test_key_separates_scanner_and_spelling(tmp_path, field):
    src = _src(tmp_path)
    scanner = Scanner()
    _scan(scanner, src)
    if field == 'scanner_id':
        _scan(scanner, src, scanner_id='m.other')
    else:
        rel = os.path.relpath(src)
        if os.path.abspath(rel) != str(src.resolve()) and rel == str(src):
            pytest.skip('no distinct spelling')
        sfc.scan_file_cached(scanner, 'm.f', 'go', rel, _validate_requested_surface)
    assert scanner.calls == 2


def test_interpreter_version_is_in_the_python_key_only(tmp_path, monkeypatch):
    src = _src(tmp_path, 'a.py')
    stamp = sfc._stat_stamp(str(src))
    before_py = sfc.file_key(str(src), 'm.f', 'python', stamp)
    before_go = sfc.file_key(str(src), 'm.f', 'go', stamp)
    monkeypatch.setattr(sys, 'version_info', (sys.version_info[0], sys.version_info[1] + 1, 0, 'final', 0))
    assert sfc.file_key(str(src), 'm.f', 'python', stamp) != before_py
    assert sfc.file_key(str(src), 'm.f', 'go', stamp) == before_go


@pytest.mark.parametrize('result', [
    {'env': [_row('x')], UNPARSED_KEY: ['x']},          # unparsed: the cause is not visible
    ['not', 'a', 'dict'],
    {'env': 'not a list'},
    {'nonsense': []},                                    # unknown category
    {'env': [{'type': 'env_var', 'name': 'X'}]},          # row without file/line
], ids=['unparsed', 'not-dict', 'bad-group', 'unknown-category', 'bad-row'])
def test_result_that_must_not_be_stored(tmp_path, result):
    src = _src(tmp_path)
    scanner = Scanner(result=result)
    _scan(scanner, src)
    _scan(scanner, src)
    assert scanner.calls == 2


def test_scan_that_raises_stores_nothing_and_raises_again(tmp_path):
    src = _src(tmp_path)
    scanner = Scanner(raises=RuntimeError('boom'))
    for _ in range(2):
        with pytest.raises(RuntimeError, match='boom'):
            _scan(scanner, src)
    assert scanner.calls == 2


def test_edit_during_the_scan_is_not_stored(tmp_path):
    src = _src(tmp_path)
    old_key = sfc.file_key(str(src), 'm.f', 'go', sfc._stat_stamp(str(src)))

    def edits_while_scanning(path):
        _touch(src)
        return {'env': [_row(path)]}

    _scan(Scanner(result=edits_while_scanning), src)
    # the result was computed while the file changed: nothing is filed under the stamp it began at
    assert disk_cache.get(sfc._SURFACE_FILE_NAMESPACE, old_key) is None


def test_unedited_scan_is_stored_under_its_key(tmp_path):
    """Positive control for the test above: the same lookup finds an entry when nothing raced."""
    src = _src(tmp_path)
    key = sfc.file_key(str(src), 'm.f', 'go', sfc._stat_stamp(str(src)))
    _scan(Scanner(), src)
    assert disk_cache.get(sfc._SURFACE_FILE_NAMESPACE, key) is not None


def test_missing_file_is_scanned_and_not_stored(tmp_path):
    scanner = Scanner()
    ghost = tmp_path / 'ghost.go'
    _scan(scanner, ghost)
    _scan(scanner, ghost)
    assert scanner.calls == 2


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='chmod 0 does not hide a file on Windows or from root')
def test_a_hit_is_not_served_for_a_file_that_is_unreadable_now(tmp_path):
    src = _src(tmp_path)
    scanner = Scanner()
    _scan(scanner, src)
    os.chmod(src, 0)
    try:
        _scan(scanner, src)
    finally:
        os.chmod(src, 0o644)
    assert scanner.calls == 2


def test_disabled_cache_scans_every_time_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    src = _src(tmp_path)
    scanner = Scanner()
    _scan(scanner, src)
    _scan(scanner, src)
    assert scanner.calls == 2
    assert not (tmp_path / 'cache').exists()


def test_namespace_is_capped_like_the_structure_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_STRUCTURE_CACHE_MAX_FILES', '3')
    scanner = Scanner()
    for i in range(6):
        _scan(scanner, _src(tmp_path, f'f{i}.go', f'package p{i}\n'))
    entries = list((disk_cache._namespace_dir(sfc._SURFACE_FILE_NAMESPACE)).glob('*.pkl'))
    assert 0 < len(entries) <= 3 + 1   # prune runs on put; the newest entry may land after a listing


def test_other_build_is_not_read(tmp_path, monkeypatch):
    src = _src(tmp_path)
    scanner = Scanner()
    _scan(scanner, src)
    monkeypatch.setattr(disk_cache, 'build_fingerprint', lambda: 'otherbuild000')
    _scan(scanner, src)
    assert scanner.calls == 2


# ---------------------------------------------------------------------------------------------
# Through `reveal surface`: invocation counts and output equality (BACK-2151)
# ---------------------------------------------------------------------------------------------

import json  # noqa: E402
import textwrap  # noqa: E402

from conftest import _run_reveal_direct  # noqa: E402
from reveal.adapters import surface  # noqa: E402
from reveal.adapters.ast.surface_matrix import CATEGORIES  # noqa: E402

ALL_TYPES = tuple(CATEGORIES)

# one small file per registered scanner (11), each reading an env var
LANGUAGE_FILES = {
    'py/a.py': 'import os\nX = os.getenv("PY_KEY")\n',
    'ts/a.ts': 'const x = process.env.TS_KEY;\n',
    'java/A.java': 'class A { void f() { System.getenv("JAVA_KEY"); } }\n',
    'cs/A.cs': 'class A { void F() { System.Environment.GetEnvironmentVariable("CS_KEY"); } }\n',
    'php/a.php': '<?php\n$x = getenv("PHP_KEY");\n',
    'swift/a.swift': 'import Foundation\nlet x = getenv("SWIFT_KEY")\n',
    'kt/a.kt': 'fun f() {\n  System.getenv("KT_KEY")\n}\n',
    'rb/a.rb': 'x = ENV["RB_KEY"]\n',
    'go/a.go': 'package a\nimport "os"\nfunc f() { os.Getenv("GO_KEY") }\n',
    'rs/a.rs': 'fn main() { let _ = std::env::var("RS_KEY"); }\n',
    'cpp/a.cpp': '#include <cstdlib>\nint main() { getenv("CPP_KEY"); }\n',
}

# route prefixes declared on a base type in another file: they travel in the cached
# ROUTE_CLASSES_KEY and are resolved after the merge (Java, Kotlin and C# are the scanners with them)
ROUTE_FILES = {
    'routes/Base.java': '@RequestMapping("/api/v1")\npublic abstract class BaseController {}\n',
    'routes/Items.java': ('@RestController\npublic class ItemsController extends BaseController {\n'
                          '  @GetMapping("/items") public String list() { return ""; }\n}\n'),
    'routes/Api.kt': ('@RequestMapping("/k")\ninterface Api\n@RestController\nclass Impl : Api {\n'
                      '  @GetMapping("/x") fun x() {}\n}\n'),
    'routes/Base.cs': '[ApiController]\n[Route("[controller]")]\npublic class BaseApiController : ControllerBase {}\n',
    'routes/Genres.cs': ('public class GenresController : BaseApiController\n{\n'
                         '  [HttpGet("{genreName}")] public IActionResult GetGenre(string genreName) => Ok();\n}\n'),
}


def _write_files(root, files):
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(body), encoding='utf-8')


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / 'proj'
    _write_files(root, {**LANGUAGE_FILES, **ROUTE_FILES})
    return root


@pytest.fixture
def spy(monkeypatch):
    """Counts every call of a per-file scanner, by file path (the call the cache sits above)."""
    seen = []
    real = surface._load_scanner

    def load(spec):
        scan = real(spec)

        def counted(path):
            seen.append(path)
            return scan(path)
        return counted

    monkeypatch.setattr(surface, '_load_scanner', load)
    return seen


def _run(root, type_filter=''):
    return surface._scan_surface(root, type_filter=type_filter)


def _canon(value):
    return json.dumps(value, sort_keys=True, default=str)


def _count(spy, fn):
    before = len(spy)
    result = fn()
    return len(spy) - before, result


def test_the_fixture_has_all_eleven_scanners_and_real_routes(tree, spy):
    n, report = _count(spy, lambda: _run(tree))
    assert n == len(LANGUAGE_FILES) + len(ROUTE_FILES)
    assert report['total'] > len(LANGUAGE_FILES) // 2
    paths = {row['path'] for row in report['surfaces']['http']}
    assert {'/api/v1/items', '/k/x', 'Genres/{genreName}'} <= paths   # inherited prefixes resolved


def test_nine_typed_runs_after_one_untyped_scan_scan_nothing(tree, spy):
    total = len(LANGUAGE_FILES) + len(ROUTE_FILES)
    first, _ = _count(spy, lambda: _run(tree, 'env'))
    assert first == total
    for category in ALL_TYPES:
        n, _ = _count(spy, lambda: _run(tree, category))
        assert n == 0, f'type={category} re-scanned {n} files'
    n, _ = _count(spy, lambda: _run(tree))
    assert n == 0


def test_edit_one_file_scans_exactly_one(tree, spy):
    _run(tree)
    target = tree / 'go' / 'a.go'
    target.write_text('package a\nimport "os"\nfunc f() { os.Getenv("GO_KEY2") }\n', encoding='utf-8')
    _touch(target)
    n, report = _count(spy, lambda: _run(tree, 'env'))
    assert n == 1 and spy[-1].endswith('a.go')
    assert 'GO_KEY2' in _canon(report)
    assert _count(spy, lambda: _run(tree, 'env'))[0] == 0


def test_delete_one_file_scans_nothing_and_serves_no_entry_for_it(tree, spy):
    first = _run(tree)
    (tree / 'rb' / 'a.rb').unlink()
    n, report = _count(spy, lambda: _run(tree))
    assert n == 0
    assert 'RB_KEY' not in _canon(report) and 'RB_KEY' in _canon(first)


def test_add_one_file_scans_exactly_one(tree, spy):
    _run(tree)
    (tree / 'py' / 'b.py').write_text('import os\nY = os.getenv("NEW_KEY")\n', encoding='utf-8')
    n, report = _count(spy, lambda: _run(tree))
    assert n == 1 and 'NEW_KEY' in _canon(report)


def test_changed_build_fingerprint_rescans_everything(tree, spy, monkeypatch):
    total = len(LANGUAGE_FILES) + len(ROUTE_FILES)
    _run(tree)
    assert _count(spy, lambda: _run(tree))[0] == 0      # positive control: same build, all hits
    monkeypatch.setattr(disk_cache, 'build_fingerprint', lambda: 'otherbuild000')
    assert _count(spy, lambda: _run(tree))[0] == total


def test_source_only_selects_files_without_changing_what_a_file_yields(tree, spy):
    (tree / 'tests').mkdir()
    (tree / 'tests' / 'test_a.py').write_text('import os\nT = os.getenv("TEST_KEY")\n', encoding='utf-8')
    _run(tree)                                              # scans every file once, tests included
    n, report = _count(spy, lambda: surface._scan_surface(tree, source_only=True))
    assert n == 0 and 'TEST_KEY' not in _canon(report)
    n, report = _count(spy, lambda: _run(tree))
    assert n == 0 and 'TEST_KEY' in _canon(report)


@pytest.mark.parametrize('category', ALL_TYPES)
def test_cold_warm_and_cache_off_agree(tree, monkeypatch, category):
    cold = _canon(_run(tree, category))
    warm = _canon(_run(tree, category))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    off = _canon(_run(tree, category))
    assert cold == warm == off


def test_untyped_cold_warm_and_cache_off_agree(tree, monkeypatch):
    cold = _canon(_run(tree))
    warm = _canon(_run(tree))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert cold == warm == _canon(_run(tree))


@pytest.mark.parametrize('fmt', ['text', 'json'])
@pytest.mark.parametrize('category', ['', 'env', 'http'])
def test_command_output_is_byte_equal_cold_warm_and_off(tree, monkeypatch, fmt, category):
    args = ['surface', str(tree), '--format', fmt] + (['--type', category] if category else [])
    cold = _run_reveal_direct(*args)
    warm = _run_reveal_direct(*args)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    off = _run_reveal_direct(*args)
    assert cold.returncode == warm.returncode == off.returncode
    assert cold.stdout == warm.stdout == off.stdout
    assert cold.stderr == warm.stderr == off.stderr
    assert cold.stdout.strip()


def test_broken_sibling_is_reported_every_run_and_rescanned(tree, spy):
    (tree / 'py' / 'broken.py').write_text('def (:\n', encoding='utf-8')
    cold = _run(tree)
    n, warm = _count(spy, lambda: _run(tree))
    assert n == 1 and spy[-1].endswith('broken.py')       # an unparsed file is never stored
    assert _canon(cold) == _canon(warm)
    assert any(f.endswith('broken.py') for f in warm['unparsed_files'])


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='chmod 0 does not hide a file on Windows or from root')
def test_unreadable_file_is_unparsed_cold_warm_and_after_it_was_cached(tree, spy):
    target = tree / 'py' / 'a.py'
    _run(tree)                                              # cached while readable
    os.chmod(target, 0)
    try:
        warm = _run(tree)
        assert any(f.endswith('a.py') for f in warm['unparsed_files'])
        assert 'PY_KEY' not in _canon(warm)
        assert _count(spy, lambda: _run(tree))[0] == 1       # never stored: rescanned
    finally:
        os.chmod(target, 0o644)
    assert not any(f.endswith('a.py') for f in _run(tree)['unparsed_files'])


def _lose_census_dir(monkeypatch):
    """A census traversal failure: the run is in directory-loss mode (BACK-2028)."""
    real = surface.census_and_coverage_for_path

    def census(*args, **kwargs):
        value = real(*args, **kwargs)
        kwargs['on_error'](PermissionError(13, 'denied', 'lost-dir'))
        return value

    monkeypatch.setattr(surface, 'census_and_coverage_for_path', census)


def _malformed_python(monkeypatch, spy):
    """a.py's scanner returns a valid http group and a malformed env group."""
    real = surface._load_scanner

    def load(spec):
        scan = real(spec)

        def run(path):
            result = scan(path)
            if spec.language == 'python' and path.endswith('a.py'):
                result = {**result, 'http': [{'type': 'http', 'name': 'ok', 'file': path, 'line': 1}],
                          'env': 'not a list'}
            return result
        return run

    monkeypatch.setattr(surface, '_load_scanner', load)


def test_directory_loss_typed_warm_equals_typed_cold_and_untyped_still_fails(tree, monkeypatch, spy):
    _lose_census_dir(monkeypatch)
    _malformed_python(monkeypatch, spy)
    results = {}
    for run in ('cold', 'warm'):
        results[run] = {t: _run(tree, t) for t in ('http', 'env', '')}
    for t in ('http', 'env', ''):
        assert _canon(results['cold'][t]) == _canon(results['warm'][t]), t
    # BACK-2028: the unaffected category still succeeds, the malformed one and the untyped run fail
    assert not results['warm']['http'].get('_discovery_error')
    assert results['warm']['env']['_discovery_error'] and results['warm']['']['_discovery_error']
    # the malformed file is never stored, so it is validated again on every run
    n, _ = _count(spy, lambda: _run(tree, 'http'))
    assert n == 1 and spy[-1].endswith('a.py')
