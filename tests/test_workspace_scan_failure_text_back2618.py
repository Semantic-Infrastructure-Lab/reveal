"""The shared workspace-list receipt names a failure's cause without its path (BACK-2618 Step 3, BACK-2249).

``utils.workspace_scan.WorkspaceScan`` records every lost entry or directory in ``meta.workspace_analysis.failures``.
Its ``message`` was ``str(error)``: for an OSError that is ``[Errno 13] Permission denied: '/abs/path'``, the host path
again beside the ``source`` field that already carries it, POSIX-spelled (the BACK-2249 class the ``oserror-cause``
ratchet counts in f-strings, which this ``str()`` call escaped). It is now ``path_utils.failure_of(error).cause``:
class and strerror only. Codex's workspace lists use the same receipt with their own counting rule, so the rule is a
constructor argument whose default is Claude's text, unchanged.
"""
from pathlib import Path, PureWindowsPath

from reveal.utils.workspace_scan import WorkspaceScan

_CLAUDE_RULE = ('Named entries after project scope and before content/display filters; analyzed plus failed equals '
                'candidates; required ordering/discovery failures count separately; aliases remain separate entries')


def _failures(scan):
    return scan.attach({})['meta']['workspace_analysis']['failures']


def test_an_oserror_failure_names_its_cause_and_keeps_the_path_in_source():
    scan = WorkspaceScan()
    scan.discovery_errors.append((Path('/abs/secret-dir'), PermissionError(13, 'Permission denied', '/abs/secret-dir')))
    scan.entry_errors.append((PureWindowsPath('C:/home/x.md'),
                              PermissionError(13, 'Permission denied', 'C:\\home\\x.md')))
    failures = _failures(scan)
    assert [f['message'] for f in failures] == ['PermissionError: Permission denied'] * 2
    assert [f['source'] for f in failures] == ['/abs/secret-dir', 'C:/home/x.md']
    assert all('secret' not in f['message'] and 'home' not in f['message'] for f in failures)


def test_a_non_oserror_failure_keeps_its_message_with_its_class():
    """An error that names no path keeps its text, with its class in front (failure_of's one spelling)."""
    scan = WorkspaceScan()
    scan.entry_errors.append((Path('/m/plugin.json'), ValueError('plugin manifest is not a JSON object')))
    assert _failures(scan)[0]['message'] == 'ValueError: plugin manifest is not a JSON object'
    assert _failures(scan)[0]['cause'] == 'ValueError'


def test_the_default_counting_rule_is_claudes_unchanged():
    """Negative control: Claude's receipts keep their counting rule."""
    assert WorkspaceScan().attach({})['meta']['workspace_analysis']['count_rule'] == _CLAUDE_RULE


def test_the_counting_rule_is_the_callers():
    rule = 'Files under the Codex directory, before display cuts'
    assert WorkspaceScan(count_rule=rule).attach({})['meta']['workspace_analysis']['count_rule'] == rule


def test_claudes_reexport_is_the_shared_class():
    from reveal.adapters.claude.workspace_scan import WorkspaceScan as ClaudeScan
    assert ClaudeScan is WorkspaceScan
