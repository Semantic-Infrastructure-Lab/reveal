"""A declared subcommand notes a retired alias however the command line spells it (BACK-2620).

Two spellings reach a declared parameter without naming the alias as its URI key: a hyphenated
subcommand flag for an underscore alias (``--max-files`` for ``max_files``) and a legacy global flag
bound through ``ParamSpec.cli_flags`` that is itself an alias (``--verbose`` for ``detail=full``).
Both must consult the same ``param:<name>.<alias>`` row the URI spelling does; canonical flags and
cli_flags that are not aliases (``--all``) note nothing.
"""
import argparse

import pytest

from reveal.cli import invocation
from reveal.cli.invocation import Invocation, Retirement, invocation_scope, noted_retirements
from reveal.cli.routing.declared import _bind_legacy_cli_values, _note_retired_flags
from reveal.utils.query_binding import prepare_declared_params
from reveal.utils.query_parser import CliBinding, ParamSpec

SCAN = ParamSpec('scan-limit', 'integer', 'Input budget', None, int, aliases=('scan_limit', 'max_files'),
                 cli=CliBinding(('--scan-limit', '--max-files'), dest='scan_limit'))
def _detail_alias(name, value):
    return ('full' if value is True else 'normal') if name == 'verbose' else value


DETAIL = ParamSpec('detail', 'string', 'How much', None, str, aliases=('verbose',), alias_normalize=_detail_alias,
                   cli_flags=(('verbose', 'full'),), cli=CliBinding(('--detail',)))
ROWS = ParamSpec('rows', 'integer', 'Row cap', None, int, cli_flags=(('all', '1000000'),),
                 cli=CliBinding(('--rows',)))


class Demo:
    PARAM_SPECS = (SCAN, DETAIL, ROWS)


@pytest.fixture(autouse=True)
def rows(monkeypatch):
    for key in ('max_files', 'scan_limit', 'verbose', 'all', 'scan-limit', 'detail', 'rows'):
        monkeypatch.setitem(invocation.RETIREMENTS, f'param:demo.{key}', Retirement(f'demo {key}', 'its replacement'))


def flags_noted(*argv):
    with invocation_scope(Invocation.parse(['reveal', 'demo', '.', *argv]), retirements_to_stderr=False):
        _note_retired_flags('demo', Demo)
        return sorted(noted_retirements())


def bound_noted(source=None, **flags):
    args = argparse.Namespace(**flags)
    with invocation_scope(Invocation.parse(['reveal', 'demo', '.']), retirements_to_stderr=False):
        source = dict(source or {})
        _bind_legacy_cli_values('demo', Demo, args, source)
        return sorted(noted_retirements()), source


def prepared(source):
    return dict(prepare_declared_params(Demo.PARAM_SPECS, source, 'typed').peek_items())


def test_hyphenated_flag_for_an_underscore_alias_notes_that_alias():
    assert flags_noted('--max-files', '3') == ['param:demo.max_files']
    assert flags_noted('--max-files=3') == ['param:demo.max_files']


def test_canonical_flag_notes_the_canonical_key_not_an_alias():
    # --scan-limit is the canonical spelling; its underscore alias scan_limit must not be noted.
    assert flags_noted('--scan-limit', '3') == ['param:demo.scan-limit']
    assert flags_noted('--detail', 'full') == ['param:demo.detail']


def test_legacy_global_flag_bound_to_an_alias_notes_it():
    noted, source = bound_noted(verbose=True)
    assert noted == ['param:demo.verbose'] and prepared(source) == {'detail': 'full'}


def test_legacy_global_alias_flag_conflicting_with_the_canonical_flag_rejects():
    # --verbose --detail normal names two values for one parameter: the binder's alias check rejects
    # it (exit 2 on the subcommand), instead of the global flag being reported unused.
    noted, source = bound_noted({'detail': 'normal'}, verbose=True)
    assert noted == ['param:demo.verbose']
    with pytest.raises(ValueError, match='detail: conflicting spellings'):
        prepared(source)
    _noted, equal = bound_noted({'detail': 'full'}, verbose=True)
    assert prepared(equal) == {'detail': 'full'}


def test_legacy_global_flag_that_is_not_an_alias_notes_nothing():
    noted, source = bound_noted(all=True)
    assert noted == [] and source == {'rows': '1000000'}
    noted, source = bound_noted(verbose=False)
    assert noted == [] and source == {}
