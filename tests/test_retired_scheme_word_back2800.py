"""A bare word naming a retired scheme teaches that scheme's RETIREMENTS row, not the scheme (BACK-2800).

``reveal stats PATH`` (``classify``, ``depends``: schemes with no subcommand) is no command and no path, so the path read
refused it with "stats is a URI noun: reveal stats://PATH", which teaches a spelling that itself retires
(COMMAND_MODEL "Retirement notes": no replacement names a spelling that itself retires). The row names the answer
that replaces it (``reveal metrics PATH``); a removed scheme (python://) has no adapter left, and its row still teaches.
An unretired URI-only noun keeps its hint, an unknown word stays a missing path and a path of that name is read.
"""
import pytest

from conftest import _run_reveal_in, invalid_request_document
from reveal.cli.invocation import RETIREMENTS

RETIRED_URI_ONLY = ['stats', 'classify', 'depends', 'python']


@pytest.mark.parametrize('scheme', RETIRED_URI_ONLY)
def test_a_word_naming_a_retired_scheme_teaches_its_row(tmp_path, scheme):
    row = RETIREMENTS[f'scheme:{scheme}']
    result = _run_reveal_in(tmp_path, scheme, '.')
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr.splitlines()[0] == f'Error: {row.text}', result.stderr
    assert 'URI noun' not in result.stderr and 'not found' not in result.stderr


@pytest.mark.parametrize('scheme', RETIRED_URI_ONLY)
def test_json_answers_the_path_reads_document_with_the_rows_text(tmp_path, scheme):
    row = RETIREMENTS[f'scheme:{scheme}']
    result = _run_reveal_in(tmp_path, scheme, '.', '--format', 'json')
    document = invalid_request_document(result)
    assert document is not None, result.stdout[:300]
    assert (document['type'], document['source'], document['error']) == ('file_structure', scheme, row.text)


def test_control_an_unretired_uri_only_noun_keeps_its_hint(tmp_path):
    result = _run_reveal_in(tmp_path, 'nginx', 'src with spaces')
    assert result.returncode == 2
    assert result.stderr.splitlines()[0] == "Error: nginx is a URI noun: reveal 'nginx://src with spaces'"


def test_control_an_unknown_word_is_a_missing_path(tmp_path):
    result = _run_reveal_in(tmp_path, 'nosuchword', '.')
    assert result.returncode == 2
    assert 'nosuchword not found' in result.stderr


def test_control_a_path_of_that_name_is_read(tmp_path):
    (tmp_path / 'stats').mkdir()
    (tmp_path / 'stats' / 'inner.py').write_text('def inner():\n    return 1\n', encoding='utf-8')
    result = _run_reveal_in(tmp_path, 'stats')
    assert result.returncode == 0, result.stderr
    assert 'inner.py' in result.stdout
