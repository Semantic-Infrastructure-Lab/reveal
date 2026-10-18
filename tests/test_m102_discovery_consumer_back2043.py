"""Independent M102 eligible/config scope regressions on existing APIs."""
import importlib
import os
from pathlib import Path

import pytest

import reveal
from reveal.rules import _file_config, RuleRegistry
from reveal.rules.scan_caches import get_scan_disclosures

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
mod = importlib.import_module('reveal.rules.maintainability.M102')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root, *, disabled=False, positive=False, uppercase=False):
    worker = write(root / ('worker.PY' if uppercase else 'worker.py'),
                   ('import stable_symbol\n' if positive else '') + 'VALUE=1\n')
    write(root / 'included' / 'main.py', 'import worker\n')
    write(root / 'pyproject.toml', '[project]\nname="probe"\n')
    if disabled:
        write(root / '.reveal.yaml', 'root: true\nrules:\n  disable: [M102]\n')
    return worker


@pytest.fixture
def observed(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False,
             'events': [], 'calls': [], 'reads': []}
    real_collect, real_scan, real_extract = mod.M102._collect_all_imports, os.scandir, mod._extract_imports_regex
    def collect(self, root):
        state['active'] = True
        try:
            value = real_collect(self, root)
            state['calls'].append(root)
            return value
        finally:
            state['active'] = False
    def scandir(path):
        if state['active'] and Path(path) in state['denied']:
            state['events'].append(Path(path))
            if state['unknown']:
                raise PermissionError('actual unlocated independent M102 importer loss')
            raise PermissionError(13, 'actual independent M102 importer loss', str(path))
        return real_scan(path)
    def extract(*args, **kwargs):
        result = real_extract(*args, **kwargs)
        if state['active']:
            state['reads'].append(Path(args[2]))
        return result
    monkeypatch.setattr(mod.M102, '_collect_all_imports', collect)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(mod, '_extract_imports_regex', extract)
    return state


def build_partial(worker, observed, *, root_loss=False):
    root = worker.parent
    observed['denied'] = {root if root_loss else root / 'included'}
    rule = mod.M102()
    result = rule.check(str(worker), None, worker.read_text(encoding='utf-8'))
    assert len(result) == 1 and observed['events'][-1] in observed['denied']
    assert root in mod._import_cache
    return mod._import_cache[root]


def note(files, *, select=None, ignore=None):
    return get_scan_disclosures(files, select, ignore)


def assert_loss(notes, root):
    assert len(notes) == 1, 'Actual cached M102 importer loss must reach eligible public Check notes'
    text = notes[0]
    assert 'M102' in text and str(root) in text and 'directory enumeration' in text
    assert 'false positive' in text.lower() or ('orphan' in text.lower() and 'may' in text.lower())
    assert 'lower bound' not in text.lower()
    return text


@pytest.mark.parametrize('positive', [False, True])
def test_partial_inventory_scope_uses_native_per_file_config_and_preserves_same_memo(tmp_path, observed, positive):
    root = tmp_path / 'project'
    worker = project(root, positive=positive)
    disabled = write(root / 'disabled.py', 'VALUE=2\n')
    write(root / '.reveal.yaml', 'root: true\noverrides:\n  - files: disabled.py\n    rules:\n      disable: [M102]\n')
    inventory = build_partial(worker, observed)
    assert inventory == ({'stable_symbol'} if positive else set())
    assert _file_config(str(worker)).is_rule_enabled('M102')
    assert not _file_config(str(disabled)).is_rule_enabled('M102')
    before = (len(observed['calls']), len(observed['reads']))
    assert note([disabled]) == []
    assert_loss(note([worker, disabled, worker]), root)
    assert_loss(note([disabled], select=['M102']), root)
    assert note([worker], select=['E501']) == [] and note([worker], ignore=['M102']) == []
    assert (len(observed['calls']), len(observed['reads'])) == before
    assert mod._import_cache[root] is inventory


@pytest.mark.parametrize('unknown', [False, True])
def test_mixed_roots_keep_config_scope_and_unknown_attribution(tmp_path, observed, unknown):
    observed['unknown'] = unknown
    enabled = project(tmp_path / 'enabled')
    disabled = project(tmp_path / 'disabled', disabled=True)
    for worker in (enabled, disabled):
        build_partial(worker, observed, root_loss=unknown)
    assert len(observed['events']) == 2
    before = len(observed['calls'])
    text = assert_loss(note([enabled, disabled]), enabled.parent)
    assert str(disabled.parent) not in text
    both = note([enabled, disabled], select=['M102'])
    assert len(both) == 2 and len(set(both)) == 2
    assert all(any(str(worker.parent) in row for row in both) for worker in (enabled, disabled))
    if unknown:
        assert all('0 identified directory' in row and '1 enumeration error event(s)' in row for row in both)
    assert len(observed['calls']) == before


@pytest.mark.parametrize('alias', ['relative', 'symlink', 'uppercase'])
def test_checked_target_aliases_use_registry_identity_and_do_not_duplicate_root(tmp_path, observed, monkeypatch, alias):
    root = tmp_path / 'project'
    worker = project(root, uppercase=alias == 'uppercase')
    build_partial(worker, observed)
    if alias == 'relative':
        monkeypatch.chdir(root)
        requested = Path(worker.name)
    elif alias == 'symlink':
        requested = tmp_path / 'alias.py'
        requested.symlink_to(worker)
    else:
        requested = worker
    assert mod.M102.matches_target(str(requested))
    assert mod._project_root(requested.resolve()) == root
    before = len(observed['calls'])
    assert_loss(note([requested, worker], select=['M102']), root)
    assert len(observed['calls']) == before


def test_none_diagnostic_population_and_empty_checked_population_are_distinct(tmp_path, observed):
    worker = project(tmp_path / 'project')
    build_partial(worker, observed)
    before = len(observed['calls'])
    assert note([], select=['M102']) == []
    all_notes = note(None, select=['M102'])
    assert any(str(worker.parent) in row for row in all_notes), all_notes
    assert len(observed['calls']) == before


@pytest.mark.parametrize('population', ['entry', 'test', 'plugin', 'non_python', 'unmarked_root', 'missing_cache'])
def test_unreached_subject_controls_never_build_or_adopt_another_cached_root(tmp_path, observed, population):
    worker = project(tmp_path / 'cached')
    build_partial(worker, observed)
    if population == 'entry':
        target = write(worker.parent / 'main.py', 'import worker\n')
    elif population == 'test':
        target = write(worker.parent / 'specs' / 'test_worker.py', 'import worker\n')
    elif population == 'plugin':
        target = write(worker.parent / 'B123.py', 'VALUE=1\n')
    elif population == 'non_python':
        target = write(worker.parent / 'visible.js', 'const value=1;\n')
    elif population == 'unmarked_root':
        target = write(tmp_path / 'unmarked' / 'worker.py', 'VALUE=1\n')
        assert mod._project_root(target) is None
    else:
        target = project(tmp_path / 'never_built')
    before = (len(observed['calls']), len(observed['reads']))
    assert note([target], select=['M102']) == []
    assert (len(observed['calls']), len(observed['reads'])) == before


def test_default_disabled_actual_registry_scope_vs_explicit_selection_override(tmp_path, observed):
    worker = project(tmp_path / 'project', disabled=True)
    build_partial(worker, observed)
    before = len(observed['calls'])
    default = RuleRegistry.check_file(str(worker), None, worker.read_text(encoding='utf-8'))
    assert not any(d.rule_code == 'M102' for d in default)
    assert len(observed['calls']) == before
    assert note([worker]) == []
    selected = RuleRegistry.check_file(str(worker), None, worker.read_text(encoding='utf-8'), select=['M102'])
    assert len(selected) == 1 and selected[0].rule_code == 'M102'
    assert_loss(note([worker], select=['M102']), worker.parent)


def test_existing_plain_set_seeds_and_set_operations_stay_compatible(tmp_path):
    worker = project(tmp_path / 'project')
    root = worker.parent
    plain = {'worker'}
    mod._import_cache[root] = plain  # Explicit legacy worker/cache fixture, no lifetime claim.
    result = mod.M102()._collect_all_imports(root)
    assert result is plain and isinstance(result, set)
    assert result.copy() == {'worker'} and result | {'other'} == {'worker', 'other'}
    assert result & {'worker'} == {'worker'} and list(sorted(result)) == ['worker']
    assert mod.M102().check(str(worker), None, worker.read_text(encoding='utf-8')) == []
    assert note([worker], select=['M102']) == []
