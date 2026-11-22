"""Markdown text answers teach the one spelling and point to their counting rules (BACK-2614 B8/B9, BACK-2599).

- The listing's header names the request as the subcommand's flags, not the retiring query string (``Filter: ?where=...``,
  ``explain=True``).
- The link graph prints one number per word: the header's orphan count is the Orphans list's, and the definitions move to
  one ``Rules:`` pointer whose text is the JSON's ``_meta.known_limits``.
- A ranked body match points to its ranking rule the same way; a request that orders by a field has no ranking rule.
"""
import json
import re

import pytest

from conftest import _run_reveal_in

DOCS = {
    'alpha.md': '---\ntitle: Alpha\ntype: guide\n---\n# Alpha\n\nauthentication. See [beta](beta.md).\n',
    'beta.md': '---\ntitle: Beta\ntype: reference\n---\n# Beta\n\nauthentication authentication. [alpha](alpha.md)\n',
    'plain.md': '# Plain\n\nLinks [alpha](alpha.md).\n',
    'lonely.md': '---\ntitle: Lonely\n---\nNo links.\n',
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    for name, text in DOCS.items():
        (tmp_path / 'docs').mkdir(exist_ok=True)
        (tmp_path / 'docs' / name).write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _text(root, *argv):
    run = _run_reveal_in(root, *argv)
    assert run.returncode == 0, run.stderr
    return run.stdout


def test_the_listing_header_names_the_request_as_flags(root):
    out = _text(root, 'markdown', 'docs', '--where', 'type=guide', '--match', 'authentication', '--explain',
                '--limit', '1')
    assert 'Filter: --where type=guide --match authentication --explain --limit 1' in out, out
    assert '?' not in out.split('Filter:', 1)[1].splitlines()[0] and 'explain=True' not in out


def test_a_plain_listing_has_no_filter_line(root):
    assert 'Filter:' not in _text(root, 'markdown', 'docs')


def _count(out, word):
    return int(re.search(rf'(\d+) {word}', out).group(1))


def test_the_link_graph_prints_one_number_per_word_and_points_to_its_rules(root):
    out = _text(root, 'markdown', 'docs', '--view', 'links')
    listed = re.search(r'Orphans \((\d+)\)', out)
    assert listed and int(listed.group(1)) == _count(out, 'orphans'), out
    assert 'files that link out' not in out and 'files with no links' not in out
    assert 'Rules: --format json (_meta.known_limits)' in out


def test_the_link_graph_json_carries_the_definitions(root):
    doc = json.loads(_run_reveal_in(root, 'markdown', 'docs', '--view', 'links', '--format', 'json').stdout)
    limits = doc['_meta']['known_limits']
    assert any(line.startswith('orphans:') for line in limits) and any(line.startswith('isolated:') for line in limits)
    assert sorted(doc['orphans']) == ['lonely.md', 'plain.md'] and doc['isolated'] == ['lonely.md']


def test_a_ranked_match_points_to_its_ranking_rule(root):
    out = _text(root, 'markdown', 'docs', '--match', 'authentication')
    assert 'Rules: --format json (_meta.known_limits)' in out
    doc = json.loads(_run_reveal_in(root, 'markdown', 'docs', '--match', 'authentication', '--format', 'json').stdout)
    assert 'relevance_score' in doc['_meta']['known_limits'][0]


@pytest.mark.parametrize('argv', [['--match', 'authentication', '--sort', 'title'], ['--where', 'type=guide']],
                         ids=['sorted by a field', 'no match'])
def test_an_unranked_listing_has_no_ranking_rule(root, argv):
    assert 'Rules:' not in _text(root, 'markdown', 'docs', *argv)
