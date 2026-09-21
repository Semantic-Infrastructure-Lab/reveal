"""BACK-1361: `--verbose` was silently dropped on the URI path for `imports://`.

`reveal 'imports://src?circular' --verbose` printed the same truncated output as
without the flag (and the renderer itself advised "Run with --verbose"), while the
spelling `&verbose` worked but made the validator warn that it was "ignored".
Adapters now declare the fragment (`CLI_QUERY_FLAGS['verbose']`), the CLI injects it
for `--verbose`, and the adapter's schema lists the param it has always honored.
"""

from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from reveal.adapters import base as adapters_base
from reveal.cli.routing.flag_specs import inject_query_flags

pytestmark = pytest.mark.component


def _args(**kw):
    return Namespace(**{'verbose': False, **kw})


def test_default_declares_no_verbose_query():
    assert 'verbose' not in adapters_base.ResourceAdapter.CLI_QUERY_FLAGS


def test_imports_declares_verbose():
    from reveal import adapters  # noqa: F401
    assert adapters_base.get_adapter_class('imports').CLI_QUERY_FLAGS['verbose'] == 'verbose'


def test_verbose_injects_fragment():
    assert inject_query_flags('src?circular', 'imports', _args(verbose=True)) == 'src?circular&verbose'
    assert inject_query_flags('src', 'imports', _args(verbose=True)) == 'src?verbose'


def test_explicit_uri_value_wins():
    assert inject_query_flags('src?circular&verbose', 'imports', _args(verbose=True)) \
        == 'src?circular&verbose'


def test_key_match_is_exact_not_substring():
    assert inject_query_flags('src?verbosex=1', 'imports', _args(verbose=True)) \
        == 'src?verbosex=1&verbose'


def test_without_verbose_flag_nothing_changes():
    assert inject_query_flags('src?circular', 'imports', _args()) == 'src?circular'


@pytest.mark.parametrize('scheme', ['stats', 'hotspots', 'overview', 'claude', 'nosuchscheme'])
def test_adapters_without_declaration_untouched(scheme):
    assert inject_query_flags('src', scheme, _args(verbose=True)) == 'src'


def test_ampersand_verbose_does_not_warn_unknown(tmp_path):
    from reveal.adapters.imports import ImportsAdapter

    err = StringIO()
    with redirect_stderr(err):
        ImportsAdapter(str(tmp_path), 'circular&verbose')
    assert 'Unknown query param' not in err.getvalue()


def _cycle_fixture(root, size=5):
    (root / 'pyproject.toml').write_text('[project]\nname = "cyc"\nversion = "0"\n', encoding='utf-8')
    pkg = root / 'pkg'
    pkg.mkdir()
    (pkg / '__init__.py').write_text('', encoding='utf-8')
    for i in range(1, size + 1):
        (pkg / f'm{i}.py').write_text(f'from . import m{i % size + 1}\n', encoding='utf-8')
    return pkg


def _render(uri, **flags):
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import handle_uri

    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        handle_uri(uri, None, _default_args(**flags))
    return out.getvalue()


def test_end_to_end_verbose_flag_expands_the_cycle_report(tmp_path):
    pkg = _cycle_fixture(tmp_path)
    uri = f'imports://{pkg}?circular'

    terse = _render(uri)
    assert '[+2 more files]' in terse and 'cycle:' not in terse

    for full in (_render(uri, verbose=True), _render(uri + '&verbose')):
        assert 'm5.py' in full and 'cycle:' in full and 'more files' not in full
