"""BACK-2627 (S3b-1, C4a): ``declared.typed_source`` is the one reading of a declaration's flags off a parsed namespace.

Moved unchanged out of ``run_declared_command`` so the path read's element views bind through it too (no second
forwarding path). It keys a value by the control's dest, a flag-only modifier by its own name and an old flag with an
argument of its own by its legacy name; it names each key's typed flag; it reads without counting a use.
"""
import argparse

from reveal.cli.routing.declared import typed_source
from reveal.cli.routing.ledger import FlagLedger
from reveal.utils.query_binding import add_declared_arguments
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, whole_number

LIMIT = ParamSpec('limit', 'integer', 'cap', None, whole_number, cli=CliBinding(('--limit',)),
                  legacy=(LegacySpelling('top', flag='--top'),))
CHURN = ParamSpec('churn', 'boolean', 'switch', None, str, cli=CliBinding(('--churn',)),
                  legacy=(LegacySpelling('no_churn', flag='--no-churn', flag_value=True),))
HEAD = ParamSpec('head', 'integer', 'slice', None, whole_number, flag_only='applied',
                 cli=CliBinding(('--head',), dest='slice_head'))
CARRIED = ParamSpec('all', 'boolean', 'carried by a global flag', False, bool)
SPECS = (LIMIT, CHURN, HEAD, CARRIED)


def _parse(*argv):
    parser = argparse.ArgumentParser(add_help=False)
    add_declared_arguments(parser, SPECS, None)
    return parser.parse_args(list(argv))


def test_keys_and_spellings():
    source, spelled = typed_source(SPECS, _parse('--top', '3', '--no-churn', '--head', '2'))
    assert source == {'limit': '3', 'no_churn': True, 'head': '2'}  # the binder translates top and no_churn
    assert spelled == {'limit': '--limit', 'no_churn': '--no-churn', 'head': '--head'}


def test_omitted_flags_are_absent():
    assert typed_source(SPECS, _parse()) == ({}, {})


def test_a_control_with_no_flag_goes_to_the_carried_callback():
    seen = []
    source, _ = typed_source(SPECS, _parse('--limit', '1'),
                             carried=lambda spec, src, spelled: (seen.append(spec.name), src.update(all=True)))
    assert seen == ['all'] and source == {'limit': '1', 'all': True}


def test_reading_is_not_use():
    args = _parse('--limit', '1')
    ledger = FlagLedger(args)
    tracked = ledger.track(args)
    typed_source(SPECS, tracked)
    assert 'limit' not in ledger.used
