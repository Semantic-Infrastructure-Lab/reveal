"""BACK-2130: L001 on an anchored link to a non-markdown file.

`[x](code.ts#L1)` used to reach `_extract_headings()` (a markdown-only method) on the
TypeScript analyzer: an AttributeError, a WARNING per link, and the link recorded as an
unavailable outcome.  Only markdown targets have heading anchors, so the anchor on any other
target is a declared, once-per-target 'skipped' outcome (the file's existence is still checked).
"""

import logging

import pytest

from reveal.rules import RuleRegistry
from reveal.rules.links.L001 import L001

pytestmark = pytest.mark.component


def _link(url, line=1):
    return {'text': 'x', 'url': url, 'line': line}


def _project(tmp_path, links, target_name='code.ts', target_text='export const a = 1;\n'):
    (tmp_path / 'a.md').write_text('\n'.join(f'[x]({u})' for u in links) + '\n', encoding='utf-8')
    if target_name:
        (tmp_path / target_name).write_text(target_text, encoding='utf-8')
    return {'links': [_link(u, i) for i, u in enumerate(links, 1)]}


def _check(tmp_path, links, **kw):
    structure = _project(tmp_path, links, **kw)
    rule = L001()
    found = rule.check(str(tmp_path / 'a.md'), structure, '\n'.join(f'[x]({u})' for u in links) + '\n')
    return rule, found


@pytest.mark.parametrize('name', ['code.ts', 'page.html', 'notes.txt', 'Makefile'])
def test_anchor_on_non_markdown_target_is_declared_not_an_error(tmp_path, caplog, name):
    with caplog.at_level(logging.WARNING):
        rule, found = _check(tmp_path, [f'{name}#L1'], target_name=name)
    assert found == []
    assert 'has no attribute' not in caplog.text and 'Failed to extract headings' not in caplog.text
    assert [o for o in rule.outcomes if o['status'] == 'unavailable'] == []
    skipped = [o for o in rule.outcomes if o['status'] == 'skipped']
    assert [o['subject'] for o in skipped] == [str(tmp_path / name)]
    assert 'anchor' in skipped[0]['reason'] and 'not markdown' in skipped[0]['reason']
    # the rest of the file was still checked: the rule is 'run' with the skip underneath it
    assert any(o['status'] == 'run' for o in rule.outcomes)


def test_the_declaration_reaches_the_coverage_ledger(tmp_path):
    structure = _project(tmp_path, ['code.ts#L1'])
    coverage = []
    RuleRegistry.check_file(str(tmp_path / 'a.md'), structure, '[x](code.ts#L1)\n',
                            select=['L001'], coverage=coverage)
    entry = next(e for e in coverage if e['rule'] == 'L001')
    assert entry['status'] == 'run'
    assert [s['status'] for s in entry['subjects'] if s['subject'] == str(tmp_path / 'code.ts')] == ['skipped']


def test_declared_once_per_target_however_many_links(tmp_path):
    rule, found = _check(tmp_path, ['code.ts#L1', 'code.ts#L2', 'code.ts#fn'])
    assert found == []
    assert [o['subject'] for o in rule.outcomes if o['status'] == 'skipped'] == [str(tmp_path / 'code.ts')]


def test_a_missing_code_file_with_an_anchor_is_still_broken(tmp_path):
    rule, found = _check(tmp_path, ['gone.ts#L1'], target_name=None)
    assert len(found) == 1 and 'gone.ts#L1' in found[0].message
    assert [o for o in rule.outcomes if o['status'] == 'skipped'] == []


def test_a_code_link_without_an_anchor_records_nothing(tmp_path):
    rule, found = _check(tmp_path, ['code.ts'])
    assert found == [] and rule.outcomes == []


def test_markdown_anchor_present_still_verifies_clean(tmp_path):
    rule, found = _check(tmp_path, ['b.md#sec'], target_name='b.md', target_text='# Other\n\n## Sec\n')
    assert found == [] and rule.outcomes == []


def test_markdown_anchor_missing_is_still_reported(tmp_path):
    rule, found = _check(tmp_path, ['b.md#nope'], target_name='b.md', target_text='# Other\n\n## Sec\n')
    assert len(found) == 1 and 'b.md#nope' in found[0].message
    assert rule.outcomes == []
