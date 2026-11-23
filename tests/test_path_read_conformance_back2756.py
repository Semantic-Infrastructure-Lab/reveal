"""Path-read conformance gaps found by the element pseudo-noun (BACK-2756, cells 3, 21j and 22).

Cell 3 (D1 A): an element request (``FILE ELEMENT --view V`` and the other element controls) given a flag the main
parser has no option for (``--offset``, ``--where``, ``--match``, ``--detail``, ``--tests``, ``--against``, an unknown
flag) exits 2 with rule 3's one message, naming the flag and the element controls, as ``--limit`` and ``--since``
already did; it used to get argparse's usage error. A path read that is not an element request (the file view,
element extraction, ``--outline``, ``--head``, a directory) keeps BACK-522's scoped usage line: it has no declaration
to name. URI targets keep their noun's message, subcommands their own parser.
"""
import pytest

from reveal.nav_params import ELEMENT_VIEW_SPECS
from reveal.utils.query_binding import unsupported_controls_message
from test_vocabulary_conformance_back2654 import ELEMENT_FILE, _run, element_workspace  # noqa: F401  (the fixture)

ELEMENT = 'process_order'
VIEW = ('--view', 'boundary')

# --- cell 3: flags the main parser does not have, on an element request ------------------------------------------

UNPARSED_CONTROLS = [('--offset', '1'), ('--where', 'name=x'), ('--match', 'x'), ('--detail', 'full'),
                     ('--tests',), ('--against', 'x'), ('--zz-unknown', '1')]


def _scoped_usage(run) -> bool:
    """BACK-522's usage error: the scoped usage line, argparse's message, the help pointer."""
    return (run.rc == 2 and run.out == '' and run.err.startswith('usage: reveal [options]')
            and 'unrecognized arguments:' in run.err)


@pytest.mark.parametrize('extra', UNPARSED_CONTROLS, ids=[words[0] for words in UNPARSED_CONTROLS])
def test_an_element_request_teaches_a_flag_the_main_parser_lacks(element_workspace, extra):
    run = _run(ELEMENT_FILE, ELEMENT, *VIEW, *extra)
    message = unsupported_controls_message(ELEMENT_VIEW_SPECS, [extra[0]])
    assert run.rc == 2 and run.out == '', run.brief()
    assert run.err == f'reveal: error: {message}\n'


def test_every_unknown_flag_is_named_once(element_workspace):
    run = _run(ELEMENT_FILE, ELEMENT, *VIEW, '--zz-a', '--offset', '1', '--zz-a')
    assert run.rc == 2
    assert run.err == f"reveal: error: {unsupported_controls_message(ELEMENT_VIEW_SPECS, ['--zz-a', '--offset'])}\n"


@pytest.mark.parametrize('selection', [('--varflow', 'order'), ('--view', 'flow', '--kind', 'if'), ('--outline',)],
                         ids=['varflow', 'flow-kind', 'code-element-outline'])
def test_every_element_control_makes_it_an_element_request(element_workspace, selection):
    run = _run(ELEMENT_FILE, ELEMENT, *selection, '--zz-unknown')
    assert run.rc == 2 and 'usage:' not in run.err, run.brief()
    assert "unsupported control '--zz-unknown'; supported controls: view," in run.err


@pytest.mark.parametrize('argv', [
    (ELEMENT_FILE, ELEMENT, '--zz-unknown'),         # element extraction: no element control
    (ELEMENT_FILE, '--zz-unknown'),                  # the file view
    (ELEMENT_FILE, '--outline', '--zz-unknown'),     # the file outline
    (ELEMENT_FILE, '--head', '2', '--zz-unknown'),   # a slice of the file
    ('proj', '--zz-unknown'),                         # a directory
    (ELEMENT_FILE, ELEMENT, '--offset', '1'),         # a shared control on element extraction
], ids=['extraction', 'file', 'outline', 'head', 'directory', 'extraction-offset'])
def test_a_path_read_that_is_no_element_request_keeps_the_scoped_usage(element_workspace, argv):
    """Control (D1 A): no declaration to name, so BACK-522's scoped usage line stands."""
    assert _scoped_usage(_run(*argv)), _run(*argv).err


def test_a_known_flag_the_element_request_does_not_read_keeps_its_refusal(element_workspace):
    """Control: --limit is the main parser's own flag; the element request's refusal (U1) is unchanged."""
    run = _run(ELEMENT_FILE, ELEMENT, *VIEW, '--limit', '1')
    assert run.rc == 2 and run.err == f"error: {unsupported_controls_message(ELEMENT_VIEW_SPECS, ['--limit'])}\n"


def test_a_declared_uri_keeps_its_noun_message(element_workspace):
    """Control: a URI target is taught by its noun, not by the element declarations."""
    run = _run('ast://proj', '--zz-unknown')
    assert run.rc == 2 and "unsupported control '--zz-unknown'" in run.err and 'supported controls: view' not in run.err


def test_mcp_reveal_run_gives_the_same_teaching(element_workspace):
    """reveal_run answers a refused request as its error text (a tool error on the registered tool)."""
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    text = reveal_run([ELEMENT_FILE, ELEMENT, *VIEW, '--offset', '1'])
    assert text.startswith('[reveal error:') and 'usage:' not in text
    assert unsupported_controls_message(ELEMENT_VIEW_SPECS, ['--offset']) in text


# The owner of cell 3's message (beside the URI's, uri_flag_message), unit by unit: one answer per route the main parser's error reaches.
def _reread(*argv):
    from reveal.cli.parser import create_argument_parser
    args, _unknown = create_argument_parser('').parse_known_args(list(argv))
    return args


@pytest.mark.parametrize('argv, message, taught', [
    ((ELEMENT_FILE, ELEMENT, *VIEW), 'unrecognized arguments: --zz 1', True),            # an element request
    ((ELEMENT_FILE, ELEMENT, '--varflow', 'order'), 'unrecognized arguments: --zz', True),
    ((ELEMENT_FILE, ELEMENT, '--outline'), 'unrecognized arguments: --zz', True),         # the code-element outline
    ((ELEMENT_FILE, ELEMENT), 'unrecognized arguments: --zz', False),                     # element extraction
    (('proj/README.md', 'Intro', '--outline'), 'unrecognized arguments: --zz', False),    # a Markdown outline
    ((ELEMENT_FILE,), 'unrecognized arguments: --zz', False),                             # the file view
    (('proj',), 'unrecognized arguments: --zz', False),                                   # a directory
    (('ast://proj', ELEMENT, *VIEW), 'unrecognized arguments: --zz', False),              # a URI: its noun's message
    (('@targets.txt', *VIEW), 'unrecognized arguments: --zz', False),                     # an @file list
    ((ELEMENT_FILE, ELEMENT, *VIEW), 'argument --head: expected one argument', False),    # another usage error
    ((ELEMENT_FILE, ELEMENT, *VIEW), 'unrecognized arguments: extra', False),             # an extra positional
], ids=['element-view', 'varflow', 'code-element-outline', 'extraction', 'markdown-outline', 'file', 'directory', 'uri', 'at-file', 'other-error', 'positional'])
def test_path_read_flag_message_answers_only_element_requests(argv, message, taught):
    from reveal.cli.routing.declared import path_read_flag_message
    flags = [word for word in message.partition(':')[2].split() if word.startswith('-')]
    expected = unsupported_controls_message(ELEMENT_VIEW_SPECS, flags) if taught else None
    assert path_read_flag_message(_reread(*argv), message) == expected


@pytest.mark.parametrize('target, path_read', [('a.py', True), ('proj/', True), ('-', True), ('ast://proj', False),
                                               ('@list.txt', False), ('', False), (None, False)])
def test_is_path_read(target, path_read):
    from reveal.cli.routing.declared import is_path_read
    assert is_path_read(target) is path_read


# --- cell 21j: an invalid path read in --format json answers the invalid-request document ------------------------
# D2: the document's type is the facet the declarations use (element_view, code_element, file_structure; a directory's
# tree), its source the path as typed; stderr says the error once under the file route's label, ``Error (PATH):``.

from test_vocabulary_conformance_back2654 import _invalid_document  # noqa: E402

# (label, argv before --format json, the document's type, a word the error names)
INVALID_IN_JSON = [
    # refused by the main parser (argparse): cell 3's teaching, choices, a missing value, an extra argument
    ('element unknown flag', (ELEMENT_FILE, ELEMENT, *VIEW, '--zz-unknown'), 'element_view', "'--zz-unknown'"),
    # a missing value stops argparse's re-read: the request is read from its positionals, format and output, so the
    # document names the answer the positionals select, as a noun's names its default answer (``_typed_defaults``)
    ('element missing value', (ELEMENT_FILE, ELEMENT, *VIEW, '--varflow'), 'code_element', '--varflow'),
    ('element extra argument', (ELEMENT_FILE, ELEMENT, *VIEW, 'extra'), 'element_view', 'extra'),
    ('extraction unknown flag', (ELEMENT_FILE, ELEMENT, '--zz-unknown'), 'code_element', '--zz-unknown'),
    ('file unknown flag', (ELEMENT_FILE, '--zz-unknown'), 'file_structure', '--zz-unknown'),
    ('outline unknown flag', (ELEMENT_FILE, '--outline', '--zz-unknown'), 'file_structure', '--zz-unknown'),
    ('head missing value', (ELEMENT_FILE, '--head'), 'file_structure', '--head'),
    ('head not a number', (ELEMENT_FILE, '--head', 'abc'), 'file_structure', '--head'),
    ('directory unknown flag', ('proj', '--zz-unknown'), 'directory_tree', '--zz-unknown'),
    # refused after parsing: the binder, the element request's own refusal (U1), rule 4
    ('view outside its choices', (ELEMENT_FILE, ELEMENT, '--view', 'nosuch'), 'element_view', 'nosuch'),
    ('two views', (ELEMENT_FILE, ELEMENT, '--boundary', '--exits'), 'element_view', 'boundary'),
    ('kind unread by boundary', (ELEMENT_FILE, ELEMENT, *VIEW, '--kind', 'if'), 'element_view', 'kind'),
    ('main-parser flag unread', (ELEMENT_FILE, ELEMENT, *VIEW, '--limit', '1'), 'element_view', "'--limit'"),
    ('verbose is detail', (ELEMENT_FILE, ELEMENT, *VIEW, '--verbose'), 'element_view', 'detail'),
    # a malformed stdout sink
    ('malformed --output', (ELEMENT_FILE, ELEMENT, *VIEW, '--output', 'zz-sink'), 'element_view', 'zz-sink'),
]


@pytest.mark.parametrize('label, argv, answer_type, named', INVALID_IN_JSON, ids=[row[0] for row in INVALID_IN_JSON])
def test_an_invalid_path_read_in_json_answers_the_document(element_workspace, label, argv, answer_type, named):
    import json
    run = _run(*argv, '--format', 'json')
    assert _invalid_document(run, named, source=argv[0]), f'{run.brief()}; stdout {run.out[:120]!r}'
    doc = json.loads(run.out)
    assert doc['type'] == answer_type
    assert run.err.count(doc['error']) == 1 and f"Error ({argv[0]}): {doc['error']}" in run.err
    assert 'usage:' not in run.err


def test_a_missing_config_on_a_transitive_view_answers_the_document(element_workspace, monkeypatch):
    """ConfigValidationError, raised by the transitive walk, is an invalid request like the others."""
    monkeypatch.setenv('REVEAL_CONFIG', 'no-such-dir/reveal.yaml')
    run = _run(ELEMENT_FILE, ELEMENT, *VIEW, '--transitive', '--format', 'json')
    assert _invalid_document(run, 'no-such-dir', source=ELEMENT_FILE), run.brief()


@pytest.mark.parametrize('label, argv, answer_type, named', INVALID_IN_JSON, ids=[row[0] for row in INVALID_IN_JSON])
def test_text_mode_keeps_its_usage_error(element_workspace, label, argv, answer_type, named):
    """Control: the same requests in text mode print no document and no file-route label (argparse's usage, or the
    owner's ``error:`` line), stdout empty."""
    run = _run(*argv)
    assert run.rc == 2 and run.out == '' and named in run.err, run.brief()
    assert f'Error ({argv[0]})' not in run.err and 'contract_version' not in run.err


def test_a_failed_analysis_is_not_an_invalid_request(element_workspace, tmp_path):
    """Control: a file that fails to parse is a failed answer (exit 3), not refused before analysis; the route's
    JSON-mode refusal does not reach it."""
    import json
    (element_workspace / 'bad.xml').write_text('<a><b></a>', encoding='utf-8')
    run = _run('bad.xml', '--format', 'json')
    assert run.rc == 3
    errors = (json.loads(run.out).get('meta') or {}).get('errors') or [] if run.out.strip() else []
    assert [e.get('code') for e in errors] != ['invalid_request']


def test_mcp_reveal_run_in_json_returns_the_document(element_workspace):
    import json
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    text = reveal_run([ELEMENT_FILE, ELEMENT, *VIEW, '--zz-unknown', '--format', 'json'])
    assert text.startswith('[reveal error: {')
    doc = json.loads(text[len('[reveal error: '):-1])
    assert doc['type'] == 'element_view' and [e['code'] for e in doc['meta']['errors']] == ['invalid_request']


# The owner of the path read's invalid-request document, unit by unit (declared.invalid_path_read): the routes the
# main parser and the file route hand it, and the targets it leaves to their own owners.
@pytest.mark.parametrize('argv, answer_type', [
    ((ELEMENT_FILE, ELEMENT, *VIEW), 'element_view'),
    ((ELEMENT_FILE, ELEMENT, '--outline'), 'element_view'),
    ((ELEMENT_FILE, ELEMENT), 'code_element'),
    ((ELEMENT_FILE,), 'file_structure'),
    ((ELEMENT_FILE, '--head', '2'), 'file_structure'),
    (('no-such.py',), 'file_structure'),
    (('proj',), 'directory_tree'),
    (('ast://proj',), None),
    (('@targets.txt',), None),
], ids=['element-view', 'code-element-outline', 'extraction', 'file', 'head', 'missing', 'directory', 'uri', 'at-file'])
def test_invalid_path_read_names_the_declared_facet(element_workspace, argv, answer_type):
    from reveal.cli.routing.declared import invalid_path_read
    from reveal.errors import RequestValidationError
    error = RequestValidationError('bad request')
    answer = invalid_path_read(argv[0], 'bad request', _reread(*argv), error=error)
    if answer_type is None:
        assert answer is None
        return
    assert answer.result['type'] == answer_type and answer.result['source'] == argv[0]
    assert [e['code'] for e in answer.result['meta']['errors']] == ['invalid_request']
    assert answer.request_error is not None and str(answer.request_error) == 'bad request'
