"""A capped failure warning loses nothing in JSON: ``failures`` lists every subject (BACK-2659, D8).

A warning such as ``analysis_failed`` names five files in ``files`` and ``message``, counts the rest and
gives the cause classes. Until step 4 the per-file stderr lines carried the other names and the full
reason, also beside a JSON answer; they are no longer printed there, so the JSON itself must carry them
(COMMAND_MODEL "Transports": every diagnostic the CLI prints to stderr is in that JSON first; dropping one
is not a fix, BACK-1998). Each capped warning therefore carries ``failures``: every subject it counts,
uncapped, as ``{path, cause, reason}``, built once by the shared builder. ``files`` and ``message`` are
unchanged.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from reveal.adapters.ast.analysis import parse_recovered_warning
from reveal.adapters.claude.handlers.workspace import skipped_entries_warning
from reveal.adapters.markdown.files import unreadable_warning
from reveal.analyzers.imports.diagnostics import parse_failure_warning
from reveal.reveal_types import PathFailure
from reveal.utils.parallel import worker_lost_warning
from reveal.utils.path_utils import analysis_skipped_warning, traversal_failed_warning

pytestmark = pytest.mark.component

BOM = b'\xef\xbb\xbf'
REASON = 'invalid Python source: unexpected U+FEFF after UTF-8 BOM (line 1:1)'
NAMES = [f'f{n}.py' for n in range(7)]


def _cli(cwd, *argv):
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(cwd / 'xdg'))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=cwd, timeout=180)


def _assert_capped_and_complete(warning, count, spelled):
    """``files``/``message`` stay capped at five; ``failures`` names every subject, as ``files`` spells it."""
    assert warning['count'] == count
    assert len(warning['files']) == 5 and f"and {count - 5} more" in warning['message']
    assert spelled[5] not in warning['message']
    paths = [record['path'] for record in warning['failures']]
    assert paths == sorted(spelled) and len(paths) == count
    assert warning['files'] == paths[:5]


# --- the shared builders ---------------------------------------------------------------------------

def test_analysis_failed_lists_every_file_with_its_cause_class_and_full_reason(tmp_path):
    skipped = [(str(tmp_path / name), f'PermissionError: denied #{n}') for n, name in enumerate(NAMES)]
    warning = analysis_skipped_warning(skipped, tmp_path)
    _assert_capped_and_complete(warning, 7, NAMES)
    assert warning['failures'][6] == {'path': 'f6.py', 'cause': 'PermissionError', 'reason': 'PermissionError: denied #6'}
    assert '(PermissionError)' in warning['message']


def test_a_reason_names_the_file_as_the_answer_does_not_by_its_absolute_path(tmp_path):
    """``str(OSError)`` embeds the absolute filename (BACK-2249): the reason spells it as ``path`` does."""
    target = tmp_path / 'pkg' / 'a.py'
    reason = f"PermissionError: [Errno 13] Permission denied: '{target}'"
    (record,) = analysis_skipped_warning([(str(target), reason)], tmp_path)['failures']
    assert record == {'path': 'pkg/a.py', 'cause': 'PermissionError',
                      'reason': "PermissionError: [Errno 13] Permission denied: 'pkg/a.py'"}
    assert str(tmp_path) not in json.dumps(record)


def test_analysis_incomplete_lists_every_directory_and_unlocated_event(tmp_path):
    failures = [PathFailure(str(tmp_path / f'd{n}'), 'PermissionError: Permission denied') for n in range(7)]
    failures.append(PathFailure(None, 'OSError: lost'))
    warning = traversal_failed_warning(failures, tmp_path)
    assert warning['count'] == 7 and len(warning['directories']) == 5
    assert warning['failures'][0] == {'path': None, 'cause': 'OSError', 'reason': 'OSError: lost'}
    assert [r['path'] for r in warning['failures'][1:]] == [f'd{n}' for n in range(7)]
    assert all(r['cause'] == 'PermissionError' for r in warning['failures'][1:])


@pytest.mark.parametrize('build,kind', [
    (lambda paths, base: worker_lost_warning(paths, 'their results are missing', base), 'worker_lost'),
    (lambda paths, base: parse_failure_warning(paths, base), 'partial_parse'),
], ids=['worker_lost', 'partial_parse'])
def test_a_single_cause_warning_lists_every_file_under_its_own_kind(tmp_path, build, kind):
    warning = build([str(tmp_path / name) for name in NAMES], tmp_path)
    _assert_capped_and_complete(warning, 7, NAMES)
    assert all(record == {'path': record['path'], 'cause': kind} for record in warning['failures'])


def test_parse_recovered_lists_every_file():
    warning = parse_recovered_warning([{'file': f'src/{name}', 'parse_recovered': True} for name in NAMES])
    _assert_capped_and_complete(warning, 7, [f'src/{name}' for name in NAMES])
    assert {record['cause'] for record in warning['failures']} == {'parse_recovered'}


def test_unreadable_markdown_files_are_listed_with_their_reasons(tmp_path):
    unreadable = [(str(tmp_path / f'd{n}.md'), 'UnicodeDecodeError: invalid start byte') for n in range(7)]
    warning = unreadable_warning(unreadable, 'their links are missing', tmp_path)
    _assert_capped_and_complete(warning, 7, [f'd{n}.md' for n in range(7)])
    assert warning['failures'][0]['cause'] == 'UnicodeDecodeError'
    assert warning['failures'][0]['reason'] == 'UnicodeDecodeError: invalid start byte'


def test_skipped_claude_entries_are_listed_without_the_absolute_path(tmp_path):
    skipped = [(tmp_path / f'e{n}.md', PermissionError(13, 'Permission denied', str(tmp_path / f'e{n}.md')))
               for n in range(7)]
    warning = skipped_entries_warning('plans', iter(skipped))
    _assert_capped_and_complete(warning, 7, [f'e{n}.md' for n in range(7)])
    assert warning['failures'][0] == {'path': 'e0.md', 'cause': 'PermissionError',
                                      'reason': 'PermissionError: Permission denied'}
    assert str(tmp_path) not in json.dumps(warning['failures'])


def test_no_failure_is_still_no_warning(tmp_path):
    """Negative control: the builders' None for an empty input is unchanged."""
    assert analysis_skipped_warning([], tmp_path) is None
    assert traversal_failed_warning([], tmp_path) is None
    assert worker_lost_warning([], 'x') is None
    assert parse_failure_warning([]) is None
    assert parse_recovered_warning([{'file': 'a.py'}]) is None
    assert unreadable_warning([], 'x') is None
    assert skipped_entries_warning('plans', []) is None


# --- the hand-built capped warnings ----------------------------------------------------------------

def test_diff_side_analysis_failed_lists_every_file():
    from reveal.adapters.diff.adapter import DiffAdapter
    sides = SimpleNamespace(left_uri='git://HEAD~1/', right_uri='git://HEAD/')
    skipped = {name: f'SyntaxError: bad {name}' for name in NAMES}
    (warning,) = DiffAdapter._skipped_warnings(sides, {'skipped_files': skipped}, {})
    _assert_capped_and_complete(warning, 7, NAMES)
    assert warning['failures'][6] == {'path': 'f6.py', 'cause': 'SyntaxError', 'reason': 'SyntaxError: bad f6.py'}


def test_pack_file_measurement_failures_are_listed_past_five():
    from reveal.adapters import pack
    failures = tuple((name, 'stat', 'PermissionError: Permission denied') for name in NAMES)
    meta = {}
    pack._record_file_measurement_warning(failures, meta)
    (warning,) = meta['warnings']
    assert len(warning['files']) == 5 and 'omitted' in warning['message']
    assert [r['path'] for r in warning['failures']] == NAMES
    assert warning['failures'][0] == {'path': 'f0.py', 'cause': 'PermissionError',
                                      'reason': 'PermissionError: Permission denied (stat)'}


def test_xlsx_unsearched_sheet_is_listed_with_its_reason(tmp_path):
    from test_xlsx_part_errors_back1853 import _search, _sheet_book
    result = _search(_sheet_book(tmp_path, bad_sheet2=True), 'two')
    (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'sheets_unsearched']
    (record,) = warning['failures']
    assert record['path'] == 'S2' and 'corrupt or malformed XML' in record['reason']


def test_metrics_failures_list_every_file(tmp_path):
    from reveal.adapters.stats.adapter import StatsAdapter
    adapter = StatsAdapter(str(tmp_path))
    adapter._traversal_failures = []
    adapter._analysis_failures = (
        [{'file': f'p{n}.py', 'parse_degraded': True, 'parse_error_line': n + 1} for n in range(7)]
        + [{'file': f'r{n}.py', 'check_rules_failed': True} for n in range(7)]
        + [{'path': str(tmp_path / f'x{n}.py'), 'analysis_failed': f'ValueError: broken {n}'} for n in range(7)])
    result = {'summary': {}}
    adapter._disclose_failures(result)
    warnings = {w['type']: w for w in result['meta']['warnings']}
    degraded, rules, failed = warnings['parse_degraded'], warnings['check_rules_failed'], warnings['analysis_failed']
    _assert_capped_and_complete(degraded, 7, [f'p{n}.py' for n in range(7)])
    assert degraded['failures'][6] == {'path': 'p6.py', 'cause': 'parse_degraded', 'reason': 'parse error at line 7'}
    _assert_capped_and_complete(rules, 7, [f'r{n}.py' for n in range(7)])
    _assert_capped_and_complete(failed, 7, [f'x{n}.py' for n in range(7)])
    assert failed['failures'][6] == {'path': 'x6.py', 'cause': 'ValueError', 'reason': 'ValueError: broken 6'}


# --- through the CLI: the D8 cases -----------------------------------------------------------------

def _bom_files(root, count):
    root.mkdir()
    for n in range(count):
        (root / f'b{n}.py').write_bytes(BOM * 2 + b'x = 1\n')
    return root


@pytest.mark.cli
def test_ast_json_answer_names_every_failed_file_and_its_full_reason(tmp_path):
    """Seven failed files: the JSON names all seven and the full reason the text answer's lines print."""
    root = _bom_files(tmp_path / 'proj', 7)
    result = _cli(tmp_path, f'ast://{root.as_posix()}', '--format', 'json')
    assert result.stderr == ''
    (warning,) = [w for w in json.loads(result.stdout)['meta']['warnings'] if w['type'] == 'analysis_failed']
    spelled = [(root / f'b{n}.py').as_posix() for n in range(7)]
    _assert_capped_and_complete(warning, 7, spelled)
    assert {record['reason'] for record in warning['failures']} == {REASON}
    assert {record['cause'] for record in warning['failures']} == {'invalid Python source'}
    text = _cli(tmp_path, f'ast://{root.as_posix()}')
    for path in spelled:  # every file and reason the text answer prints is in the JSON
        assert f'Failed to analyze {Path(path)}: {REASON}' in text.stderr


@pytest.mark.cli
def test_a_clean_answer_has_no_failures_field(tmp_path):
    """Negative control: nothing failed, so no warning and no ``failures`` anywhere in the answer."""
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    result = _cli(tmp_path, f'ast://{root.as_posix()}', '--format', 'json')
    assert result.returncode == 0 and result.stderr == ''
    assert '"failures"' not in result.stdout


# --- the shared record builder (failure_records) ---------------------------------------------------

def test_failure_records_spell_sort_and_classify(tmp_path):
    from reveal.utils.path_utils import failure_records
    records = failure_records([(str(tmp_path / 'b.py'), 'OSError: x'), (None, 'ValueError: y'),
                               (str(tmp_path / 'a.py'), 'invalid Python source: z')], tmp_path)
    assert records == [{'path': None, 'cause': 'ValueError', 'reason': 'ValueError: y'},
                       {'path': 'a.py', 'cause': 'invalid Python source', 'reason': 'invalid Python source: z'},
                       {'path': 'b.py', 'cause': 'OSError', 'reason': 'OSError: x'}]


def test_failure_records_without_a_reason_take_the_given_cause_and_keep_posix_spelling():
    from reveal.utils.path_utils import failure_records
    assert failure_records([('pkg\\a.py', None)], cause='worker_lost') == [  # noqa: win-path
        {'path': 'pkg/a.py', 'cause': 'worker_lost'}]


def test_traversal_failures_arriving_as_lists_are_listed(tmp_path):
    """Failures that crossed a pool or a JSON cache arrive as lists, not ``PathFailure`` tuples."""
    warning = traversal_failed_warning([[str(tmp_path / 'd'), 'PermissionError: x']] * 2, tmp_path)
    assert warning['failures'] == [{'path': 'd', 'cause': 'PermissionError', 'reason': 'PermissionError: x'}]


@pytest.mark.cli
@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='needs POSIX permissions that bind the current user')
@pytest.mark.parametrize('noun', ['imports', 'metrics'])
def test_a_real_unreadable_file_is_listed_with_its_reason_and_no_absolute_path(tmp_path, noun):
    """A denied read's ``str(OSError)`` names the absolute file; an answer that spells files relatively
    (imports' own spelling, metrics' base) spells it relatively in the reason too (BACK-2249)."""
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'ok.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    locked = root / 'locked.py'
    locked.write_text('x = 1\n', encoding='utf-8')
    locked.chmod(0)
    try:
        result = _cli(tmp_path, f'{noun}://{root.as_posix()}', '--format', 'json')
    finally:
        locked.chmod(0o644)
    assert result.stderr == ''
    records = [r for w in json.loads(result.stdout)['meta']['warnings'] for r in w.get('failures', ())]
    assert [(r['path'], r['cause']) for r in records] == [('locked.py', 'PermissionError')]
    assert 'Permission denied' in records[0]['reason'] and root.as_posix() not in records[0]['reason']
