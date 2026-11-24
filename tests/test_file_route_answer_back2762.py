"""The file route emits its structure as an Answer the invocation log keeps (BACK-2762).

A host running the CLI's own dispatch (MCP ``reveal_run``, and ``reveal_structure`` over it) maps the outcome from the
answer's facts, as for a URI (COMMAND_MODEL "Transports"). The file route printed its structure without one, so a file
that failed to parse (exit 3) read as a success to the host. Effect on other routes: ``handle_file``'s element, nav,
``--meta`` and special-flag branches emit no structure and log nothing (a control below); the URI router already logs.
"""
import pytest

from reveal.file_handler import handle_file
from reveal.utils.invocation_log import current_log, log_scope
from reveal.utils.results import AnalysisCompleteness, execution_failed


def _logged(path, *, element=None, output_format='text'):
    with log_scope(to_stderr=False):
        code = 0
        try:
            handle_file(str(path), element, False, output_format)
        except SystemExit as exc:
            code = exc.code
        return code, current_log().last_answer


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'bad.xml').write_text('<root></bad>', encoding='utf-8')
    (tmp_path / 'shape.ipynb').write_text('[]', encoding='utf-8')
    (tmp_path / 'ok.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'syn.py').write_text('def f(:\n  pass\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('name,code,cause', [
    ('bad.xml', 3, 'XML parse error'),
    ('shape.ipynb', 2, 'not a notebook'),
])
@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_a_failed_structure_is_logged_with_its_facts_and_public_cause(root, capsys, name, code, cause, output_format):
    exit_code, answer = _logged(root / name, output_format=output_format)
    assert exit_code == code
    assert answer is not None and answer.kind == 'structure'
    assert execution_failed(answer.execution_facts)
    assert cause in answer.public_diagnostic
    assert answer.result.get('error') == answer.public_diagnostic
    capsys.readouterr()


@pytest.mark.parametrize('name', ['ok.py', 'syn.py'])
def test_an_answered_structure_is_logged_with_no_diagnostic(root, capsys, name):
    exit_code, answer = _logged(root / name)
    assert exit_code == 0
    assert answer is not None and answer.kind == 'structure'
    assert not execution_failed(answer.execution_facts)
    assert answer.execution_facts.completeness is AnalysisCompleteness.COMPLETE
    assert answer.public_diagnostic is None
    capsys.readouterr()


def test_an_element_read_logs_its_element_answer_not_the_structure(root, capsys):
    """Control: the element branch prints the element, not the structure, and logs the element's own Answer (BACK-2325:
    an element read is an Answer too, so MCP maps its outcome from its facts)."""
    exit_code, answer = _logged(root / 'ok.py', element='ok')
    assert exit_code == 0
    assert answer is not None and answer.kind == 'element'
    assert answer.execution_facts.completeness is AnalysisCompleteness.COMPLETE
    assert 'return 1' in capsys.readouterr().out


def test_the_failed_structure_still_prints_its_document_and_error_line(root, capsys):
    """Control: emitting through the Answer still prints the JSON document on stdout and the cause on stderr."""
    with log_scope(to_stderr=False):
        try:
            handle_file(str(root / 'bad.xml'), None, False, 'json')
        except SystemExit:
            pass
    out = capsys.readouterr()
    assert '"error": "XML parse error' in out.out
    assert 'XML parse error' in out.err
