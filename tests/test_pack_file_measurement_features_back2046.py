"""Post-source callback, default-chain and native measurement acceptance."""
from pathlib import Path
import sys

import pytest

from reveal.adapters import pack

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_count_callback_receives_actual_oserror_without_changing_legacy_zero(tmp_path, monkeypatch):
    file = write(tmp_path / 'file.py', 'X=1\n')
    actual = PermissionError('actual unlocated line read')
    def denied(*args, **kwargs):
        raise actual
    monkeypatch.setattr(Path, 'read_text', denied)
    errors = []
    assert pack._count_lines(file, on_error=errors.append) == 0
    assert errors == [actual]
    assert pack._count_lines(file) == 0


@pytest.mark.parametrize('error_class', [OSError, RuntimeError])
def test_count_callback_failure_propagates_outside_native_io_catch(tmp_path, monkeypatch, error_class):
    file = write(tmp_path / 'file.py', 'X=1\n')
    def denied(*args, **kwargs):
        raise PermissionError('actual native read loss')
    sentinel = error_class('callback failure must propagate')
    def callback(error):
        assert isinstance(error, PermissionError)
        raise sentinel
    monkeypatch.setattr(Path, 'read_text', denied)
    with pytest.raises(error_class) as raised:
        pack._count_lines(file, on_error=callback)
    assert raised.value is sentinel


@pytest.mark.parametrize('operation', ['stat', 'read'])
def test_candidate_file_callback_oserror_is_not_reclassified_as_measurement_loss(tmp_path, monkeypatch, operation):
    file = write(tmp_path / 'core.py', 'X=1\n')
    original = getattr(Path, operation if operation == 'stat' else 'read_text')
    events = []
    def denied(*args, **kwargs):
        if args[0] == file:
            events.append(file)
            raise PermissionError('actual candidate file loss')
        return original(*args, **kwargs)
    monkeypatch.setattr(Path, operation if operation == 'stat' else 'read_text', denied)
    sentinel = OSError('FILE callback itself failed')
    facts = []
    def callback(fact):
        facts.append(fact)
        raise sentinel
    with pytest.raises(OSError) as raised:
        pack._collect_candidates(tmp_path, None, on_file_error=callback)
    assert raised.value is sentinel and events == [file] and len(facts) == 1
    assert facts[0][0] == file.as_posix() and 'PermissionError' in facts[0][2]


@pytest.mark.parametrize('error_class', [OSError, RuntimeError])
def test_priority_errors_propagate_instead_of_becoming_file_diagnostics(tmp_path, monkeypatch, error_class):
    write(tmp_path / 'core.py', 'X=1\n')
    sentinel = error_class('priority implementation failed')
    def broken(*args, **kwargs):
        raise sentinel
    monkeypatch.setattr(pack, '_compute_priority', broken)
    facts = []
    with pytest.raises(error_class) as raised:
        pack._collect_candidates(tmp_path, None, on_file_error=facts.append)
    assert raised.value is sentinel and facts == []


@pytest.mark.parametrize('name,size', [('main.py', 3000), ('pkg/__init__.py', 3000), ('core.py', 51000)])
def test_adopted_measurement_stat_is_reused_for_init_entry_and_large_file_priority(tmp_path, monkeypatch, name, size):
    file = write(tmp_path / name, 'x' * size)
    real_stat = Path.stat
    calls = []
    def stat(*args, **kwargs):
        if args[0] == file:
            calls.append(sys._getframe(1).f_code.co_name)
        return real_stat(*args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    rows = pack._collect_candidates(tmp_path, None, on_file_error=lambda fact: pytest.fail(str(fact)))
    assert len(rows) == 1 and rows[0]['size'] == size
    assert calls.count('_candidate_measurements') == 1
    assert '_file_size' not in calls and '_candidate_stat' not in calls
    # Path.resolve/upstream path validation may stat independently; this is the
    # candidate size/mtime measurement, not a claim of one filesystem stat total.


def test_zero_known_priority_size_does_not_fall_back_to_stat(tmp_path, monkeypatch):
    path = write(tmp_path / 'main.py', '')
    real_stat = Path.stat
    calls = []
    def stat(*args, **kwargs):
        if args[0] == path:
            calls.append(path)
        return real_stat(*args, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(Path, 'stat', stat)
        score = pack._compute_priority(path, Path('main.py'), None, size_bytes=0)
    assert score == 2.0 and calls == []  # Native key-stem bonus; zero is a known size.


def test_default_collector_retains_old_count_and_priority_call_shapes(tmp_path, monkeypatch):
    write(tmp_path / 'core.py', 'X=1\n')
    real_count, real_priority = pack._count_lines, pack._compute_priority
    calls = []
    def count(path):  # Intentionally the historical one-positional helper.
        calls.append('count')
        return real_count(path)
    def priority(path, rel, focus, is_changed=False, fan_in=0, graph_relevance=0.0, is_root_config=True):
        calls.append('priority')
        return real_priority(path, rel, focus, is_changed, fan_in, graph_relevance, is_root_config)
    monkeypatch.setattr(pack, '_count_lines', count)
    monkeypatch.setattr(pack, '_compute_priority', priority)
    rows = pack._collect_candidates(tmp_path, None, None, None, None, None)
    assert type(rows) is list and rows[0]['lines'] == 1 and calls == ['count', 'priority']


def test_full_file_facts_known_context_survives_unlocated_causes_and_display_cap(tmp_path, monkeypatch):
    files = {write(tmp_path / f'file{index}.py', 'X=1\n') for index in range(7)}
    real_stat = Path.stat
    denied = []
    def stat(*args, **kwargs):
        if args[0] in files:
            denied.append(args[0])
            raise PermissionError('actual filename-less candidate stat loss')
        return real_stat(*args, **kwargs)
    class Sink:
        def __init__(self):
            self.facts = []
        def __bool__(self):
            return False
        def __call__(self, fact):
            self.facts.append(fact)
    sink = Sink()
    monkeypatch.setattr(Path, 'stat', stat)
    rows = pack._collect_candidates(tmp_path, None, on_file_error=sink)
    assert rows == [] and set(denied) == files
    assert len(sink.facts) == 7 and all(type(fact) is tuple for fact in sink.facts)
    assert {fact[0] for fact in sink.facts} == {file.as_posix() for file in files}
    assert all(fact[1] == 'stat' and fact[2].startswith('PermissionError:') for fact in sink.facts)
    full = tuple(sink.facts)
    meta = {}
    pack._record_file_measurement_warning(full, meta)
    note, = meta['warnings']
    assert full == tuple(sink.facts) and len(full) == 7
    assert len(note['files']) == len(note['causes']) == 5
    assert note['operations'] == ['stat'] and 'additional file measurement failures' in note['message']
    assert note.get('unit') != 'directories' and 'count' not in note
