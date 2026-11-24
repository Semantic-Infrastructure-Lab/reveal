"""file_handler.handle_file(..., answer_consumer=): the file structure's Answer and a refusal's (no analyzer, an
unreadable file) go to the consumer instead of being printed, as handle_uri hands its answers (BACK-2325). The
document an Answer carries is the one ``--format json`` prints. Without a consumer nothing changes for the text CLI."""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct
from reveal.cli.parser import create_argument_parser
from reveal.file_handler import handle_file
from reveal.utils.results import execution_exit_code


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def foo():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'bad.xml').write_text('<a><b></a>\n', encoding='utf-8')
    (tmp_path / 'README.rst').write_text('Title\n=====\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _consume(path, *flags):
    args = create_argument_parser('test').parse_args([path, *flags, '--format', 'json'])
    answers = []
    handle_file(path, None, False, 'json', args, answer_consumer=answers.append)
    return answers


@pytest.mark.parametrize('name, code', [('ok.py', 0), ('bad.xml', 3)])
def test_the_structure_answer_goes_to_the_consumer_with_the_printed_document(fx, capsys, name, code):
    answers = _consume(name)
    assert capsys.readouterr() == ('', ''), 'nothing printed, not even the failed file\'s error line'
    [answer] = answers
    assert execution_exit_code(answer.execution_facts) == code
    assert answer.document() == json.loads(_run_reveal_direct(name, '--format', 'json').stdout)


def test_a_file_no_analyzer_reads_hands_its_refusal_to_the_consumer(fx, capsys):
    [answer] = _consume('README.rst')
    assert capsys.readouterr() == ('', '')
    assert execution_exit_code(answer.execution_facts) == 2
    assert str(answer.request_error) == "No analyzer found for file 'README.rst' (extension: .rst)"


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows')
@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')
def test_an_unreadable_file_hands_its_os_error_to_the_consumer(fx, capsys):
    (fx / 'denied.py').write_text('x = 1\n', encoding='utf-8')
    os.chmod(fx / 'denied.py', 0)
    try:
        [answer] = _consume('denied.py')
    finally:
        os.chmod(fx / 'denied.py', 0o644)
    assert capsys.readouterr() == ('', '')
    assert execution_exit_code(answer.execution_facts) == 3 and isinstance(answer.exception, PermissionError)


@pytest.mark.parametrize('argv, code', [(['ok.py'], 0), (['bad.xml'], 3), (['README.rst'], 2)])
def test_sibling_without_a_consumer_the_text_cli_is_unchanged(fx, argv, code):
    run = _run_reveal_direct(*argv)
    assert run.returncode == code
    if code == 2:
        assert run.stdout == '' and run.stderr.startswith("Error: No analyzer found for file 'README.rst'")
    if code == 3:
        assert run.stderr.startswith('Error (bad.xml): XML parse error')


# --- the element read (BACK-2325, BACK-2775): an Answer too ----------------------------------------------------------------

def _consume_element(path, element):
    args = create_argument_parser('test').parse_args([path, element, '--format', 'json'])
    answers = []
    handle_file(path, element, False, 'json', args, answer_consumer=answers.append)
    return answers


def test_an_element_answer_goes_to_the_consumer_with_the_printed_document(fx, capsys):
    [answer] = _consume_element('ok.py', 'foo')
    assert capsys.readouterr() == ('', '')
    assert answer.kind == 'element' and execution_exit_code(answer.execution_facts) == 0
    assert answer.document() == json.loads(_run_reveal_direct('ok.py', 'foo', '--format', 'json').stdout)


def test_a_miss_hands_its_element_not_found_refusal_to_the_consumer(fx, capsys):
    from reveal.errors import ElementNotFoundError
    [answer] = _consume_element('ok.py', 'nosuch')
    assert capsys.readouterr() == ('', '')
    assert execution_exit_code(answer.execution_facts) == 2
    assert type(answer.request_error) is ElementNotFoundError and answer.request_error.element == 'nosuch'
    assert str(answer.request_error) == "Element 'nosuch' not found in ok.py"
    assert answer.public_diagnostic.startswith("Error: Element 'nosuch' not found in ok.py\nHint:")


def test_a_miss_of_a_file_whose_parse_failed_hands_the_failure_with_its_cause(fx, capsys):
    [answer] = _consume_element('bad.xml', 'b')
    assert capsys.readouterr() == ('', '')
    assert execution_exit_code(answer.execution_facts) == 3
    assert answer.public_diagnostic == 'XML parse error: mismatched tag: line 1, column 8'
    assert answer.exception is None and answer.request_error is None
    assert answer.result['type'] == 'code_element' and answer.result['error'] == answer.public_diagnostic


def test_a_line_miss_of_a_broken_file_is_a_miss(fx, capsys):
    # A line read needs no structure: past the end is a miss, exit 2, whatever the parse said.
    [answer] = _consume_element('bad.xml', ':99')
    assert execution_exit_code(answer.execution_facts) == 2
    assert str(answer.request_error) == 'Line 99 is past the end of bad.xml (1 lines)'


@pytest.mark.parametrize('argv, code', [(['ok.py', 'foo'], 0), (['ok.py', 'nosuch'], 2), (['bad.xml', ':1'], 0)])
def test_sibling_without_a_consumer_the_element_text_is_unchanged(fx, argv, code):
    run = _run_reveal_direct(*argv)
    assert run.returncode == code
    if code == 0:
        assert run.stdout.startswith(f'{argv[0]}:')
    else:
        assert run.stdout == '' and run.stderr.startswith("Error: Element 'nosuch' not found in ok.py")
