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
    from mcp.server.fastmcp.exceptions import ToolError
    from reveal.mcp_server import reveal_run
    with pytest.raises(ToolError) as raised:
        reveal_run([ELEMENT_FILE, ELEMENT, *VIEW, '--offset', '1'])
    text = str(raised.value)
    assert unsupported_controls_message(ELEMENT_VIEW_SPECS, ['--offset']) in text and 'usage:' not in text
