"""BACK-1624: overview counts messages (not JSONL records) and omits readme_present where no README sits beside the transcript."""
from claude_transcript_builder import (SESSION, assistant, install, prompt, run_json, run_text,
                                       tool_result, tool_use)


def _session():
    return [
        prompt(0, 'typed prompt one'),
        # one assistant message split over three records (thinking, text, tool_use) sharing an id
        assistant(1, [{'type': 'thinking', 'thinking': 'hm'}], 'msg_A'),
        assistant(2, [{'type': 'text', 'text': 'Reading.'}], 'msg_A'),
        assistant(3, [tool_use('t1', 'Read', file_path='/p/a.py')], 'msg_A'),
        tool_result(4, 't1', 'contents'),
        assistant(5, [{'type': 'text', 'text': 'Done.'}], 'msg_B'),
        prompt(6, [{'type': 'text', 'text': 'typed prompt two'}]),
        assistant(7, [{'type': 'text', 'text': 'Ok.'}], 'msg_C'),
    ]


def test_overview_counts_messages_not_records(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    out = run_json(f'claude://session/{SESSION}')
    assert out['user_messages'] == 2           # real prompts only
    assert out['tool_result_messages'] == 1   # tool results are their own count
    assert out['assistant_messages'] == 3     # msg_A, msg_B, msg_C
    # negative control: message_count is still the record count
    assert out['message_count'] == 8
    # the same fields on the summary view
    assert run_json(f'claude://session/{SESSION}?summary')['assistant_messages'] == 3


def test_overview_text_labels_the_counts(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    text = run_text(f'claude://session/{SESSION}')
    assert 'User: 2 | Assistant: 3 | Tool results: 1' in text
    assert 'Messages: 8 records' in text


def test_readme_present_omitted_when_no_readme_beside_transcript(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    out = run_json(f'claude://session/{SESSION}')
    assert 'readme_present' not in out
    assert 'README' not in run_text(f'claude://session/{SESSION}')


def test_readme_present_true_when_a_readme_sits_beside_the_transcript(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session(), extra_files={'README_2026-10-01.md': '# notes\n'})
    assert run_json(f'claude://session/{SESSION}')['readme_present'] is True
    assert 'README: ✓ present' in run_text(f'claude://session/{SESSION}')


def test_session_list_omits_readme_flag_without_readme(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    sessions = run_json('claude://sessions/')['recent_sessions']
    assert sessions and all('readme_present' not in s for s in sessions)
