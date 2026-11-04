"""BACK-2486: a noun's --help advertises only the --fail-on values that noun accepts.

The flag came from the shared global-options parent, so every declared noun listed
``{none,findings}`` while the same page's exit-code epilog (from FINDINGS_POLICIES)
correctly omitted exit 1, and ``--fail-on findings`` then exited 2. Rejection itself stays
in the one runtime validator so the subcommand and URI spellings keep one message
(test_declared_parity_back2053).
"""
import re

import pytest

from conftest import _run_reveal_direct
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
from reveal.cli.invocation import COMMANDS

NOUNS = sorted(name for name in COMMANDS if declared_adapter_class(name) is not None)


def _advertised(help_text):
    match = re.search(r'--fail-on \{([a-z,]+)\}', help_text)
    assert match, help_text
    return tuple(match.group(1).split(','))


def test_nouns_cover_both_policy_shapes():
    # Positive control: the parametrized set really contains gated and ungated nouns.
    shapes = {'findings' in declared_adapter_class(n).FINDINGS_POLICIES for n in NOUNS}
    assert shapes == {True, False}, NOUNS


@pytest.mark.parametrize('noun', NOUNS)
def test_help_lists_exactly_the_nouns_policies(noun):
    policies = tuple(declared_adapter_class(noun).FINDINGS_POLICIES)
    help_text = create_declared_parser(noun).format_help()
    assert _advertised(help_text) == policies
    usage = help_text.split('\n\n', 1)[0]
    assert _advertised(usage) == policies
    if 'findings' not in policies:
        assert 'no findings gate' in ' '.join(help_text.split())


@pytest.mark.parametrize('noun', NOUNS)
def test_cli_help_advertises_only_accepted_values(noun):
    result = _run_reveal_direct(noun, '--help')
    assert result.returncode == 0
    action = create_declared_parser(noun)._option_string_actions['--fail-on']
    advertised = _advertised(result.stdout)
    # Advertised means accepted at parse time and by the runtime validator.
    assert set(advertised) <= set(action.choices)
    assert set(advertised) == set(declared_adapter_class(noun).FINDINGS_POLICIES)
