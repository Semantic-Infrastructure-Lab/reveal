"""BACK-2599 controls for the overview comparison (``overview --against``): the standing McCabe caveat goes behind the
one Rules pointer only on an answer that prints the pointer; a side's request-specific warning stays visible, and a
failed comparison (which prints no pointer) keeps the caveat in full."""
from reveal.rendering.diff import architecture_diff_text

MCCABE = 'complexity is McCabe cyclomatic complexity (a count of decision points), not weighted by nesting depth.'
RULE = 'Rule: fan-in and fan-out count static imports between files under the scanned path.'


def _report(**extra):
    report = {
        'path': 'proj', 'base_ref': 'HEAD', 'head_ref': 'working tree',
        'analysis': {'complete': True, 'basis': 'snapshots', 'snapshots': {'base': {}, 'head': {}}},
        'edge_rule': {'text': RULE},
        'deltas': {'fan_in': [], 'fan_out': [], 'circular_groups': {'introduced': [], 'resolved': []},
                   'component_coupling': [],
                   'complexity_centroid': {'top_n': 20, 'base': 1.0, 'head': 1.0, 'change': 0.0},
                   'entry_points': {'added': [], 'removed': []}},
        'meta': {'warnings': [
            {'type': 'complexity_is_unweighted', 'message': f'base: {MCCABE}', 'snapshot': 'base'},
            {'type': 'complexity_is_unweighted', 'message': f'head: {MCCABE}', 'snapshot': 'head'},
            {'type': 'analysis_failed', 'message': 'head: 1 file failed to parse', 'snapshot': 'head'}]}}
    report.update(extra)
    return report


def test_comparison_points_at_the_standing_caveat_and_keeps_side_warnings():
    text = architecture_diff_text(_report(), title='Overview Diff')
    assert text.splitlines().count('Rules: --format json (edge_rule.text, meta.warnings)') == 1
    assert MCCABE not in text and RULE not in text
    assert '  ⚠ head: 1 file failed to parse' in text.splitlines()


def test_failed_comparison_keeps_the_caveat_in_full():
    report = _report(error='base snapshot failed')
    text = architecture_diff_text(report, title='Overview Diff')
    assert 'Rules: ' not in text
    assert f'  ⚠ base and head: {MCCABE}' in text.splitlines()
