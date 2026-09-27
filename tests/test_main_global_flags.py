"""Global flags must behave the same on every path (BACK-1378, BACK-1375).

The CLI has two forms (subcommands and the path/URI form), parsed and dispatched by one
path (main._dispatch_and_run, BACK-1058), and the MCP server is a third. A global flag handled on one and not the others is the silently-dropped-flag bug
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
    reveal_main.main(['reveal', *argv])


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


@pytest.mark.parametrize('flags', [('-c',), ('-qc',), ('-q', '-c')])
def test_copy_honors_every_spelling_argparse_accepts(monkeypatch, tree, clipboard, flags):
    # BACK-1058: a raw `'-c' in argv` scan missed -qc, which argparse accepts: no copy, no note.
    _run(monkeypatch, str(tree / 'a.py'), *flags)
    assert clipboard and clipboard[0].strip()


# ------------------------------------------------ one Invocation for both forms (BACK-1058)

@pytest.mark.parametrize('before', [
    ('--format', 'json'), ('--format=json',), ('--provenance', '--format', 'json'), ('-q', '--format', 'json'),
])
def test_global_options_may_precede_the_subcommand(capsys, tree, before):
    # `reveal --format json overview DIR` used to be the path form: "Error: overview not found".
    reveal_main.main(['reveal', *before, 'overview', str(tree)])
    out = capsys.readouterr().out
    assert '"type": "overview"' in out


def test_a_non_global_option_before_the_name_keeps_the_path_form(monkeypatch, tmp_path, capsys):
    # Only options every subcommand accepts may precede its name; after any other the word
    # is a path, as before (a directory named `overview` here).
    (tmp_path / 'overview').mkdir()
    (tmp_path / 'overview' / 'x.py').write_text('def g():\n    pass\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    reveal_main.main(['reveal', '--depth', '1', 'overview'])
    assert 'x.py' in capsys.readouterr().out


# ------------------------------------------------------------- REVEAL_FORMAT (BACK-1362)
#
# Documented in CONFIGURATION_GUIDE.md and merged into RevealConfig's dict by
# config._load_from_env(), but nothing ever read config['output']['format'] back out --
# a fully dead env var (test_config.py::test_reveal_format only asserted the dict got
# populated, never that any output changed). Fixed by using it as --format's parser
# default (reveal.cli.parser._format_default), the same seam every subcommand and the
# main parser both already share for --format itself.

def test_reveal_format_env_var_sets_default_on_bare_path(monkeypatch, tree, capsys):
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    _run(monkeypatch, str(tree / 'a.py'))
    assert capsys.readouterr().out.lstrip().startswith('{')


def test_reveal_format_env_var_sets_default_on_a_uri(monkeypatch, tree, capsys):
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    _run(monkeypatch, f'stats://{tree}')
    assert capsys.readouterr().out.lstrip().startswith('{')


def test_reveal_format_env_var_sets_default_on_a_subcommand(monkeypatch, tree, capsys):
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    _run(monkeypatch, 'overview', str(tree))
    assert capsys.readouterr().out.lstrip().startswith('{')


def test_explicit_format_flag_overrides_reveal_format_env_var(monkeypatch, tree, capsys):
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    _run(monkeypatch, str(tree / 'a.py'), '--format', 'text')
    assert not capsys.readouterr().out.lstrip().startswith('{')


def test_invalid_reveal_format_env_var_warns_and_falls_back_to_text(monkeypatch, tree, capsys):
    monkeypatch.setenv('REVEAL_FORMAT', 'bogus')
    _run(monkeypatch, str(tree / 'a.py'))
    captured = capsys.readouterr()
    assert 'REVEAL_FORMAT' in captured.err
    assert not captured.out.lstrip().startswith('{')
