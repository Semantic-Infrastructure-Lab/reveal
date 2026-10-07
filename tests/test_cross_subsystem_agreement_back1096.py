"""Oracle-free cross-subsystem agreement (BACK-1096, slice 2).

Two implementations answering the same question must agree; a disagreement
proves one is wrong without saying which.  Pairs from the consistency audit's
"Not assessed" list (REVEAL_CROSS_SUBSYSTEM_CONSISTENCY_AUDIT_2026-08-10.md).
"""
import re
from collections import Counter

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.adapters.stats import StatsAdapter
from reveal.cli.file_checker import check_and_collect_file
from reveal.registry import get_analyzer
from reveal.rules import RuleRegistry
from reveal.rules.maintainability.M101 import M101

pytestmark = [pytest.mark.component]


@pytest.fixture(autouse=True)
def serial_pools(monkeypatch):
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')


# ---------------------------------------------------------------- line counts

FILLER = ''.join('x%d = %d\n' % (i, i) for i in range(520))   # > M101's 500-line floor
TAIL = 'def tail():\n    return 1\n'
DISAGREE = 'stats:// and M101 count str.splitlines() (it also splits on \\x0c, \\x85, \\u2028); ast:// and editors count \\n'


def _spell(label):
    """(text, bom) for a 522-line file whose last line ends a function."""
    odd = {'formfeed': '\x0c\n', 'u2028': 's = "a b"\n', 'nel': 's = "a\x85b"\n'}
    text = FILLER + odd.get(label, '') + TAIL
    if label in ('crlf', 'bom_crlf'):
        text = text.replace('\n', '\r\n')
    if label == 'no_final_newline':
        text = text.rstrip('\n')
    return text, label.startswith('bom')


LINE_VARIANTS = [
    'lf', 'crlf', 'bom', 'bom_crlf', 'no_final_newline',
    pytest.param('formfeed', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
    pytest.param('u2028', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
    pytest.param('nel', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
]


def _line_counts(tmp_path, label):
    text, bom = _spell(label)
    path = tmp_path / 'sample.py'
    path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
    analyzer = get_analyzer(str(path))(str(path))
    last_function_end = analyzer.get_structure()['functions'][-1]['line_end']
    stats_total = StatsAdapter(str(path)).get_structure()['files'][0]['lines']['total']
    (detection,) = M101().check(str(path), None, analyzer.content)
    m101_total = int(re.search(r'([\d,]+) lines', detection.context).group(1).replace(',', ''))
    return last_function_end, stats_total, m101_total


@pytest.mark.parametrize('label', LINE_VARIANTS)
def test_stats_m101_and_ast_agree_on_line_count(tmp_path, label):
    last_function_end, stats_total, m101_total = _line_counts(tmp_path, label)
    assert last_function_end == 522, 'positive control: the file ends where its last function ends'
    assert stats_total == m101_total == last_function_end


def test_empty_file_has_zero_lines_in_every_counter(tmp_path):
    path = tmp_path / 'empty.py'
    path.write_text('', encoding='utf-8')
    assert StatsAdapter(str(path)).get_structure()['files'][0]['lines']['total'] == 0
    assert M101().check(str(path), None, '') == []


# ------------------------------------------------- check --select vs rule.check

KITCHEN_SINK = '''import os, sys
import os


def f(a, b=[], c={}):
    try:
        x = 1
    except:
        pass
    if a == None:
        print("hi")
    for i in range(10):
        for j in range(10):
            for k in range(10):
                if i and j or k:
                    while True:
                        if a:
                            return 1
    eval("1")
    return x  # TODO fix ''' + 'y' * 200 + '''


class A:
    pass
'''


def _key(detection):
    return (detection.rule_code, detection.line, detection.column, detection.message)


def test_select_one_rule_equals_calling_that_rule_directly(tmp_path):
    path = tmp_path / 'sink.py'
    path.write_text(KITCHEN_SINK, encoding='utf-8')
    RuleRegistry.discover()
    analyzer = get_analyzer(str(path))(str(path))
    structure, content = analyzer.get_structure(extract_links=True), analyzer.content
    fired, compared = set(), 0
    for rule_class in RuleRegistry.get_rules():
        if not rule_class.matches_target(str(path)):
            continue
        rule = RuleRegistry.get_configured_rule(rule_class.code, str(path))
        direct = [_key(d) for d in rule.check(str(path), structure, content) or []]
        _, routed, status = check_and_collect_file(path, tmp_path, [rule_class.code], None)
        assert status['status'] in ('ok', 'warning'), (rule_class.code, status)
        assert [_key(d) for d in routed] == direct, rule_class.code
        compared += 1
        if direct:
            fired.add(rule_class.code)
    assert compared >= 20 and len(fired) >= 5, 'positive control: rules must actually fire here'


def test_unselected_run_is_the_union_of_single_rule_runs(tmp_path):
    path = tmp_path / 'sink.py'
    path.write_text(KITCHEN_SINK, encoding='utf-8')
    RuleRegistry.discover()
    _, everything, _ = check_and_collect_file(path, tmp_path, None, None)
    union = Counter()
    for rule_class in RuleRegistry.get_rules():
        _, routed, _ = check_and_collect_file(path, tmp_path, [rule_class.code], None)
        union.update(_key(d) for d in routed)
        assert {d.rule_code for d in routed} <= {rule_class.code}, 'select leaked another rule'
    assert Counter(_key(d) for d in everything) == union
    assert len(union) >= 5
