"""reveal:// unknown section (BACK-2761, the half of BACK-2700 that did not land; D6: an invalid resource exits 2).

Before: ``reveal reveal://no-such`` printed ``Unknown reveal:// section 'no-such'. Sections: ...`` and exited 1 (the
findings code) on CLI text and JSON; the JSON document carried the error with an empty ``meta.errors``;
``api.query`` returned that document instead of raising; MCP said ``[reveal exited with code 1]``; a ``--stdin --batch``
entry had no ``exit_code``. Each transport now answers the invalid request: exit 2 naming the section and the real
ones, ``invalid_request`` in JSON with the answer's own type ``reveal_structure``, ``MissingResourceError`` from the
API, ``[reveal error: ...]`` on MCP, and a batch entry that exits 2 as the direct request does. Every real section,
the bare resource and ``--check`` answer as before.
"""
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct
from reveal.errors import MissingResourceError
from reveal.main import main

MESSAGE = "Unknown reveal:// section 'no-such'. Sections: config, analyzers, rules, adapters."


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _batch(*lines):
    """(batch exit code, the batch's entries) for `lines` piped to `reveal --stdin --batch --format json`."""
    out, err, code = io.StringIO(), io.StringIO(), 0
    with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', io.StringIO(''.join(f'{x}\n' for x in lines))):
        try:
            main(['reveal', '--stdin', '--batch', '--format', 'json'])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, json.loads(out.getvalue())['results']


def test_cli_text_exits_2_naming_the_section_and_no_answer():
    run = _run_reveal_direct('reveal://no-such')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert MESSAGE in run.stderr and not run.stdout.strip(), (run.stdout, run.stderr)


def test_cli_json_answers_the_invalid_request_document_with_the_answer_type():
    run, doc = _json('reveal://no-such')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert doc['type'] == 'reveal_structure', doc
    assert doc['error'] == MESSAGE
    assert [e['code'] for e in doc['meta']['errors']] == ['invalid_request'], doc['meta']
    assert run.stderr.count(MESSAGE) == 1, run.stderr


def test_a_section_that_names_a_source_file_keeps_its_hint():
    run = _run_reveal_direct('reveal://main.py')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert "Unknown reveal:// section 'main.py'" in run.stderr
    assert 'To read that source file: reveal ' in run.stderr and 'main.py' in run.stderr.rsplit('reveal ', 1)[1]


def test_the_api_raises_the_invalid_request():
    from reveal import api
    with pytest.raises(MissingResourceError) as raised:
        api.query('reveal://no-such')
    assert MESSAGE in str(raised.value)


def test_mcp_reports_the_invalid_request():
    pytest.importorskip('mcp')
    from reveal import mcp_server
    answer = mcp_server.reveal_query('reveal://no-such')
    assert answer.startswith('[reveal error: ') and MESSAGE in answer, answer
    assert 'exited with code 1' not in answer
    run = mcp_server.reveal_run(['reveal://no-such', '--format', 'json'])
    assert run.startswith('[reveal error: ') and MESSAGE in run, run


def test_a_batch_entry_exits_as_the_direct_request():
    code, (entry,) = _batch('reveal://no-such')
    assert entry['status'] == 'error' and MESSAGE in entry['error'], entry
    assert entry['exit_code'] == 2, entry
    assert code == 2


@pytest.mark.parametrize('resource', ['', 'config', 'analyzers', 'rules', 'adapters', 'Rules'])
def test_real_sections_answer_as_before(resource):
    """Negative control: every real section (case-insensitive, as before) and the bare resource answer, exit 0."""
    run, doc = _json(f'reveal://{resource}')
    assert run.returncode == 0, (resource, run.stderr)
    assert doc['type'] == 'reveal_structure' and 'error' not in doc, doc.get('error')


def test_check_answers_as_before():
    """Negative control: ``reveal:// --check`` is not a section read and keeps its answer."""
    run, doc = _json('reveal://', '--check', '--select', 'V001')
    assert run.returncode == 0, run.stderr
    assert 'error' not in doc
