"""CLI flags -> URI query fragments, driven by one table plus adapter declarations (BACK-1376).

`FLAG_SPECS` (cli/routing/flag_specs.py) says how a global flag becomes a query fragment;
an adapter opts in with `CLI_QUERY_FLAGS = {flag: fragment}`. These tests are derived from
both, so a new spec or declaration is checked without a new hand-written test.
"""
import io
import logging
from argparse import Namespace
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from reveal.adapters import base as adapters_base
from reveal.cli.defaults import _default_args
from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.flag_specs import FLAG_SPECS, inject_query_flags

REPO = Path(__file__).resolve().parent.parent


def _declarations():
    from reveal import adapters  # noqa: F401  (registers every scheme)
    for scheme in sorted(adapters_base.list_supported_schemes()):
        cls = adapters_base.get_adapter_class(scheme)
        for dest, fragment in dict(getattr(cls, 'CLI_QUERY_FLAGS', {})).items():
            yield scheme, dest, fragment


def _inject(uri_resource, scheme, **flags):
    err = io.StringIO()
    with redirect_stderr(err):
        out = inject_query_flags(uri_resource, scheme, _default_args(**flags))
    return out, err.getvalue()


# ------------------------------------------------------------- derived consistency

def test_every_spec_dest_is_a_real_parser_dest():
    dests = set(vars(create_argument_parser('0', full_help=False).parse_args([])))
    assert {s.dest for s in FLAG_SPECS} <= dests


def test_every_declaration_has_a_spec():
    known = {s.dest for s in FLAG_SPECS}
    orphans = [(sch, d) for sch, d, _ in _declarations() if d not in known]
    assert not orphans, f'adapter declares a flag no FlagSpec carries: {orphans}'


def test_declarations_exist():
    assert {(s, d) for s, d, _ in _declarations()} >= {
        ('hotspots', 'all'), ('imports', 'verbose'), ('git', 'since'), ('git', 'until'),
        ('overview', 'respect_gitignore'), ('stats', 'respect_gitignore')}


@pytest.mark.parametrize('scheme,dest,fragment', list(_declarations()))
def test_declared_fragment_is_accepted_by_its_adapter_without_warning(scheme, dest, fragment, caplog):
    """A declaration the adapter's own validator flags would print a false 'unknown param'
    every time the flag is used (the BACK-1361 failure)."""
    cls = adapters_base.get_adapter_class(scheme)
    query = fragment.replace('{value}', '2026-01-01')
    err = io.StringIO()
    with redirect_stderr(err), caplog.at_level(logging.WARNING):
        cls(str(REPO), query)
    seen = err.getvalue() + caplog.text
    assert 'nknown query param' not in seen, f'{scheme}:// warns on its own {fragment!r}: {seen}'


# ----------------------------------------------------------------------- injection

def test_supported_flag_is_injected():
    assert _inject('.', 'git', since='2026-01-01')[0] == '.?since=2026-01-01'


def test_both_since_and_until_are_injected_in_order():
    out, _ = _inject('.', 'git', since='2026-01-01', until='2026-06-01')
    assert out == '.?since=2026-01-01&until=2026-06-01'


def test_uri_value_wins_over_the_flag():
    out, _ = _inject('.?since=2020-01-01', 'git', since='2099-01-01')
    assert out == '.?since=2020-01-01'


def test_key_match_is_exact_not_substring():
    out, _ = _inject('.?not_since=1', 'git', since='2026-01-01')
    assert out.endswith('&since=2026-01-01')


def test_raw_date_filter_counts_as_already_scoped():
    out, _ = _inject('.?date>2020-01-01', 'git', since='2099-01-01')
    assert 'since=' not in out


def test_unset_flag_changes_nothing_and_says_nothing():
    assert _inject('.', 'git') == ('.', '')


def test_default_respect_gitignore_is_not_injected():
    assert _inject('.', 'overview') == ('.', '')


def test_no_gitignore_injects_the_declared_fragment():
    assert _inject('.', 'overview', respect_gitignore=False)[0] == '.?respect_gitignore=false'


def test_unsupported_flag_gets_a_note_naming_the_supporting_schemes():
    out, err = _inject('.', 'ast', since='2026-01-01')
    assert out == '.'
    # Not a fixed list -- schemes gain since/until support over time (BACK-1379);
    # just confirm the note names ast:// and includes a real supporting scheme.
    assert '--since has no effect on ast://' in err and 'git://' in err


def test_note_lists_every_declaring_scheme():
    # BACK-1386: every walking adapter declares --no-gitignore; env:// walks nothing.
    _, err = _inject('.', 'env', respect_gitignore=False)
    assert '--no-gitignore has no effect on env://' in err
    assert 'overview://' in err and 'stats://' in err and 'ast://' in err


def test_all_and_verbose_stay_silent_on_adapters_without_a_declaration():
    """Many adapters honor --all/--verbose themselves (claude, nginx, overview), so a
    missing declaration is not evidence the flag is ignored: no note."""
    assert _inject('.', 'env', all=True, verbose=True) == ('.', '')


def test_all_and_verbose_inject_where_declared():
    assert _inject('.', 'hotspots', all=True)[0] == '.?top=1000000'
    assert _inject('.', 'imports', verbose=True)[0] == '.?verbose'


def test_namespace_missing_the_flags_is_tolerated():
    assert inject_query_flags('.', 'git', Namespace()) == '.'


# --- universal specs: --sort / --limit (BACK-1376) ---------------------------------

def test_sort_and_desc_inject_on_any_scheme():
    assert _inject('env://', 'env', sort='name', desc=True)[0] == 'env://?sort=-name'


def test_sort_already_negated_is_not_double_negated():
    assert _inject('ast://x', 'ast', sort='-lines', desc=True)[0] == 'ast://x?sort=-lines'


def test_limit_zero_is_a_real_request():
    assert _inject('ast://x', 'ast', limit=0)[0] == 'ast://x?limit=0'


def test_limit_left_at_parser_default_injects_nothing():
    args = _default_args()
    assert args.limit is None
    assert inject_query_flags('ast://x', 'ast', args) == 'ast://x'


def test_uri_limit_wins_and_key_match_is_exact():
    assert _inject('ast://x?limit=5', 'ast', limit=9)[0] == 'ast://x?limit=5'
    assert _inject('ast://x?dir_limit=5', 'ast', limit=9)[0] == 'ast://x?dir_limit=5&limit=9'


def test_check_still_caps_at_50_when_limit_is_not_typed(tmp_path, capsys):
    """--limit's parser default is None (so URI routing can tell 'typed'); `check` must still
    apply its own 50-file cap (BACK-539) and honor a typed value or 0."""
    from reveal.cli.file_checker import handle_recursive_check
    for i in range(55):
        (tmp_path / f'm{i}.py').write_text('import os\nimport sys\n', encoding='utf-8')

    def footer(**flags):
        with pytest.raises(SystemExit):  # issues found -> non-zero exit
            handle_recursive_check(tmp_path, _default_args(format='text', **flags))
        return capsys.readouterr().out

    assert '(--limit 50)' in footer()
    assert '(--limit 3)' in footer(limit=3)
    assert 'more files' not in footer(limit=0)
