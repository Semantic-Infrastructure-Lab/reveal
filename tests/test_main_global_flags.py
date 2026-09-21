"""Global flags must behave the same on every path (BACK-1378, BACK-1375).

main.py has two entry paths (subcommand dispatch and _main_impl) and the MCP server has a
third. A global flag handled on one and not the others is the silently-dropped-flag bug
class. These tests pin the shared hook and the --copy behavior on each path.
"""
import sys

import pytest

from reveal import main as reveal_main
from reveal.utils import json_utils


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    return tmp_path


@pytest.fixture(autouse=True)
def _restore_provenance_flag():
    yield
    json_utils.set_provenance_enabled(False)


@pytest.fixture
def clipboard(monkeypatch):
    copied = []
    monkeypatch.setattr(reveal_main, 'copy_to_clipboard', lambda text: copied.append(text) or True)
    return copied


def _provenance_on():
    return 'execution' in json_utils.attach_provenance({})


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['reveal', *argv])
    reveal_main._dispatch_and_run()


# ------------------------------------------------------------------ apply_global_flags

@pytest.mark.parametrize('value,expected', [(True, True), (False, False)])
def test_apply_global_flags_sets_provenance(value, expected):
    from argparse import Namespace

    from reveal.cli.global_flags import apply_global_flags

    json_utils.set_provenance_enabled(not expected)
    apply_global_flags(Namespace(provenance=value))
    assert _provenance_on() is expected


def test_apply_global_flags_tolerates_namespaces_without_the_flag():
    from argparse import Namespace

    from reveal.cli.global_flags import apply_global_flags

    json_utils.set_provenance_enabled(True)
    apply_global_flags(Namespace())
    assert _provenance_on() is False


# ------------------------------------------------- every path calls the shared hook

def test_bare_path_calls_the_hook(monkeypatch, tree):
    seen = []
    monkeypatch.setattr(reveal_main, 'apply_global_flags', seen.append)
    _run(monkeypatch, str(tree / 'a.py'), '--provenance')
    assert len(seen) == 1 and seen[0].provenance is True


def test_subcommand_path_calls_the_hook(monkeypatch, tree):
    seen = []
    monkeypatch.setattr(reveal_main, 'apply_global_flags', seen.append)
    _run(monkeypatch, 'overview', str(tree), '--provenance')
    assert len(seen) == 1 and seen[0].provenance is True


def test_mcp_query_calls_the_hook(monkeypatch, tree):
    from reveal import mcp_server

    seen = []
    monkeypatch.setattr(mcp_server, 'apply_global_flags', lambda a: seen.append(a.provenance))
    mcp_server.reveal_query(f'stats://{tree}', provenance=True)
    assert seen == [True]


# ------------------------------------------------------------------------ --copy

def test_copy_works_on_the_bare_path(monkeypatch, tree, clipboard):
    _run(monkeypatch, str(tree / 'a.py'), '--copy')
    assert clipboard and 'f' in clipboard[0]


def test_copy_works_on_a_uri(monkeypatch, tree, clipboard):
    _run(monkeypatch, f'stats://{tree}', '--copy')
    assert clipboard and clipboard[0].strip()


def test_copy_works_on_a_subcommand(monkeypatch, tree, clipboard):
    _run(monkeypatch, 'overview', str(tree), '--copy')
    assert clipboard and clipboard[0].strip(), 'subcommand ran but nothing was copied'


def test_copy_restores_stdout_after_a_subcommand(monkeypatch, tree, clipboard):
    before = sys.stdout
    _run(monkeypatch, 'overview', str(tree), '--copy')
    assert sys.stdout is before


def test_no_copy_flag_means_no_clipboard_write(monkeypatch, tree, clipboard):
    _run(monkeypatch, 'overview', str(tree))
    assert clipboard == []
