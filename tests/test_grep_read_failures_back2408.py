"""A failed byte read is neither a nonmatch nor a dead pool worker."""

import builtins
import pickle
from concurrent.futures import Future
from pathlib import Path

import pytest

from reveal.reveal_types import PathFailure
from reveal.utils import parallel
from reveal.utils.path_utils import to_posix


class _ImmediatePool:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, item):
        future = Future()
        future.set_result(fn(item))
        return future


@pytest.mark.parametrize('pooled', [False, True], ids=['serial', 'pooled'])
@pytest.mark.parametrize('failure', ['missing', 'unnamed', 'foreign'])
def test_read_failure_retains_candidate_and_preserves_matches(tmp_path, monkeypatch, pooled, failure):
    first, bad, other, last = [tmp_path / name for name in
                               ('first.md', 'bad.md', 'other.md', 'last.md')]
    for path, content in ((first, b'needle'), (other, b'other'), (last, b'needle')):
        path.write_bytes(content)
    original = builtins.open
    if failure != 'missing':
        bad.write_bytes(b'needle')

        def denied(file, *args, **kwargs):
            if Path(file) == bad:
                if failure == 'foreign':
                    raise PermissionError(13, 'READ_DENIED', to_posix(tmp_path / 'foreign.md'))
                raise PermissionError('READ_DENIED')
            return original(file, *args, **kwargs)

        monkeypatch.setattr(builtins, 'open', denied)
    monkeypatch.setattr(parallel, '_PARALLEL_THRESHOLD', 0 if pooled else 100)
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _ImmediatePool)
    found = parallel.grep_files([first, bad, other, last], 'needle')
    assert found == [first, last]
    assert found.lost == []
    failures = getattr(found, 'unreadable', [])
    assert len(failures) == 1, 'the unreadable candidate was indistinguishable from a proven nonmatch'
    record = failures[0]
    assert isinstance(record, PathFailure)
    assert record.path == to_posix(bad)
    assert ('FileNotFoundError' if failure == 'missing' else 'PermissionError') in record.cause
    assert to_posix(tmp_path) not in record.cause
    assert pickle.loads(pickle.dumps(record)) == record


def test_worker_does_not_call_a_missing_file_a_nonmatch(tmp_path):
    path = tmp_path / 'missing.md'
    outcome = parallel._scan_one((path, (b'needle',)))
    assert outcome is not None, 'a read failure was returned as a successful negative scan'
    assert isinstance(outcome, PathFailure)
    assert outcome.path == to_posix(path)


def test_healthy_and_unconstrained_results_have_no_read_failures(tmp_path):
    match, other = tmp_path / 'match.md', tmp_path / 'other.md'
    match.write_bytes(b'needle')
    other.write_bytes(b'other')
    for paths, terms, expected in (([match, other], 'needle', [match]),
                                    ([match, other], '', [match, other]),
                                    ([], 'needle', [])):
        result = parallel.grep_files(paths, terms)
        assert result == expected
        assert result.lost == []
        assert getattr(result, 'unreadable', []) == []
