"""codex:// /digest: a multi-line thread title stays on the header line."""

import contextlib
import io

from reveal.adapters.codex.render_messages import _render_codex_digest


def test_digest_header_is_one_line():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _render_codex_digest({'session_id': 'abc', 'title': 'Run the suite\n\nthen report'})
    assert buf.getvalue().splitlines()[0] == 'Digest: abc — Run the suite then report'
