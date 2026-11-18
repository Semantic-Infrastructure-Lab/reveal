"""recovered_paths: the files one import build read only through error recovery (BACK-2665).

One owner for the set ``file_loss_warnings`` names as ``parse_recovered``, so a consumer that needs the
paths (Pack's parse_recovered disclosure) reads them instead of re-deriving the three-way split.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from reveal.analyzers.imports import service as import_service
from reveal.analyzers.imports.diagnostics import file_loss_warnings, recovered_paths

pytestmark = pytest.mark.component


def _extraction(read_error=None, parse=None):
    return SimpleNamespace(read_error=read_error, diagnostics={'parse': parse} if parse else {})


def _analysis():
    recovered, unread, unavailable, lost = (Path('r/a.py'), Path('r/u.py'), Path('r/n.py'), Path('r/l.py'))
    return SimpleNamespace(
        files_failed=[recovered, unread, unavailable, lost],
        files_lost=[lost],
        extractions={recovered: _extraction(),
                     unread: _extraction('PermissionError', {'reason': 'denied'}),
                     unavailable: _extraction(parse={'status': 'unavailable', 'reason': 'no grammar'})},
    )


def test_only_recovered_files_neither_unread_nor_lost():
    assert recovered_paths(_analysis()) == [Path('r/a.py')]


def test_within_keeps_only_the_answers_own_files():
    assert recovered_paths(_analysis(), within=lambda path: path.name != 'a.py') == []


def test_matches_the_partial_parse_warning_of_a_real_build(tmp_path):
    (tmp_path / 'a.py').write_text('def b():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('from a import b\n\ndef broken(:\n    pass\n', encoding='utf-8')
    analysis = import_service.analyze(import_service.path_scope(tmp_path.resolve())).analysis
    paths = recovered_paths(analysis)
    assert [Path(p).name for p in paths] == ['b.py']
    (partial,) = [w for w in file_loss_warnings(analysis) if w['type'] == 'parse_recovered']
    assert partial['count'] == len(paths) and partial['files'] == [Path(p).as_posix() for p in paths]


def test_clean_build_has_none(tmp_path):
    (tmp_path / 'a.py').write_text('def b():\n    return 1\n', encoding='utf-8')
    analysis = import_service.analyze(import_service.path_scope(tmp_path.resolve())).analysis
    assert recovered_paths(analysis) == []
