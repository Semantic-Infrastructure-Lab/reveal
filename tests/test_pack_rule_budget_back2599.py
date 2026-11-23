"""BACK-2599: pack's standing not-requested notice moves behind the Rules pointer; a requested graph signal that could
not be built is a request-specific failure and keeps its stderr warning (BACK-2599 note #1)."""

import io
from contextlib import redirect_stderr

from reveal.rendering.adapters.pack import RELEVANCE_NOT_REQUESTED, PackRenderer, pack_rule_lines

FAILED = ('fan-in not computed; the optional import graph is unavailable (OSError) -- files are ranked by '
          'filename/entry-point heuristics and recency only')


def _stderr(meta):
    err = io.StringIO()
    with redirect_stderr(err):
        PackRenderer._advisories({'meta': meta})
    return err.getvalue()


def test_standing_notice_is_the_pointer_and_next_step_not_a_warning():
    result = {'meta': {'relevance_warning': RELEVANCE_NOT_REQUESTED}}
    assert pack_rule_lines(result) == [
        'Rules: --format json (meta.relevance_warning)',
        'Next: --architecture ranks by import fan-in; --focus PATTERN by graph relevance']
    assert _stderr(result['meta']) == ''


def test_failed_graph_keeps_its_stderr_warning_and_no_pointer():
    """Control: the failure sentence is not the standing one, so it is neither hidden nor pointed at."""
    meta = {'relevance_warning': FAILED}
    assert pack_rule_lines({'meta': meta}) == []
    assert _stderr(meta) == f'Warning: {FAILED}\n'


def test_mcp_layout_leaves_out_the_standing_notice_but_points_at_the_edge_rule():
    assert pack_rule_lines({'meta': {'relevance_warning': RELEVANCE_NOT_REQUESTED}}, relevance_note=False) == []
    ranked = {'meta': {}, 'edge_rule': {'text': 'Rule: fan-in counts static imports ...'}}
    assert pack_rule_lines(ranked, relevance_note=False) == ['Rules: --format json (edge_rule.text)']
