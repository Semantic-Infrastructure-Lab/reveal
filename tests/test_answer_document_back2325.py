"""``uri.Answer.document`` (BACK-2325, D21): the JSON document an answer prints with ``--format json``, for an answer
whose renderer builds that document from more than ``result`` (the file route's envelope). The Python API reads it to
return the CLI's own document; nothing else calls it.

Shared owner: ``cli/routing/uri.py``. Effect on every other route and transport: none. Every producer leaves it None
(the document stays ``json_answer(result)``), ``emit`` never calls it (a text answer never builds a document), and it
takes no part in the answer's ``repr`` or equality.
"""
import pytest

from reveal.cli.routing.uri import Answer
from reveal.file_handler import handle_file
from reveal.utils.invocation_log import current_log, log_scope

pytestmark = [pytest.mark.unit]


def _printer(answer, **options):
    print('printed', answer.result['n'])


def test_an_answer_has_no_document_unless_its_producer_gives_one():
    assert Answer({'n': 1}, 'structure', _printer).document is None


def test_emit_prints_and_never_builds_the_document(capsys):
    built = []

    def document():
        built.append(True)
        return {'type': 'doc'}

    answer = Answer({'n': 1}, 'structure', _printer, document=document)
    answer.emit()
    assert capsys.readouterr().out == 'printed 1\n'
    assert built == []
    assert answer.document() == {'type': 'doc'} and built == [True]


def test_the_document_is_not_part_of_repr_or_equality():
    first = Answer({'n': 1}, 'structure', _printer, document=lambda: {'a': 1})
    second = Answer({'n': 1}, 'structure', _printer, document=lambda: {'b': 2})
    assert first == second
    assert 'document' not in repr(first)


def test_the_file_route_answer_carries_the_document_it_prints(tmp_path, capsys):
    # The file structure's Answer (BACK-2762) carries the document its renderer prints (BACK-2325, step A3): the
    # Python API reads it; emitting never calls it.
    import json
    path = tmp_path / 'ok.py'
    path.write_text('def ok():\n    return 1\n', encoding='utf-8')
    with log_scope(to_stderr=False):
        handle_file(str(path), None, False, 'json')
        answer = current_log().last_answer
        document = answer.document() if answer is not None and answer.document is not None else None
    assert answer is not None and answer.kind == 'structure'
    assert document == json.loads(capsys.readouterr().out)
