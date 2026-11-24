"""declared.path_read_refusal: the Answer of a refused path read prints the site's text exactly, answers the path read's
document in JSON, exits with the site's code, and carries what the Python API raises and MCP reads (BACK-2325)."""
import json

import pytest

from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.declared import PathReadRefused, path_read_refusal
from reveal.errors import PathNotFoundError
from reveal.utils.results import FailureCause, execution_exit_code

TEXT = 'Error: missing.py not found\nHint: Running from /somewhere\n'


def _args(*argv):
    return create_argument_parser('test').parse_args(list(argv))


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_emit_prints_the_sites_text_and_exits_with_its_code(capsys, fmt):
    answer = path_read_refusal('missing.py', TEXT, _args('missing.py', '--format', fmt), exit_code=2)
    with pytest.raises(SystemExit) as exited:
        answer.emit()
    out, err = capsys.readouterr()
    assert exited.value.code == 2 and err == TEXT
    if fmt == 'text':
        assert out == ''
    else:
        document = json.loads(out)
        assert document['type'] == 'file_structure' and document['source'] == 'missing.py'
        assert document['error'] == 'missing.py not found'
        assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': 'missing.py not found'}]


def test_a_legacy_exit_code_is_kept_and_the_label_is_stripped(capsys):
    text = '❌ Error: --related only works with markdown files\n\nLearn more: reveal help://markdown\n'
    answer = path_read_refusal('ok.py', text, _args('ok.py', '--format', 'json'), exit_code=1)
    with pytest.raises(SystemExit) as exited:
        answer.emit()
    out, err = capsys.readouterr()
    assert exited.value.code == 1 and err == text
    assert json.loads(out)['error'] == '--related only works with markdown files'


def test_the_answer_carries_the_request_error_and_the_mcp_diagnostic():
    error = PathNotFoundError('missing.py not found')
    answer = path_read_refusal('missing.py', TEXT, _args('missing.py'), error=error)
    assert execution_exit_code(answer.execution_facts) == 2
    assert type(answer.request_error) is PathNotFoundError and str(answer.request_error) == 'missing.py not found'
    assert answer.exception is None
    assert answer.public_diagnostic == TEXT.strip()
    assert PathReadRefused(answer).answer is answer


def test_an_unreadable_file_carries_its_os_error_as_an_analysis_failure():
    error = PermissionError(13, 'Permission denied', 'denied.py')
    answer = path_read_refusal('denied.py', 'Error: cannot read denied.py: Permission denied\n', _args('denied.py'),
                               exit_code=3, error=error, cause=FailureCause.ANALYSIS)
    assert execution_exit_code(answer.execution_facts) == 3
    assert answer.exception is error and answer.request_error is None
    assert answer.result['meta']['errors'] == [{'code': 'analysis', 'message': 'cannot read denied.py: Permission denied'}]


def test_an_element_read_and_a_directory_take_their_facets(tmp_path):
    (tmp_path / 'd').mkdir()
    assert path_read_refusal('x.py', 'Error: x\n', _args('x.py', 'foo')).result['type'] == 'code_element'
    assert path_read_refusal(str(tmp_path / 'd'), 'Error: x\n', _args(str(tmp_path / 'd'))).result['type'] == \
        'directory_tree'


def test_an_invalid_request_without_an_error_of_its_own_carries_one_with_the_documents_message():
    from reveal.errors import RequestValidationError
    answer = path_read_refusal('x.rst', "Error: No analyzer found for file 'x.rst'\n\nContext:\n", _args('x.rst'))
    assert type(answer.request_error) is RequestValidationError
    assert str(answer.request_error) == "No analyzer found for file 'x.rst'" == answer.result['error']


# diagnostic= (BACK-2775): an element read of a file whose structure failed prints the file route's own line; the cause
# is what the document, the Python API and MCP say.
_FAILED = 'Error (bad.xml): XML parse error: mismatched tag: line 1, column 8\n'
_CAUSE = 'XML parse error: mismatched tag: line 1, column 8'


def test_a_diagnostic_is_the_documents_message_and_the_callers_text(capsys):
    answer = path_read_refusal('bad.xml', _FAILED, _args('bad.xml', 'b', '--format', 'json'), exit_code=3,
                               cause=FailureCause.ANALYSIS, diagnostic=_CAUSE)
    assert answer.public_diagnostic == _CAUSE and answer.exception is None and answer.request_error is None
    with pytest.raises(SystemExit) as exited:
        answer.emit()
    out, err = capsys.readouterr()
    assert exited.value.code == 3 and err == _FAILED
    document = json.loads(out)
    assert document['type'] == 'code_element' and document['error'] == _CAUSE
    assert document['meta']['errors'] == [{'code': 'analysis', 'message': _CAUSE}]


def test_an_invalid_request_with_a_diagnostic_carries_it_as_the_request_error():
    cause = 'Invalid ZIP archive: File is not a zip file'
    answer = path_read_refusal('bad.docx', f'Error (bad.docx): {cause}\n', _args('bad.docx', 'x'), diagnostic=cause)
    assert execution_exit_code(answer.execution_facts) == 2
    assert type(answer.request_error).__name__ == 'RequestValidationError' and str(answer.request_error) == cause
    assert answer.public_diagnostic == cause
