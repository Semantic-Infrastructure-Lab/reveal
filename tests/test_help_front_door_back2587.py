"""BACK-2587: the help front door tells live adapters from retired ones, and counts only the live ones.

``reveal help://`` listed architecture/classify/depends/deps/hotspots/stats/testability/trace as ordinary
Beta adapters with their pre-retirement descriptions, while ``--adapters`` had a "Retired adapters"
section, and the README claimed 34 adapters when 26 are live. Each view now agrees.
"""

import re
import subprocess
import sys

import pytest

from reveal.adapters.base import list_public_schemes
from reveal.cli.handlers.introspection import retired_schemes


def _reveal(*args):
    proc = subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True, text=True,
                          encoding='utf-8', timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope='module')
def live_count():
    retired = retired_schemes()
    return len([s for s in list_public_schemes() if s not in retired])


def test_there_are_retired_adapters_to_separate():
    assert retired_schemes()  # the positive control: the assertions below are not vacuous


def test_topic_index_lists_retired_adapters_apart_from_live_ones(live_count):
    out = _reveal('help://')
    live_part, _, retired_part = out.partition('### Retired adapters')
    assert retired_part, 'the topic index has no Retired adapters section'
    assert f'### URI Adapters ({live_count})' in live_part
    registered = set(list_public_schemes())
    for scheme, row in retired_schemes().items():
        if scheme not in registered:  # python:// is removed outright: no adapter left to list
            continue
        assert f'  {scheme}://' not in live_part, f'{scheme}:// listed as live'
        assert f'  {scheme}://      - Use {row.replacement}' in retired_part


def test_adapters_header_counts_live_adapters_only(live_count):
    assert f'Registered Adapters ({live_count})' in _reveal('--adapters')


def test_help_adapters_summary_counts_live_adapters_only(live_count):
    assert f'# URI Adapters ({live_count} total)' in _reveal('help://adapters')


def test_quick_help_has_one_gap_row_and_no_internal_adapter():
    rows = [line for line in _reveal('help://quick').splitlines() if 'not named above' in line]
    assert len(rows) == 1
    assert not re.search(r'\breveal\b(?=,|\s+→|$)', rows[0].split('not named above:')[1].split('→')[0])


def test_limit_and_sort_help_name_no_retired_adapter():
    out = _reveal('--help')
    flags = out[out.index('--sort FIELD'):out.index('--since DATE')]
    assert '--limit N' in flags  # the slice holds both flags
    for scheme in retired_schemes():
        assert not re.search(rf'\b{scheme}\b', flags), scheme
