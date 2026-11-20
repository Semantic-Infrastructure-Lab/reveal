"""Flags after a URI are the subcommand's flags (COMMAND_MODEL "Flags after a URI", BACK-2673 Step 3b-2).

A declared noun's URI is parsed by that noun's own parser, so ``reveal NOUN://T --flag v`` is the request
``reveal NOUN T --flag v`` is. Conformance column '23' (tests/test_vocabulary_conformance_back2654.py) compares
the two spellings flag by flag; this file pins what the column cannot see: a main-only mode refused on a declared
noun, the paths the change must leave alone (an element after the URI, a ``--stdin`` batch, the legacy spellings
waiting for their RETIREMENTS rows, the flagless MCP answer).
"""
import io
import json

import pytest

from conftest import without_request_notes
from test_vocabulary_conformance_back2654 import BASE, TARGETS, _answer, _run, _uri, workspace  # noqa: F401

from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import declared_adapter_class

SUBCOMMAND_NOUNS = sorted(noun for noun, spec in COMMANDS.items() if spec.declared_adapter)


@pytest.fixture
def config_writes(monkeypatch):
    """Every call of the main-only mode that writes the user's config, recorded instead of written."""
    calls = []
    monkeypatch.setattr('reveal.main.disable_breadcrumbs_permanently', lambda: calls.append(1) or True)
    return calls


@pytest.mark.parametrize('extra', [(), ('--format', 'json')])
def test_disable_breadcrumbs_is_not_an_option_of_a_declared_subcommand(workspace, config_writes, extra):
    """``--disable-breadcrumbs`` is a main-command mode that writes the user's config: a declared noun's subcommand does
    not take it, so it exits 2 naming it, in JSON with the invalid-request document, and nothing is written (it used
    to be accepted and noted unused)."""
    run = _run('ast', 'proj', '--disable-breadcrumbs', *extra)
    assert run.rc == 2, run.brief()
    message = json.loads(run.out)['error'] if extra else run.err
    assert "unsupported control '--disable-breadcrumbs'" in message, run.brief()
    assert config_writes == []


def test_disable_breadcrumbs_after_a_uri_keeps_the_pathless_refusal(workspace, config_writes):
    """Control: after a URI the main command's modes that take no path keep the main parser's refusal, which names the
    mode and the path it would ignore (BACK-1751): exit 2, as on the subcommand, and nothing is written."""
    run = _run('ast://proj', '--disable-breadcrumbs')
    assert run.rc == 2 and '--disable-breadcrumbs takes no path' in run.err, run.brief()
    assert config_writes == []


def test_the_main_command_keeps_disable_breadcrumbs(workspace, config_writes):
    """Control: the main command's mode still runs."""
    run = _run('--disable-breadcrumbs')
    assert run.rc == 0 and config_writes == [1], run.brief()


@pytest.mark.parametrize('extra', [(), ('--format', 'json')])
def test_an_element_after_a_declared_uri_is_refused_naming_the_uri_form(workspace, extra):
    """Control: an element after a declared noun's URI keeps its one refusal (BACK-2526, BACK-2687)."""
    from reveal.adapters.base import unread_element_message
    run = _run('ast://proj', 'serve', *extra)
    expected = unread_element_message(declared_adapter_class('ast'), 'ast', 'serve')
    assert run.rc == 2, run.brief()
    assert expected in (json.loads(run.out)['error'] if extra else run.err), run.brief()


def test_a_stdin_batch_line_still_binds_the_command_lines_flags(workspace, monkeypatch):
    """Control: a ``--stdin`` batch parses the command line once with the main parser (its per-line parse is its own
    task); ``--limit`` still reaches each declared line."""
    monkeypatch.setattr('sys.stdin', io.StringIO('ast://proj\n'))
    run = _run('--stdin', '--limit', '1', '--format', 'json')
    assert run.rc == 0, run.brief()
    assert len(json.loads(run.out)['results']) == 1


def test_no_main_parser_flag_is_held_on_the_old_route(workspace):
    """Claude ``--tail`` was the last main-parser flag kept on the URI-only route (held for Scott's ruling, step 3b-3);
    since BACK-2709 it is a flag-only modifier like ``--head``, so the URI and the subcommand give one answer, exit 0,
    and the declared route keeps no table of held flags."""
    from reveal.cli.routing import declared
    assert not hasattr(declared, '_PENDING_MAIN_FLAGS')
    uri = _run('claude://session/my-session?view=messages', '--tail', '1', '--format', 'json')
    sub = _run('claude', 'session/my-session', '--view', 'messages', '--tail', '1', '--format', 'json')
    assert uri.rc == sub.rc == 0, (uri.brief(), sub.brief())
    assert json.loads(uri.out)['messages'] == json.loads(sub.out)['messages'] and len(json.loads(sub.out)['messages']) == 1


def _without_execution(document):
    return {key: value for key, value in document.items() if key != 'execution'}


@pytest.mark.parametrize('noun', SUBCOMMAND_NOUNS)
def test_the_flagless_mcp_answer_is_the_cli_json(workspace, noun):
    """Control: the change is on the CLI parse only; a real ``reveal_query`` call answers each noun's default URI with
    the CLI's JSON document (COMMAND_MODEL "Transports"), the provenance block aside (it names the command)."""
    from reveal.mcp_server import reveal_query
    uri = _uri(noun)
    cli = _run(uri, '--format', 'json', '--provenance')
    assert cli.rc in (0, 1, 3), cli.brief()
    mcp = json.loads(reveal_query(uri, provenance=True))
    # each transport says its request note in its own form (BACK-2716)
    assert _without_execution(without_request_notes(mcp)) == _without_execution(without_request_notes(json.loads(cli.out)))
