"""``reveal health`` on a code path is check's job: it answers with a note (BACK-2068 slice 3c, P3-1).

health stays the ops entry point (ssl://, domain://, mysql://, sqlite://, nginx .conf). A local code
target keeps its answer until the cut (D5) and prints one note naming ``reveal check``; ops targets
print none.
"""
import json

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import RETIREMENTS

KEY = 'target:health.code'


def _retired(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def test_the_row_names_check_and_the_ops_targets():
    entry = RETIREMENTS[KEY]
    assert entry.stage == 'note'
    assert 'reveal check <path>' in entry.replacement
    assert 'ssl://' in entry.replacement


def test_a_code_target_prints_one_note_and_carries_one_warning(tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    result = run('health', str(tmp_path), '--format', 'json')
    assert result.stderr.count(f'note: {RETIREMENTS[KEY].text}') == 1, result.stderr
    assert [w['field'] for w in _retired(json.loads(result.stdout))] == [KEY]


def test_a_code_target_still_answers_like_before(tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    result = run('health', str(tmp_path), '--format', 'json')
    assert result.returncode == 0
    row = json.loads(result.stdout)['results'][0]
    assert row['summary'].startswith('code: healthy')


def test_several_code_targets_note_once(tmp_path):
    for name in ('p', 'q'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'a.py').write_text('x = 1\n', encoding='utf-8')
    result = run('health', str(tmp_path / 'p'), str(tmp_path / 'q'))
    assert result.stderr.count('deprecated') == 1, result.stderr


def test_an_nginx_conf_is_an_ops_target_and_prints_no_note(tmp_path):
    conf = tmp_path / 'site.conf'
    conf.write_text('server {\n  listen 80;\n}\n', encoding='utf-8')
    result = run('health', str(conf))
    assert 'deprecated' not in result.stderr, result.stderr


def test_a_missing_path_prints_no_note(tmp_path):
    result = run('health', str(tmp_path / 'nope'))
    assert 'deprecated' not in result.stderr, result.stderr
