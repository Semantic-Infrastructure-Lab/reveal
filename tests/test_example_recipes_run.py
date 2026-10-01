"""Every ``help://examples`` recipe runs as written (BACK-1365, first slice).

``help://examples/<task>`` is the cheapest answer reveal gives an agent, and nothing ran it:
recipes drifted from the code (a flag the adapter ignores, a result type that was renamed)
and only a hand audit found out (BACK-859, blazing-permafrost-0925). This runs each recipe
in the contract harness's hermetic fixture tree (``tests/test_output_contract_compliance``)
and fails when one

- exits nonzero, beyond its command's own findings exit (``review`` 1 = warnings),
- prints a warning or error on stderr (the flag ledger's "has no effect" note, an error), or
  carries a ``meta.warnings`` entry saying the query named something the adapter doesn't
  have (``unknown_filter_key``, ``unknown_sort_field``, ...), or
- answers with a result ``type`` other than the recipe's ``output_type``.

Placeholders (``<repo>``, ``src``, ``/path/to/app.db``) are mapped onto the fixture. Recipes
that need a live host, a server's config or a recorded session are skipped with the reason;
the other help surfaces (AGENT_HELP.md, guides) are later slices of BACK-1365. Violations
that exist today are strict xfails naming their task, so a fix fails the run until its entry
is deleted.
"""

import json
import re
import shlex

import pytest

from reveal.adapters.help import _EXAMPLE_RECIPES
from test_output_contract_compliance import _Harness, _build_tree

pytestmark = pytest.mark.contract

# Schemes whose recipes need a network host, a server's own files or credentials.
NEEDS_HOST = ('ssl://', 'nginx://', 'domain://', 'autossl://', 'cpanel://', 'letsencrypt://',
              'mysql://')
# Schemes whose recipes name a recorded session the fixture doesn't have (BACK-1594).
NEEDS_SESSION = ('claude://', 'codex://')

# Placeholder -> fixture path, longest first; `src` is mapped separately below.
PLACEHOLDERS = (
    ('<old-tag>..<new-tag>', 'v1..v2'),
    ('<repo>/<module>', 'proj/app.py'),
    ('<repo>', 'proj'),
    ('<file>', 'proj/app.py'),
    ('<refA>', 'v1'),
    ('<refB>', 'v2'),
    ('/path/to/app.db', 'proj/app.db'),
    ('/path/to/data.xlsx', 'proj/data.xlsx'),
    ('docs/README.md', 'proj/README.md'),
    ('docs/', 'proj/'),
    ('config.json', 'proj/data.json'),
)

# A subcommand's own findings exit (its --help states it); anything else must exit 0.
FINDINGS_EXITS = {'review': {0, 1}}

# A stderr line that reports a problem. Progress lines (review's "Scanning complexity…")
# are not one.
PROBLEM_LINE = re.compile(r'(?i)\b(error|warning|note|no effect|unknown|not recognized|ignored)\b')
# stderr lines that are the test environment talking, not the recipe.
ENVIRONMENT_NOISE = ('not yet downloaded',)
# meta.warnings that mean the query itself drifted. The standing disclosures (W-CALLS-1
# "dynamic dispatch is not resolved", complexity_is_unweighted) are true of every run.
DRIFT_WARNING = re.compile(r'^unknown_')

KNOWN_VIOLATIONS = {
    'reveal src/': 'BACK-1591',
    'reveal python://packages': 'BACK-1591',
}


def _recipes():
    params = []
    for task, group in sorted(_EXAMPLE_RECIPES.items()):
        for recipe in group['recipes']:
            query = recipe['query']
            marks = []
            if any(scheme in query for scheme in NEEDS_HOST):
                marks.append(pytest.mark.skip(reason='needs a live host or server files'))
            elif any(scheme in query for scheme in NEEDS_SESSION):
                marks.append(pytest.mark.skip(reason='needs a recorded session (BACK-1594)'))
            elif query in KNOWN_VIOLATIONS:
                marks.append(pytest.mark.xfail(strict=True, reason=f'{KNOWN_VIOLATIONS[query]}: known violation'))
            params.append(pytest.param(recipe, marks=marks, id=f'{task}:{query}'))
    return params


def _argv(query):
    """The recipe as the argv `reveal` gets, placeholders mapped onto the fixture."""
    query = query.split(' | ')[0]  # `reveal env:// | grep '^DB'`: the reveal half
    for placeholder, path in PLACEHOLDERS:
        query = query.replace(placeholder, path)
    argv = shlex.split(query)
    if argv[0] == 'reveal':
        argv = argv[1:]
    return [('proj' + a[3:] if a == 'src' or a.startswith('src/') else a.replace('://src', '://proj'))
            for a in argv]


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    root = tmp_path_factory.mktemp('recipe_harness')
    _build_tree(root)
    return _Harness(root)


@pytest.mark.parametrize('recipe', _recipes())
def test_recipe_runs_as_written(harness, recipe):
    argv = _argv(recipe['query'])
    code, out, err, _ = harness.run_subcommand(argv[0], *argv[1:], '--format', 'json')
    problems = [line for line in err.splitlines()
                if PROBLEM_LINE.search(line) and not any(n in line for n in ENVIRONMENT_NOISE)]
    assert not problems, f"{recipe['query']}: stderr {problems[:3]}"
    assert code in FINDINGS_EXITS.get(argv[0], {0}), f"{recipe['query']}: exit {code}"
    payload = json.loads(out)
    warnings = [w for w in (payload.get('meta') or {}).get('warnings') or []
                if isinstance(w, dict) and DRIFT_WARNING.match(str(w.get('type', '')))]
    assert not warnings, f"{recipe['query']}: meta.warnings {warnings[:2]}"
    if recipe.get('output_type'):
        assert payload.get('type') == recipe['output_type'], (
            f"{recipe['query']}: type {payload.get('type')!r}, the recipe says {recipe['output_type']!r}")


def test_the_recipe_gate_bites(harness):
    """Positive control: each check sees the drift it is for, so a clean run is not a check
    that can't fail -- a flag the adapter ignores (stderr), a key it doesn't have
    (meta.warnings), and a type the recipe would misname."""
    _, _, err, _ = harness.run_subcommand('ast://proj', '--expiring-within', '30', '--format', 'json')
    assert any(PROBLEM_LINE.search(line) for line in err.splitlines()), err
    _, out, _, _ = harness.run_subcommand('ast://proj?no_such_key=1', '--format', 'json')
    payload = json.loads(out)
    assert [w['type'] for w in payload['meta']['warnings']] == ['unknown_filter_key']
    assert payload['type'] == 'ast_query' != 'contracts'


def test_every_task_has_a_recipe_that_runs():
    """The skips can't swallow a whole task: each task keeps at least one recipe that runs."""
    runnable = {task for task, group in _EXAMPLE_RECIPES.items()
                for r in group['recipes']
                if not any(s in r['query'] for s in NEEDS_HOST + NEEDS_SESSION)}
    skipped_whole = set(_EXAMPLE_RECIPES) - runnable
    assert skipped_whole <= {'infrastructure', 'sessions', 'history'}, skipped_whole
