"""The first screen teaches no retired spelling (BACK-2196).

Retired spellings still run and print a "replaced by" note, so the executable-docs gate cannot see a
README that teaches them. This ratchet reads the one ``RETIREMENTS`` table and fails when a teaching
surface names a retired spelling outside a sentence that says it is retired:

- ``README.md`` and ``ROADMAP.md`` (the public face),
- the first section of ``AGENT_HELP.md`` (everything before "Common Tasks"),
- ``help://quick`` and every ``help://examples/<task>`` recipe.

The scanner is scripts/check_retired_names.py, run by ci-local.sh (also with --no-tests) and CI; this file
holds its controls. A new ``RETIREMENTS`` row is covered the day it lands: the patterns are derived from the key's kind
(``subcommand:``, ``scheme:``, ``param:``, ``value:``, ``flag:``, ``target:``), and a kind this file does
not know fails ``test_every_row_has_a_pattern``. Each row also has a positive control: a spelling built
from the row must be found, so a pattern that silently matches nothing cannot pass.

Spellings that are due to retire but have no row yet (``architecture``, ``hotspots``) join the ratchet
when their rows land (BACK-2070, BACK-2149).
"""
import pytest

from scripts.check_retired_names import RETIREMENTS, SURFACES, _patterns, _sample, scan, surface_hits

# --- the scanner itself: patterns exist, find their spelling, and spare the live ones ----------

def test_every_row_has_a_pattern():
    assert [key for key in RETIREMENTS if not _patterns(key)] == []


@pytest.mark.parametrize('key', sorted(RETIREMENTS))
def test_each_row_is_found_when_a_doc_teaches_it(key):
    assert [hit[1] for hit in scan(_sample(key))].count(key) == 1, _sample(key)


@pytest.mark.parametrize('key', sorted(k for k in RETIREMENTS if k.startswith('subcommand:')))
def test_a_bare_backticked_subcommand_in_a_prose_list_is_found(key):
    name = key.partition(':')[2]
    assert [hit[1] for hit in scan(f'`check` 0 clean; `{name}` 0 pass, 1 findings; `health` 0 pass')] == [key]


@pytest.mark.parametrize('key', sorted(RETIREMENTS))
def test_each_row_is_spared_in_a_replaced_by_sentence(key):
    assert scan(f'{_sample(key)}  # was: the old spelling, retired') == []
    assert scan(f'`{_sample(key)}` is retired.\nUse something else.') == []


def test_a_list_item_is_judged_without_its_neighbours():
    text = '- `review` 0 pass, 1 findings\n- `deps` is retired, use imports'
    assert [hit[1] for hit in scan(text)] == ['subcommand:review']


@pytest.mark.parametrize('line', [
    'reveal ssl://example.com --check',
    'reveal @domains.txt --check',
    'nginx.conf --extract domains | reveal --stdin --check',
    'reveal health ssl://api.example.com domain://example.com',
    'reveal health nginx.conf',
    'reveal check src/ --changed main..HEAD',
    "reveal 'calls://src/?callers=fn&depth=3'",
    'reveal calls src --callees main --depth 2 --detail',
    "reveal 'imports://src/?importers'",
    "reveal 'metrics://src/?hotspots=true'",
    "reveal 'patches://tests/?view=pressure'",
    "reveal 'ast://src/?type=function&complexity>10'",
    'reveal src/app.py --check-only',
    '| `reveal health [path]` | Ops health | `reveal health --help` |',
])
def test_the_live_spellings_are_not_flagged(line):
    assert scan(line) == []


# --- the surfaces --------------------------------------------------------------------------

@pytest.mark.parametrize('surface', sorted(SURFACES))
def test_the_surface_teaches_no_retired_spelling(surface):
    hits = surface_hits(surface)
    assert hits == [], f'{surface} teaches a retired spelling (name it only in a "replaced by" sentence):\n' + \
        '\n'.join(f'  line {n}: {key}: {line}' for n, key, line in hits)


def test_the_script_exits_0_on_the_current_tree():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    done = subprocess.run([sys.executable, 'scripts/check_retired_names.py'], cwd=root, capture_output=True,
                          text=True, encoding='utf-8', check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'ratchet OK' in done.stdout
