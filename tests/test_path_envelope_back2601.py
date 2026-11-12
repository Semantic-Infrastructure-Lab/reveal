"""Path envelopes preserve actual payloads, scope and cuts across public consumers."""

import json

import pytest

from conftest import _run_reveal_in


SOURCE = 'def add(x):\n    y = x + 1\n    if y:\n        return y\n    return 0\n'


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text(SOURCE, encoding='utf-8')
    (tmp_path / 'b.py').write_text('from a import add\n\ndef go():\n    return add(1)\n', encoding='utf-8')
    return tmp_path


def envelope(answer, source):
    assert answer['contract_version'] == '1.1'
    assert answer['source'] == source
    assert answer['source_type'] == 'file'
    assert isinstance(answer['type'], str)
    assert isinstance(answer['meta']['warnings'], list)
    assert isinstance(answer['meta']['errors'], list)


def test_file_outline_adds_envelope_without_losing_structure(tree):
    result = _run_reveal_in(tree, 'a.py', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    envelope(answer, 'a.py')
    assert answer['file'] == 'a.py'
    assert answer['structure']['functions'][0]['name'] == 'add'


@pytest.mark.parametrize('argv,category', [
    (('.',), 'directory'), (('.', '--files'), 'directory'),
    (('.', '--grep', 'return'), 'directory'),
    (('a.py', '--grep', 'return'), 'file'), (('a.py', '--meta'), 'file'),
    (('.', '--meta'), 'directory'), (('a.py', '--typed'), 'file'),
])
def test_other_path_reads_share_the_envelope(tree, argv, category):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['source'] == argv[0]
    assert answer['source_type'] == category
    assert answer['meta'] == {'warnings': [], 'errors': []}


def test_element_source_is_target_and_content_is_exact_code(tree):
    result = _run_reveal_in(tree, 'a.py', 'add', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    envelope(answer, 'a.py')
    assert answer['content'] == SOURCE.rstrip('\n')
    assert (answer['line_start'], answer['line_end']) == (1, 5)


@pytest.mark.parametrize('flags', [
    ('--boundary',), ('--effects',), ('--exits',), ('--flow',),
    ('--inputs',), ('--outputs',), ('--callsites',), ('--varflow', 'y'),
])
def test_element_views_have_envelope_and_keep_selection(tree, flags):
    result = _run_reveal_in(tree, 'a.py', 'add', *flags, '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    envelope(answer, 'a.py')
    assert answer['meta']['element'] == 'add'
    assert answer['meta']['from_line'] == 1
    assert answer['findings'] is not None


def test_api_element_uses_same_content_contract(tree):
    from reveal.api import element
    answer = element(str(tree / 'a.py'), 'add')
    envelope(answer, (tree / 'a.py').as_posix())
    assert answer['content'] == SOURCE.rstrip('\n')


def test_element_display_cut_keeps_content_and_disclosure(tree):
    result = _run_reveal_in(tree, 'a.py', 'add', '--head', '2', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    envelope(answer, 'a.py')
    assert answer['content'].split('\n') == SOURCE.split('\n')[:2]
    cut = next(w for w in answer['meta']['warnings'] if w['type'] == 'truncated')
    assert cut['field'] == 'content'
    assert cut['label'] == 'source'  # human wording stays aligned with text output


def test_enveloping_does_not_mutate_raw_spans_and_is_repeatable():
    from reveal.utils.results import ResultBuilder
    raw = {'source': 'code', 'sections': [{'source': 'part', 'line_start': 1, 'line_end': 1}],
           'meta': {'warnings': [{'type': 'truncated', 'field': 'source',
                                  'message': 'source: showing 1 of 2'}]}}
    answer = ResultBuilder.element(raw, 'a.py')
    assert raw['source'] == 'code' and raw['sections'][0]['source'] == 'part'
    assert raw['meta']['warnings'][0]['field'] == 'source'
    assert ResultBuilder.element(answer, 'a.py') == answer


def test_multiple_markdown_spans_keep_independent_content_and_lines(tree):
    (tree / 'a.md').write_text('# Doc\n\n## A\none\n\n## B\ntwo\n', encoding='utf-8')
    result = _run_reveal_in(tree, 'a.md', 'A|B', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    envelope(answer, 'a.md')
    assert [s['line_start'] for s in answer['sections']] == [3, 6]
    assert all('content' in span and 'source' not in span for span in answer['sections'])


def test_imports_analysis_metadata_has_one_canonical_meta_owner(tree):
    from reveal.api import query
    answer = query(f'imports://{tree}')
    assert answer['meta']['total_imports'] >= 1
    assert answer['meta']['warnings'] == []
    # An additive-stage alias is not another mutable metadata store.
    assert answer['metadata'] is answer['meta']


def test_file_check_has_files_and_summary_like_directory_check(tree):
    single = _run_reveal_in(tree, 'check', 'a.py', '--select', 'E501', '--format', 'json')
    directory = _run_reveal_in(tree, 'check', '.', '--select', 'E501', '--format', 'json')
    assert single.returncode == directory.returncode == 0
    a, b = json.loads(single.stdout), json.loads(directory.stdout)
    envelope(a, 'a.py')
    assert isinstance(a['files'], list) and isinstance(b['files'], list)
    assert a['files'][0]['detections'] == a['detections']
    assert a['summary']['files_checked'] == 1
    assert a['summary']['total_issues'] == a['total'] == 0
