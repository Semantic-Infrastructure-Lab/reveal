"""BACK-1229: `--all` ("show all results, no limit") reached only the adapters
that read it themselves. `hotspots://` accepted it and still showed its default
top 10 per ranking. Adapters now declare the query fragment that lifts their own
cap (`ResourceAdapter.CLI_QUERY_FLAGS['all']`) and the CLI injects it for `--all`.
"""

from argparse import Namespace
import re

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
    ('ast', 'limit=1000000'), ('patches', 'limit=1000000'),
    ('testability', 'top=1000000'), ('stats', 'limit=1000000'), ('metrics', 'limit=1000000'), ('git', 'limit=1000000'),
    ('overview', 'all=true'),  # Constructor-bound map expansion; does not request assessments.
])
def test_back1379_adapters_declare_all(scheme, fragment):
    from reveal import adapters  # noqa: F401
    assert adapters_base.get_adapter_class(scheme).CLI_QUERY_FLAGS['all'] == fragment
    assert inject_query_flags('src', scheme, _args(all=True)) == f'src?{fragment}'


def test_calls_all_reaches_only_the_answers_that_read_its_cap():
    """--all lifts the selected answer's cap only (Scott 2026-11-18, BACK-2656): calls' ranking and uncalled read
    limit; a callers request has no cap, so --all is satisfied there and nothing is injected."""
    from reveal import adapters  # noqa: F401
    assert adapters_base.get_adapter_class('calls').CLI_QUERY_FLAGS['all'] == 'limit=1000000'
    assert inject_query_flags('src?sort=-callers', 'calls', _args(all=True)) == 'src?sort=-callers&limit=1000000'
    assert inject_query_flags('src?uncalled', 'calls', _args(all=True)) == 'src?uncalled&limit=1000000'
    assert inject_query_flags('src?callers=main', 'calls', _args(all=True)) == 'src?callers=main'


def test_all_injects_fragment():
    assert inject_query_flags('src', 'hotspots', _args(all=True)) == 'src?top=1000000'
    assert inject_query_flags('src?functions_only=true', 'hotspots', _args(all=True)) \
        == 'src?functions_only=true&top=1000000'


def test_an_explicit_uri_value_and_all_conflict():
    """BACK-2654 rule 1: --all sets top, so beside a different ?top= it is invalid (the URI used to win)."""
    from reveal.errors import RequestValidationError
    for uri in ('src?top=3', 'src?a=1&top=3'):
        with pytest.raises(RequestValidationError, match='--all conflicts with top=3'):
            inject_query_flags(uri, 'hotspots', _args(all=True))
    assert inject_query_flags('src?top=1000000', 'hotspots', _args(all=True)) == 'src?top=1000000'


def test_key_match_is_exact_not_substring():
    # 'stop=1' contains 'top=1' but is a different parameter.
    assert inject_query_flags('src?stop=1', 'hotspots', _args(all=True)) == 'src?stop=1&top=1000000'


def test_without_all_flag_nothing_changes():
    assert inject_query_flags('src', 'hotspots', _args()) == 'src'


@pytest.mark.parametrize('scheme', ['surface', 'claude', 'nosuchscheme'])
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
        # Count function rows, excluding the now-visible McCabe caveat.
        return len(re.findall(r'\bf\d+\s+complexity:', out.getvalue()))

    assert functions_listed() == 10
    assert functions_listed(all=True) == 14


def _pairs(resource):
    return sorted(resource.partition('?')[2].split('&'))


def test_all_lifts_the_cap_of_the_answer_the_request_selects():
    """BACK-2654 Step 5: --all lifts the cap the selected answer reads. Metrics' legacy hotspots ranking declares
    its own cap, top, so that legacy answer is unchanged until the cut; every other Metrics answer reads limit, so
    --all there is the canonical limit (it used to inject top, which those answers never read)."""
    from reveal.cli.defaults import _default_args
    for scheme in ('metrics', 'stats'):
        assert _pairs(inject_query_flags('src', scheme, _args(all=True))) == ['limit=1000000']
        assert _pairs(inject_query_flags('src?view=hotspots', scheme, _args(all=True))) == \
            ['limit=1000000', 'view=hotspots']
        assert _pairs(inject_query_flags('src?hotspots=false', scheme, _args(all=True))) == \
            ['hotspots=false', 'limit=1000000']
        for legacy in ('hotspots=true', 'hotspots', 'hotspots=1'):
            assert _pairs(inject_query_flags(f'src?{legacy}', scheme, _args(all=True))) == \
                sorted([legacy, 'top=1000000'])
        # the global --hotspots selects the same legacy answer, whatever order the flags were typed in
        assert _pairs(inject_query_flags('src', scheme, _default_args(all=True, hotspots=True))) == \
            ['hotspots=true', 'top=1000000']
    # Negative controls: nouns whose answers declare no cap of their own keep their declaration.
    assert inject_query_flags('src?hotspots=true', 'calls', _args(all=True)) == 'src?hotspots=true&limit=1000000'
    assert inject_query_flags('src', 'hotspots', _args(all=True)) == 'src?top=1000000'


def test_end_to_end_metrics_all_keeps_the_legacy_ranking_and_notes_nothing_elsewhere(tmp_path):
    import json
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import handle_uri

    body = '\n'.join(f'    if x == {i}:\n        return {i}' for i in range(12))
    for n in range(14):
        (tmp_path / f'm{n}.py').write_text(f'def f{n}(x):\n{body}\n    return -1\n', encoding='utf-8')

    def answer(query, **flags):
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(StringIO()):
            handle_uri(f'metrics://{tmp_path.as_posix()}{query}', None, _default_args(format='json', **flags))
        return json.loads(out.getvalue())

    def codes(result):
        return [warning.get('code') for warning in result.get('meta', {}).get('warnings', [])]

    assert len(answer('?hotspots=true')['hotspots']) == 10
    assert len(answer('?hotspots=true', all=True)['hotspots']) == 14
    assert len(answer('', hotspots=True, all=True)['hotspots']) == 14
    assert len(answer('?view=hotspots', all=True)['hotspots']) == 14
    plain = answer('', all=True)
    assert len(plain['files']) == 14 and 'unused_flag' not in codes(plain), codes(plain)
