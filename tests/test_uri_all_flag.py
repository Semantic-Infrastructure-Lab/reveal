"""BACK-1229: `--all` ("show all results, no limit") reached only the adapters
that read it themselves. `hotspots://` accepted it and still showed its default
top 10 per ranking. Adapters now declare the query fragment that lifts their own
cap (`ResourceAdapter.CLI_QUERY_FLAGS['all']`) and the CLI injects it for `--all`.
"""

from argparse import Namespace

import pytest

from reveal.adapters import base as adapters_base
from reveal.cli.routing.flag_specs import inject_query_flags

pytestmark = pytest.mark.component


def _args(**kw):
    return Namespace(**{'all': False, **kw})


def test_default_declares_no_cap():
    assert 'all' not in adapters_base.ResourceAdapter.CLI_QUERY_FLAGS


def test_hotspots_declares_top():
    from reveal import adapters  # noqa: F401
    assert adapters_base.get_adapter_class('hotspots').CLI_QUERY_FLAGS['all'] == 'top=1000000'


@pytest.mark.parametrize('scheme,fragment', [
    ('ast', 'limit=1000000'), ('calls', 'top=1000000'), ('patches', 'limit=1000000'),
    ('testability', 'top=1000000'), ('stats', 'top=1000000'), ('git', 'limit=1000000'),
])
def test_back1379_adapters_declare_all(scheme, fragment):
    from reveal import adapters  # noqa: F401
    assert adapters_base.get_adapter_class(scheme).CLI_QUERY_FLAGS['all'] == fragment
    assert inject_query_flags('src', scheme, _args(all=True)) == f'src?{fragment}'


def test_all_injects_fragment():
    assert inject_query_flags('src', 'hotspots', _args(all=True)) == 'src?top=1000000'
    assert inject_query_flags('src?functions_only=true', 'hotspots', _args(all=True)) \
        == 'src?functions_only=true&top=1000000'


def test_explicit_uri_value_wins():
    assert inject_query_flags('src?top=3', 'hotspots', _args(all=True)) == 'src?top=3'
    assert inject_query_flags('src?a=1&top=3', 'hotspots', _args(all=True)) == 'src?a=1&top=3'


def test_key_match_is_exact_not_substring():
    # 'stop=1' contains 'top=1' but is a different parameter.
    assert inject_query_flags('src?stop=1', 'hotspots', _args(all=True)) == 'src?stop=1&top=1000000'


def test_without_all_flag_nothing_changes():
    assert inject_query_flags('src', 'hotspots', _args()) == 'src'


@pytest.mark.parametrize('scheme', ['surface', 'claude', 'overview', 'nosuchscheme'])
def test_adapters_without_declaration_untouched(scheme):
    assert inject_query_flags('src', scheme, _args(all=True)) == 'src'


def test_end_to_end_lifts_hotspots_cap(tmp_path):
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import handle_uri

    body = '\n'.join(f'    if x == {i}:\n        return {i}' for i in range(14))
    for n in range(14):
        (tmp_path / f'm{n}.py').write_text(f'def f{n}(x):\n{body}\n    return -1\n')

    def functions_listed(**flags):
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(StringIO()):
            handle_uri(f'hotspots://{tmp_path}?functions_only=true', None, _default_args(**flags))
        return sum(1 for line in out.getvalue().splitlines() if ' f' in line and 'complexity' in line)

    assert functions_listed() == 10
    assert functions_listed(all=True) == 14
