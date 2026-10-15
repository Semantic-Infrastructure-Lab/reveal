"""BACK-1827: a directory check resolved every file's project root about 11 times.

Sprint 4 added root-scoped scan accounting: the I002/D005/T006 preloads and each rule's
``get_scan_disclosures(files)`` mapped every file through ``cross_file_scan_root``
(several ceiling-bounded parent walks), and ``reveal check`` collected the disclosures
three times per text run. On reveal's own tree (1,365 files) that was 15,772 calls and
``reveal check .`` went from 48 s to 56 s. A file's scan root depends only on its
directory, so each directory is resolved once per call, and check collects once.
"""
import sys
from pathlib import Path

import pytest

import reveal.rules.duplicates.D005 as D005
import reveal.rules.imports.I002 as I002
import reveal.rules.types.T006 as T006
from reveal.rules.scan_caches import _project_roots, get_scan_disclosures

pytestmark = pytest.mark.component


def _two_projects(tmp_path, per_dir=5):
    files = []
    for project in ('p1', 'p2'):
        root = tmp_path / project
        (root / 'pkg').mkdir(parents=True)
        (root / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
        for i in range(per_dir):
            path = root / 'pkg' / f'm{i}.py'
            path.write_text(f'def f{i}():\n    return {i}\n', encoding='utf-8')
            files.append(path)
    return files


@pytest.fixture
def root_calls(monkeypatch):
    calls = []
    for module in (I002, D005, T006):
        original = module.cross_file_scan_root

        def counting(path, *args, _original=original, **kwargs):
            calls.append(path)
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(module, 'cross_file_scan_root', counting)
    return calls


def test_disclosures_resolve_each_directory_once_per_rule(tmp_path, root_calls):
    files = _two_projects(tmp_path)
    get_scan_disclosures(files)
    # 3 rules x 2 directories; was 3 x 10 files.
    assert len(root_calls) == 6


def test_preload_roots_resolve_each_directory_once(tmp_path):
    files = _two_projects(tmp_path)
    seen = []

    def find_root(path):
        seen.append(path)
        return path.parent.parent
    roots = _project_roots(tmp_path, files, find_root)
    assert list(roots) == [(tmp_path / 'p1').resolve(), (tmp_path / 'p2').resolve()]
    assert len(seen) == 2


def test_disclosures_still_scoped_to_the_checked_files_roots(tmp_path, monkeypatch):
    # Negative control: memoising by directory must not widen or narrow the root filter.
    files = _two_projects(tmp_path)
    p2 = T006._find_project_root(files[-1].resolve())
    monkeypatch.setitem(T006._project_skip_reasons, p2, 'T006: skipped p2 (test)')
    assert get_scan_disclosures(files[:5], ['T006'], None) == []
    assert get_scan_disclosures(files[5:], ['T006'], None) == ['T006: skipped p2 (test)']
    assert get_scan_disclosures(files, ['T006'], None) == ['T006: skipped p2 (test)']


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_check_collects_scan_disclosures_once(tmp_path, monkeypatch, capsys, fmt):
    import reveal.cli.file_checker as file_checker
    from reveal.main import main
    _two_projects(tmp_path, per_dir=2)
    collected = []
    original = file_checker.get_scan_disclosures

    def counting(*args, **kwargs):
        collected.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(file_checker, 'get_scan_disclosures', counting)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setattr(sys, 'argv', ['reveal', 'check', str(tmp_path), '--format', fmt, '--exit-zero'])
    with pytest.raises(SystemExit):
        main()
    capsys.readouterr()
    assert len(collected) == 1
