"""BACK-1361: `--verbose` was silently dropped on the URI path for `imports://`.

`reveal 'imports://src?circular' --verbose` printed the same truncated output as
without the flag (and the renderer itself advised "Run with --verbose"), while the
spelling `&verbose` worked but made the validator warn that it was "ignored".
Adapters now declare the fragment (`CLI_QUERY_FLAGS['verbose']`), the CLI injects it
for `--verbose`, and the adapter's schema lists the param it has always honored.

BACK-2654 rule 4: on a declared noun the fragment comes from the noun's declarations, never CLI_QUERY_FLAGS: the
noun's legacy word ``verbose`` where it declares one (imports: detail=full), else ``detail=full``.
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
    # imports declares the legacy word verbose on detail (detail=full); no CLI_QUERY_FLAGS binding.
    from reveal import adapters  # noqa: F401
    imports = adapters_base.get_adapter_class('imports')
    assert 'verbose' not in imports.CLI_QUERY_FLAGS
    detail = next(spec for spec in imports.PARAM_SPECS if spec.name == 'detail')
    assert detail.canonical_value('verbose', 'true') == 'full'


def test_verbose_injects_fragment():
    assert inject_query_flags('src?circular', 'imports', _args(verbose=True)) == 'src?circular&verbose=true'
    assert inject_query_flags('src', 'imports', _args(verbose=True)) == 'src?verbose=true'


def test_an_equal_uri_detail_binds_once():
    from reveal.utils.query_binding import prepare_declared_params
    resource = inject_query_flags('src?circular&detail=full', 'imports', _args(verbose=True))
    assert resource == 'src?circular&detail=full&verbose=true'
    imports = adapters_base.get_adapter_class('imports')
    assert prepare_declared_params(imports.PARAM_SPECS, resource.partition('?')[2], 'uri').get('detail') == 'full'


def test_key_match_is_exact_not_substring():
    assert inject_query_flags('src?verbosex=1', 'imports', _args(verbose=True)) \
        == 'src?verbosex=1&verbose=true'


def test_without_verbose_flag_nothing_changes():
    assert inject_query_flags('src?circular', 'imports', _args()) == 'src?circular'


@pytest.mark.parametrize('scheme', ['diff', 'nosuchscheme'])  # env, help, reveal are declared (no detail: refused)
def test_adapters_without_declaration_untouched(scheme):
    assert inject_query_flags('src', scheme, _args(verbose=True)) == 'src'


@pytest.mark.parametrize('scheme,resource', [('hotspots', 'src?verbose=true'), ('claude', 'src?detail=full'),
                                             ('stats', 'src?detail=full')])
def test_a_declared_noun_binds_verbose_from_its_declarations(scheme, resource):
    assert inject_query_flags('src', scheme, _args(verbose=True)) == resource


def test_a_declared_noun_without_detail_rejects_verbose():
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match="--verbose is --detail full: unsupported control 'detail'"):
        inject_query_flags('src', 'surface', _args(verbose=True))


def test_overview_verbose_uses_its_declared_map_expansion_control():
    assert inject_query_flags('src', 'overview', _args(verbose=True)) == 'src?verbose=true'
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match='--verbose conflicts with verbose=false'):  # BACK-2654 rule 1
        inject_query_flags('src?verbose=false', 'overview', _args(verbose=True))
    assert inject_query_flags('src?verbose=true', 'overview', _args(verbose=True)) == 'src?verbose=true'


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
