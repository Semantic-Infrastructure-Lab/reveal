"""BACK-1551: caps with no knob cut silently, or said so only through a private count.

Harness invariant 7 (test_output_contract_compliance) varies an adapter's own cap knob, so
it cannot see a cap that has none. git's repository view now cuts its branches and tags at
``?limit`` and is covered there (its fixture has two of each). These are the rest: each
either lists everything, or records its cut with ``note_truncation``.
"""
import sys

from conftest import _run_reveal_direct
from reveal.adapters.help import HelpAdapter
from reveal.adapters.imports import ImportsAdapter
from reveal.adapters.python.doctor import check_cwd_shadowing
from reveal.rendering.adapters.testability import patch_hotspot_lines
from reveal.analyzers.markdown import MarkdownAnalyzer
from reveal.utils.results import truncations_of


def _write_related(tmp_path, n_headings):
    (tmp_path / 'b.md').write_text(
        '# B\n\n' + ''.join(f'## Part {i}\n\ntext\n\n' for i in range(n_headings - 1)),
        encoding='utf-8')
    main = tmp_path / 'a.md'
    main.write_text('---\nrelated:\n  - ./b.md\n---\n\n# A\n', encoding='utf-8')
    return main


def test_related_doc_lists_every_heading(tmp_path):
    """HEAD kept 10 of a related doc's headings, so the text footer could never fire."""
    main = _write_related(tmp_path, 12)
    [related] = MarkdownAnalyzer(str(main)).get_structure(extract_related=True)['related']
    assert len(related['headings']) == 12


def test_related_text_view_says_how_many_it_left_out(tmp_path):
    main = _write_related(tmp_path, 12)
    out = _run_reveal_direct(str(main), '--related').stdout
    assert 'Headings (12):' in out
    assert '... and 7 more' in out


def test_patch_hotspot_text_says_how_many_profiles_it_left_out():
    """JSON lists every related profile; text shows 3 and now says so (HEAD: 5, then 3, silently)."""
    profile = {'file': 'f.py', 'function': 'g', 'complexity': 1, 'line': 1}
    lines = patch_hotspot_lines([{'key': 'k', 'patch_count': 3, 'test_count': 1,
                                  'related_profiles': [profile] * 7, 'suggestion': 's'}])
    assert '    related production functions (3 of 7; --format json lists all):' in lines


def test_schema_example_cut_is_a_note_and_leaves_the_full_schema_whole():
    """The cut said so only in an example_queries_detail string no text view printed. The
    note goes on a copy: the summary shares its schema with the cached /full one."""
    adapter = HelpAdapter('help://')
    summary = adapter.get_element('schemas/claude')
    [cut] = truncations_of(summary)
    assert (cut['field'], cut['shown']) == ('example_queries', len(summary['example_queries']))
    assert cut['total'] > cut['shown']
    assert 'example_queries_detail' not in summary
    adapter.get_element('schemas/claude')
    full = adapter.get_element('schemas/claude/full')
    assert not truncations_of(full)
    assert len(full['example_queries']) == cut['total']


def test_schema_example_cut_prints_in_text():
    out = _run_reveal_direct('help://schemas/claude').stdout
    assert '⚠ Truncated example_queries: showing 15 of' in out


def test_failed_file_sample_is_disclosed(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('import os\n', encoding='utf-8')
    adapter = ImportsAdapter(str(tmp_path))
    adapter.get_structure()
    real = adapter.get_metadata
    monkeypatch.setattr(adapter, 'get_metadata', lambda: dict(
        real(), files_failed=[f'f{i}.py' for i in range(50)], files_failed_count=73))
    [cut] = truncations_of(adapter._build_response('imports'))
    assert (cut['field'], cut['shown'], cut['total']) == ('metadata.files_failed', 50, 73)


def test_no_failed_files_no_note(tmp_path):
    (tmp_path / 'a.py').write_text('import os\n', encoding='utf-8')
    assert not truncations_of(ImportsAdapter(str(tmp_path)).get_structure())


def test_doctor_says_its_file_list_is_a_sample(tmp_path, monkeypatch):
    for i in range(7):
        (tmp_path / f'm{i}.py').write_text('', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'path', [''] + sys.path[1:])
    [warning], _ = check_cwd_shadowing()
    assert len(warning['files']) == 5
    assert warning['message'].endswith('contains 7 .py files; the first 5 are listed')



def test_testability_uri_text_carries_the_result_warnings(tmp_path):
    """BACK-916: the renderer returns its body, so the router's warning footer reaches testability://
    (the old print renderer dropped it)."""
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'a.py').write_text('import requests\n\ndef f():\n    return requests.get("x")\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text('def test_a():\n    assert True\n', encoding='utf-8')
    out = _run_reveal_direct(f'testability://{tmp_path / "pkg"}?tests={tmp_path / "tests"}').stdout
    assert 'Summary' in out and 'best-effort' in out
