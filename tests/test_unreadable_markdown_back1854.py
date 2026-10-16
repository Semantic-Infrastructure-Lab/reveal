"""A markdown file that cannot be read is disclosed, not read as "no match" (BACK-1854).

``read_body_text`` and ``extract_internal_links`` returned ''/[] on a decode error, so
``body-contains`` dropped a file its byte-level pre-filter had matched and the link graph
counted it as having no links, with only a log line.
"""
from pathlib import Path

import pytest

from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.adapters.markdown import files as md_files


@pytest.fixture
def docs(tmp_path):
    (tmp_path / 'good.md').write_text('---\ntitle: good\n---\nthe needle is here\n[b](other.md)\n',
                                      encoding='utf-8')
    (tmp_path / 'other.md').write_text('---\ntitle: other\n---\nplain\n', encoding='utf-8')
    # Latin-1 bytes: not UTF-8, but 'needle' matches at the byte level (grep_files prefilter).
    (tmp_path / 'latin.md').write_bytes(b'---\ntitle: latin\n---\nneedle caf\xe9 [g](good.md)\n')
    return tmp_path


def _unreadable(result):
    meta = result.get('meta', {})
    return [w for w in meta.get('warnings', []) if w.get('type') == 'unreadable_files']


def _assert_names_latin(warnings):
    (warning,) = warnings
    assert warning['count'] == 1
    assert warning['files'] == ['latin.md']
    assert 'UnicodeDecodeError' in warning['message']


def test_outcome_separates_unreadable_from_empty(docs, tmp_path):
    (tmp_path / 'empty.md').write_text('', encoding='utf-8')
    assert md_files.read_body_outcome(tmp_path / 'empty.md') == ('', None)
    body, failure = md_files.read_body_outcome(docs / 'latin.md')
    assert body == '' and failure.startswith('UnicodeDecodeError')
    assert md_files.extract_internal_links_outcome(docs / 'latin.md', docs)[1].startswith('UnicodeDecodeError')
    assert md_files.extract_internal_links_outcome(docs / 'good.md', docs) == (['other.md'], None)


def test_body_contains_discloses_the_unsearched_file(docs):
    result = MarkdownQueryAdapter(str(docs), 'body-contains=needle').get_structure()
    assert [Path(r['path']).name for r in result['results']] == ['good.md']
    _assert_names_latin(_unreadable(result))


def test_aggregate_discloses_the_unsearched_file(docs):
    result = MarkdownQueryAdapter(str(docs), 'aggregate=title&body-contains=needle').get_structure()
    assert result['matched_files'] == 1
    _assert_names_latin(_unreadable(result))
    assert 'unreadable_files' not in result


def test_link_graph_discloses_the_unreadable_file(docs):
    result = MarkdownQueryAdapter(str(docs), 'link-graph').get_structure()
    _assert_names_latin(_unreadable(result))
    assert 'unreadable_files' not in result


def test_backlinks_disclose_the_unreadable_file(docs):
    result = MarkdownQueryAdapter(str(docs), 'backlinks=good.md').get_structure()
    assert result['linked_by'] == []  # latin.md links to it, but cannot be read
    _assert_names_latin(_unreadable(result))


def test_clean_tree_has_no_unreadable_warning(tmp_path):
    (tmp_path / 'good.md').write_text('---\ntitle: good\n---\nthe needle\n', encoding='utf-8')
    for query in ('body-contains=needle', 'link-graph', 'backlinks=good.md', 'aggregate=title'):
        assert not _unreadable(MarkdownQueryAdapter(str(tmp_path), query).get_structure())


def test_an_impossible_frontmatter_date_is_malformed_not_a_failed_query(tmp_path):
    """BACK-1855: `date: 2001-02-30` raised ValueError out of safe_load and ended the query."""
    (tmp_path / 'ok.md').write_text('---\ntitle: ok\n---\nbody\n', encoding='utf-8')
    (tmp_path / 'bad.md').write_text('---\ntitle: bad\ndate: 2001-02-30\n---\nbody\n', encoding='utf-8')
    diagnostic = md_files.extract_frontmatter_diagnostic(tmp_path / 'bad.md')
    assert diagnostic['status'] == 'malformed' and 'out of range' in diagnostic['error']
    result = MarkdownQueryAdapter(str(tmp_path), 'title=ok').get_structure()
    assert [Path(r['path']).name for r in result['results']] == ['ok.md']
