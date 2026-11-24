"""typed.answer_path_read and the path read's keywords (BACK-2325, D21, ruling S1 K-A).

The keywords are the main parser's long flags with ``-`` as ``_``, minus what is no control of a file or directory read
(output and process options, path-less and element-less modes, the element's own controls, help): read from the
parser and the existing declarations, never a typed list. ``_answer_document`` is the document an answer prints.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import __version__
from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.typed import _answer_document, answer_path_read, path_read_options, path_read_words
from reveal.cli.routing.uri import Answer
from reveal.errors import PathNotFoundError, RequestValidationError, UnsupportedOverrideError
from reveal.utils.invocation_log import log_scope
from reveal.utils.request_cache import host_request


@pytest.fixture
def parser():
    return create_argument_parser(__version__)


def test_the_keywords_are_the_path_reads_flags(parser):
    options = path_read_options(parser)
    for keyword in ('head', 'tail', 'range', 'outline', 'depth', 'max_entries', 'files', 'ext', 'exclude',
                    'respect_gitignore', 'fallback', 'grep', 'name', 'type', 'sort', 'links', 'link_type',
                    'frontmatter', 'related', 'metadata', 'typed', 'server_name', 'breadcrumbs'):
        assert keyword in options, keyword
    assert options['link_type'][0] == '--link-type'


@pytest.mark.parametrize('keyword', ['format', 'output', 'also_json', 'fail_on', 'copy', 'verbose', 'provenance',
                                     'stdin', 'meta', 'check', 'agent_help', 'rules', 'view', 'boundary', 'varflow',
                                     'scope', 'section', 'help', 'version'])
def test_output_options_modes_and_element_controls_are_not_keywords(parser, keyword):
    assert keyword not in path_read_options(parser)


def test_the_words_render_values_as_flags(parser):
    assert path_read_words(parser, {'head': 2, 'outline': True, 'files': False}) == ['--head=2', '--outline']
    assert path_read_words(parser, {'range': (2, 4)}) == ['--range=2-4']
    assert path_read_words(parser, {'exclude': ['a', 'b']}) == ['--exclude=a', '--exclude=b']


def test_an_unknown_keyword_is_refused_and_an_analyzer_word_names_its_flag(parser):
    with pytest.raises(UnsupportedOverrideError, match="'bogus'"):
        path_read_words(parser, {'bogus': 1})
    with pytest.raises(UnsupportedOverrideError) as caught:
        path_read_words(parser, {'extract_links': True})
    assert "'extract_links' is the analyzer's word that links=, " in str(caught.value)
    with pytest.raises(UnsupportedOverrideError, match="'inline_code' is the analyzer's word that inline= sets"):
        path_read_words(parser, {'inline_code': True})


def test_answer_document_reads_the_renderers_document_else_the_json_answer():
    assert _answer_document(Answer({'a': 1}, 'structure', lambda *a, **k: None)) == {'a': 1}
    built = Answer({'a': 1}, 'structure', lambda *a, **k: None, document=lambda: {'b': 2})
    assert _answer_document(built) == {'b': 2}
    assert _answer_document(Answer({}, 'structure', lambda *a, **k: None, document=lambda: None)) is None


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def foo():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'notes.md').write_text('# T\n\n[a](ok.py)\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _answer(path, **controls):
    with host_request(), log_scope(to_stderr=False):
        return answer_path_read(path, controls)


def test_it_answers_the_clis_document_and_prints_nothing(fx, capsys):
    expected = json.loads(_run_reveal_direct('ok.py', '--format', 'json').stdout)
    capsys.readouterr()
    assert _answer('ok.py') == expected
    assert capsys.readouterr() == ('', '')


def test_a_missing_path_raises_path_not_found(fx):
    with pytest.raises(PathNotFoundError):
        _answer('missing.py')


def test_a_file_line_spelling_is_an_element_read(fx):
    with pytest.raises(RequestValidationError, match=r"api.element\('ok.py', ':1'\)"):
        _answer('ok.py:1')


def test_a_request_that_prints_no_document_is_refused(fx):
    with pytest.raises(RequestValidationError, match='prints no JSON document'):
        _answer('notes.md', related_flat=True, related=True)


# --- the element read (api.element): reveal PATH ELEMENT, through the same route ---------------------------------------------

def _element(path, element):
    with host_request(), log_scope(to_stderr=False):
        return answer_path_read(path, {}, element)


@pytest.mark.parametrize('element', ['foo', ':1', '@1', 'function:1'])
def test_an_element_answers_the_clis_document_and_prints_nothing(fx, capsys, element):
    expected = json.loads(_run_reveal_direct('ok.py', element, '--format', 'json').stdout)
    capsys.readouterr()
    assert _element('ok.py', element) == expected
    assert capsys.readouterr() == ('', '')


def test_an_element_miss_raises_element_not_found(fx):
    from reveal.errors import ElementNotFoundError
    with pytest.raises(ElementNotFoundError, match=r"^Element 'nosuch' not found in ok.py$"):
        _element('ok.py', 'nosuch')


def test_an_element_that_starts_with_a_dash_stays_the_element(fx):
    from reveal.errors import ElementNotFoundError
    with pytest.raises(ElementNotFoundError, match="'-x'"):
        _element('ok.py', '-x')


def test_an_element_is_a_string(fx):
    with pytest.raises(TypeError, match='element of a path read is a string'):
        _element('ok.py', 3)
