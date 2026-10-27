"""codex:// /workflow and /timeline: a tool output preview stays on one line.

Current rollouts' `exec` outputs are multi-line ("Script completed" / "Wall
time ..." / "Output:" ...); the workflow row printed them raw and unindented,
breaking the two-lines-per-action layout.
"""

import contextlib
import io

from reveal.adapters.codex.analysis.timeline import _summarize
from reveal.adapters.codex.render_analytics import _render_codex_workflow

MULTI = 'Script completed\nWall time 10.2 seconds\nOutput:\n\n{"ok": true}'


def _workflow_text(output):
    ev = {'kind': 'tool_call', 'name': 'exec', 'arguments': '{}', 'success': True,
          'timestamp': '2026-10-22T10:00:00Z', 'output': output}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _render_codex_workflow({'events': [ev], 'total': 1})
    return buf.getvalue()


def test_workflow_preview_is_one_line():
    arrow = [line for line in _workflow_text(MULTI).splitlines() if '→' in line]
    assert arrow == ['      → Script completed Wall time 10.2 seconds Output: {"ok": true}']


def test_workflow_preview_reads_content_blocks():
    text = _workflow_text([{'type': 'input_text', 'text': 'line one\nline two'}])
    assert '      → line one line two' in text.splitlines()


def test_timeline_output_summary_is_one_line():
    summary = _summarize('response_item', {'type': 'function_call_output', 'output': MULTI})
    assert '\n' not in summary
    assert summary.startswith('→ Script completed Wall time')
