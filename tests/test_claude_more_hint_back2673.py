"""The Claude session list and history headers name the cap's live flag when more rows exist (BACK-2673).

``--head`` on claude is a noted legacy modifier (its ``flag:claude.--head`` row names ``--limit N``), so a header that
tells the reader how to see more names ``--limit N``, not the spelling that answers with a deprecation note.
"""
from reveal.adapters.claude.render_sessions import _render_claude_history, _render_claude_session_list


def _session_list_header(capsys):
    _render_claude_session_list({'session_count': 9, 'displayed_count': 2,
                                 'recent_sessions': [{'session': 'a'}, {'session': 'b'}]})
    return capsys.readouterr().out.splitlines()[0]


def _history_header(capsys):
    _render_claude_history({'total_entries': 9, 'match_count': 9, 'displayed_count': 2,
                            'entries': [{'project': 'p', 'prompt': 'x'}, {'project': 'p', 'prompt': 'y'}]})
    return capsys.readouterr().out.splitlines()[0]


def test_the_session_list_header_names_limit_for_more(capsys):
    header = _session_list_header(capsys)
    assert '--limit N for more' in header and '--head' not in header, header


def test_the_history_header_names_limit_for_more(capsys):
    header = _history_header(capsys)
    assert '--limit N for more' in header and '--head' not in header, header


def test_a_complete_history_prints_no_more_hint(capsys):
    _render_claude_history({'total_entries': 2, 'match_count': 2, 'displayed_count': 2,
                            'entries': [{'project': 'p', 'prompt': 'x'}, {'project': 'p', 'prompt': 'y'}]})
    header = capsys.readouterr().out.splitlines()[0]
    assert 'for more' not in header, header
