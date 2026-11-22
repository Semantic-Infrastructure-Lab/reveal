"""The main ``--help`` digest of a collapsed flag group names the flags it teaches, not old ones (BACK-2627, S6).

The Code analysis group's flags are generated from the element view declarations, which also generate every old flag
(``--boundary``, ``--exits``, ...) right after the control it now spells. The digest printed for the collapsed group lists
its first four flags, so it taught two old flags beside ``--view``. A generated legacy flag still parses and is still listed
by ``--help-all``; it is only left out of the digest. Groups with no generated legacy flag keep their digest.
"""

import argparse

from reveal.cli.parser import create_argument_parser
from reveal.utils.query_binding import _LegacyFlagAction


def _groups(full_help):
    parser = create_argument_parser('0', full_help=full_help)
    return {group.title.split('  ')[0]: group for group in parser._action_groups if group.title}


def _digest(title):
    return _groups(False)[title].description.splitlines()[0].strip()


def test_code_analysis_digest_names_the_canonical_flags():
    digest = _digest('Code analysis')
    shown = digest.split(', +')[0].split(', ')
    assert shown == ['--outline', '--view', '--kind', '--in-loops'], digest


def test_no_digest_names_a_generated_legacy_flag():
    legacy = {action.option_strings[0] for group in _groups(True).values() for action in group._group_actions
              if isinstance(action, _LegacyFlagAction)}
    assert {'--boundary', '--exits', '--flow', '--effects'} <= legacy  # the scan is not empty
    for title, group in _groups(False).items():
        if 'help-all to expand' not in (group.description or ''):
            continue
        named = set(group.description.splitlines()[0].strip().split(', +')[0].split(', '))
        assert not named & legacy, (title, named & legacy)


def test_other_digests_are_unchanged():
    # Negative control: the groups without generated legacy flags keep their first four flags.
    assert _digest('Quality checks').startswith('--check, --config, --select, --ignore, +')
    assert _digest('Markdown').startswith('--links, --link-type, --broken-only, --domain, +')
    assert _digest('Type-aware output') == '--typed, --filter, --decorator-stats'


def test_legacy_flags_still_parse_and_are_counted_in_the_digest_remainder():
    parser = create_argument_parser('0', full_help=False)
    parser.parse_args(['app.py', 'run', '--boundary'])  # an old flag still parses (argparse exits 2 if not)
    full = _groups(True)['Code analysis']
    listed = [a for a in full._group_actions if a.option_strings and a.help is not argparse.SUPPRESS]
    shown, _, rest = _digest('Code analysis').partition(', +')
    canonical = [a for a in listed if not isinstance(a, _LegacyFlagAction)]
    assert int(rest.split(' ')[0]) == len(canonical) - len(shown.split(', '))
