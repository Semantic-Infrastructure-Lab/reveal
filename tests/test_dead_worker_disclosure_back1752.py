"""BACK-1752/1753/1754: a file lost to a dead pool worker is disclosed as that, everywhere.

BACK-1726 made a dead worker cost only its own files. Three disclosure gaps were left:
a lost code file with no import extractor was counted unsupported, so a structure-only
run (architecture) dropped its structure without a word (1752); lost files read as
"parsed with errors" though the file was never parsed (1753); and ``grep_files`` callers
(markdown ``body_contains``, claude ``?search=``) got only the matches (1754).
"""
import logging
from pathlib import Path

from reveal.adapters import imports as imports_adapter
from reveal.adapters.markdown import operations as markdown_ops
from reveal.rules.imports import I002 as i002
from reveal.utils import parallel

from test_pool_lost_files_back1726 import (  # noqa: F401  (pools is a fixture)
    N_FILES, _BreaksOnSubmit, _Healthy, _grep_tree, _tree, pools,
)

N_SH = 4


def _tree_with_scripts(tmp_path):
    root = _tree(tmp_path)
    for i in range(N_SH):
        (root / f'z{i}.sh').write_text('#!/bin/sh\necho hi\n', encoding='utf-8')
    return root


def _build(root, pools, executor):
    pools.setattr('concurrent.futures.ProcessPoolExecutor', executor)
    adapter = imports_adapter.ImportsAdapter(resource=str(root))
    adapter._build_graph(root, collect_structures=True)
    return adapter


# ------------------------------------------------------------------ 1752

def test_lost_file_without_an_import_extractor_is_failed_not_unsupported(tmp_path, pools):
    root = _tree_with_scripts(tmp_path)
    adapter = _build(root, pools, _BreaksOnSubmit)
    analysis = adapter.analysis
    lost_sh = [fp for fp in analysis.files_failed if fp.suffix == '.sh']
    assert lost_sh, 'the broken pool lost script files; they must reach files_failed'
    assert analysis.unsupported_extensions.get('.sh', 0) + len(lost_sh) == N_SH, \
        'a lost script is counted once: failed, not also unsupported'
    assert all(fp in analysis.files_lost for fp in lost_sh)


def test_1752_negative_control_healthy_pool_counts_scripts_unsupported(tmp_path, pools):
    root = _tree_with_scripts(tmp_path)
    adapter = _build(root, pools, _Healthy)
    assert adapter.analysis.files_failed == [] and adapter.analysis.files_lost == []
    assert adapter.analysis.unsupported_extensions.get('.sh') == N_SH


# ------------------------------------------------------------------ 1753

def test_lost_files_have_their_own_cause_in_metadata_and_warning(tmp_path, pools):
    root = _tree(tmp_path)
    adapter = _build(root, pools, _BreaksOnSubmit)
    lost = adapter.analysis.files_lost
    assert lost and set(lost) <= set(adapter.analysis.files_failed)
    meta = adapter.get_metadata()
    assert meta['files_lost_count'] == len(lost)
    assert sorted(meta['files_lost']) == sorted(str(fp) for fp in lost)
    kinds = {w['type']: w for w in adapter.integrity_warnings(root)}
    assert kinds['worker_lost']['count'] == len(lost)
    assert 'partial_parse' not in kinds, 'a lost file was never parsed; it is not a parse error'
    assert 'pool worker died' in kinds['worker_lost']['message']


def test_a_real_parse_failure_stays_a_partial_parse(tmp_path, pools):
    root = _tree(tmp_path)
    adapter = _build(root, pools, _Healthy)
    adapter.analysis.files_failed = [root / 'm0.py']  # what a tree-sitter error records
    kinds = {w['type'] for w in adapter.integrity_warnings(root)}
    assert kinds == {'partial_parse'}


def test_imports_text_render_says_lost_not_parsed_with_errors(tmp_path, pools, capsys):
    root = _tree(tmp_path)
    adapter = _build(root, pools, _BreaksOnSubmit)
    result = adapter.get_structure()
    imports_adapter.ImportsRenderer._render_import_summary(result, str(root))
    out = capsys.readouterr().out
    assert 'pool worker died' in out
    assert 'parsed with errors' not in out


def test_i002_names_lost_files_as_lost(tmp_path, pools):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
    graph = i002.I002()._build_import_graph(root)
    assert graph.lost_files and set(graph.lost_files) <= set(graph.failed_files)
    disclosures = i002.get_scan_disclosures()
    assert any('pool worker died' in d for d in disclosures), disclosures
    assert not any('parsed with errors' in d for d in disclosures), disclosures


# ------------------------------------------------------------------ 1754

def test_grep_files_result_carries_the_lost_files(tmp_path, monkeypatch):
    files = _grep_tree(tmp_path)
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _BreaksOnSubmit)
    found = parallel.grep_files(files, 'needle')
    assert found == [files[0]]
    assert found.lost and set(found.lost) == set(files[1:])


def test_grep_files_negative_control_nothing_lost(tmp_path, monkeypatch):
    files = _grep_tree(tmp_path)
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _Healthy)
    assert parallel.grep_files(files, 'needle').lost == []
    assert parallel.grep_files(files[:2], 'needle').lost == []  # sequential path


def test_markdown_body_contains_discloses_unscanned_files(tmp_path, monkeypatch):
    for i in range(10):
        (tmp_path / f'd{i}.md').write_text('needle\n', encoding='utf-8')
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _BreaksOnSubmit)
    from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
    result = MarkdownQueryAdapter(str(tmp_path), 'body-contains=needle').get_structure()
    warnings = (result.get('meta') or {}).get('warnings') or []
    lost = [w for w in warnings if w.get('type') == 'worker_lost']
    assert lost and lost[0]['count'] >= 1, warnings


def test_claude_search_discloses_unscanned_sessions(tmp_path, monkeypatch):
    from reveal.adapters.claude.analysis import search as claude_search
    sessions = []
    for i in range(10):
        p = tmp_path / f's{i}.jsonl'
        p.write_text('{"message": "needle"}\n', encoding='utf-8')
        sessions.append({'path': str(p), 'session': f's{i}', 'modified': '2026-10-07'})
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _BreaksOnSubmit)
    lost: list = []
    claude_search.search_sessions_for_term(sessions, 'needle', lost_out=lost)
    assert lost and all(isinstance(p, Path) for p in lost)
