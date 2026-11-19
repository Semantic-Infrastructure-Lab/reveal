"""A patches scan with no test files names the declared controls it could not use with the one shared warning (BACK-2696).

Under a directory with no test files, ``patches://pkg`` declines (not applicable, exit 0): there is no scan for ``limit``,
``min``, ``--all`` and the other scan controls to shape. Which target has test files only the data can tell, so the
request is valid and the controls are named once in the shared ``control_unread_by_data`` warning (COMMAND_MODEL
"Applicability", Scott 2026-11-18 Q2), as JSON names ``sort`` on a value that is not a list. The unused-input ledger
(``unused_query_param``, ``unused_flag``) must not fire on a declared noun (Q3): it named them instead.
"""
import json

import pytest

from conftest import _run_reveal_direct as run

_LEDGER = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def project(tmp_path, monkeypatch):
    """``pkg`` has code and no test file; ``withtests`` has one test that patches a target."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'app.py').write_text('def serve(x):\n    return x\n', encoding='utf-8')
    (tmp_path / 'withtests' / 'tests').mkdir(parents=True)
    (tmp_path / 'withtests' / 'tests' / 'test_a.py').write_text(
        'from unittest import mock\n\n\ndef test_x():\n    with mock.patch("os.getcwd"):\n        pass\n',
        encoding='utf-8')
    return tmp_path


def _warnings(doc):
    return [warning for warning in (doc.get('meta') or {}).get('warnings') or []]


def _codes(doc):
    return [warning.get('code') or warning.get('type') for warning in _warnings(doc)]


def _json(*argv):
    response = run(*argv, '--format', 'json')
    assert response.returncode == 0, (argv, response.stdout, response.stderr)
    return json.loads(response.stdout)


# (argv, the control the shared warning names): URI keys, a flag after the URI, and the subcommand's flags.
NO_TESTS = [
    (('patches://pkg?limit=0',), 'limit'),
    (('patches://pkg', '--all'), 'limit'),
    (('patches', 'pkg', '--all'), 'limit'),
    (('patches://pkg?min=2',), 'min'),
    (('patches', 'pkg', '--min', '2'), 'min'),
    (('patches://pkg?target=serve',), 'target'),
    (('patches', 'pkg', '--limit', '0'), 'limit'),
]


@pytest.mark.parametrize('argv,control', NO_TESTS, ids=[' '.join(argv) for argv, _control in NO_TESTS])
def test_no_test_files_names_the_control_in_the_one_shared_warning(project, argv, control):
    doc = _json(*argv)
    assert 'not_applicable' in _codes(doc)
    ledger = [warning for warning in _warnings(doc) if (warning.get('code') or warning.get('type')) in _LEDGER]
    assert not ledger, f'the ledger named a declared control: {ledger}'
    shared = [warning for warning in _warnings(doc) if warning.get('code') == 'control_unread_by_data']
    assert len(shared) == 1 and shared[0]['fields'] == [control], _warnings(doc)
    assert 'has no effect on this data' in shared[0]['message']


def test_no_test_files_through_mcp_carries_the_shared_warning(project):
    """Transports: MCP answers the CLI's JSON."""
    from reveal.mcp_server import reveal_query
    doc = json.loads(reveal_query('patches://pkg?limit=0', provenance=True))
    assert 'control_unread_by_data' in _codes(doc) and not set(_codes(doc)) & set(_LEDGER), _warnings(doc)


def test_no_test_files_in_text_mode_says_it_once(project):
    """Text is as honest as JSON: the warning prints once under the not-applicable answer, as JSON's own Q2 warning
    prints under its answer, and the ledger's note is gone."""
    response = run('patches://pkg?limit=0')
    text = response.stdout + response.stderr
    assert response.returncode == 0, text
    assert text.count("'limit' has no effect on this data") == 1, text
    assert 'has no effect on this patches:// query' not in text, text


@pytest.mark.parametrize('argv', [('patches://withtests?limit=0',), ('patches://withtests', '--all'),
                                  ('patches', 'withtests', '--min', '2'), ('patches://pkg',)],
                         ids=['tests ?limit=0', 'tests --all', 'tests subcommand --min', 'no tests, no control'])
def test_a_scan_that_reads_its_controls_or_none_given_stays_quiet(project, argv):
    """Siblings: with test files present the scan reads its controls; with none given there is nothing to name."""
    doc = _json(*argv)
    assert not {'control_unread_by_data', *_LEDGER} & set(_codes(doc)), _warnings(doc)
