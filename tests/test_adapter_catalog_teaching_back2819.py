"""The adapter catalogs teach each analysis noun's subcommand (BACK-2819, residue of BACK-2713; D20).

``reveal help://adapters`` printed ``Example: imports://src``, ``Syntax: metrics://<path>[?<filters>]`` and
``Example: metrics://./src``, and ``reveal --adapters`` printed ``Example: reveal imports://src`` and
``Example: reveal metrics://./src``: analysis-only schemes and a query string, both retiring under D20. The lines
come from the nouns' help data (``reveal/adapters/help_data/{imports,metrics}.yaml``: the first example and the
syntax). The catalogs' own headings name every adapter by its scheme, which the discovery folding settles
(BACK-1055, BACK-2818); this file judges only the Example and Syntax lines.
"""
import json

import pytest

from conftest import _run_reveal_direct
from teaching_patterns import retiring_lines

SURFACES = {
    'help://adapters': (('help://adapters',), '## {scheme}://'),
    '--adapters': (('--adapters',), '  {scheme}://'),
}


def _section(text, heading):
    """The heading's block: from its line to the next blank line."""
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines))
    return lines[start + 1:end]


def _taught(surface, scheme):
    args, heading = SURFACES[surface]
    result = _run_reveal_direct(*args)
    assert result.returncode == 0, result.stderr
    taught = [line.strip() for line in _section(result.stdout, heading.format(scheme=scheme))
              if line.strip().startswith(('Example:', 'Syntax:'))]
    assert taught, f'{surface} prints no Example or Syntax line for {scheme}'
    return taught


@pytest.mark.parametrize('surface', sorted(SURFACES))
@pytest.mark.parametrize('scheme', ['imports', 'metrics'])
def test_the_catalogs_teach_the_subcommand(surface, scheme):
    taught = _taught(surface, scheme)
    assert not [line for line in taught if retiring_lines(line)], taught
    assert any(f'reveal {scheme} ' in line for line in taught), taught


@pytest.mark.parametrize('surface', sorted(SURFACES))
@pytest.mark.parametrize('scheme', ['ast', 'calls'])
def test_sibling_nouns_already_teach_the_subcommand(surface, scheme):
    """Negative control: nouns whose help data was migrated before keep their lines."""
    taught = _taught(surface, scheme)
    assert not [line for line in taught if retiring_lines(line)], taught


def test_the_help_adapters_json_example_is_the_subcommand():
    result = _run_reveal_direct('help://adapters', '--format', 'json')
    adapters = json.loads(result.stdout)['adapters']
    for scheme in ('imports', 'metrics'):
        assert adapters[scheme]['example'].startswith(f'reveal {scheme} '), adapters[scheme]
        assert adapters[scheme]['syntax'].startswith(f'reveal {scheme} '), adapters[scheme]


@pytest.mark.parametrize('line', ['Example: imports://src', 'Syntax: metrics://<path>[?<filters>]',
                                  'Example: reveal metrics://./src'])
def test_the_check_bites_on_the_lines_it_replaced(line):
    """Positive control: the lines the catalogs printed are found."""
    assert retiring_lines(line) == [line]
