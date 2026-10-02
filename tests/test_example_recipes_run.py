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

KNOWN_VIOLATIONS: dict = {}


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


def _assert_runs_as_written(harness, query, output_type):
    argv = _argv(query)
    code, out, err, _ = harness.run_subcommand(argv[0], *argv[1:], '--format', 'json')
    problems = [line for line in err.splitlines()
                if PROBLEM_LINE.search(line) and not any(n in line for n in ENVIRONMENT_NOISE)]
    assert not problems, f"{query}: stderr {problems[:3]}"
    assert code in FINDINGS_EXITS.get(argv[0], {0}), f"{query}: exit {code}"
    payload = json.loads(out)
    warnings = [w for w in (payload.get('meta') or {}).get('warnings') or []
                if isinstance(w, dict) and DRIFT_WARNING.match(str(w.get('type', '')))]
    assert not warnings, f"{query}: meta.warnings {warnings[:2]}"
    if output_type:
        assert payload.get('type') == output_type, (
            f"{query}: type {payload.get('type')!r}, the recipe says {output_type!r}")


@pytest.mark.parametrize('recipe', _recipes())
def test_recipe_runs_as_written(harness, recipe):
    _assert_runs_as_written(harness, recipe['query'], recipe.get('output_type'))


# -- second source: every adapter's get_schema()['example_queries'] (BACK-1599) -------------
# Nothing executed these (~200): reveal://adapters/reveal.py get_element had been dead since it
# was written (BACK-1565). They are written in their own dialect, so the placeholders differ.

SCHEMA_PLACEHOLDERS = (
    ('/path/to/app.db', 'proj/app.db'),
    ('/path/to/file.xlsx', 'proj/data.xlsx'),
    ('/path/to/data.xlsx', 'proj/data.xlsx'),
    ('sqlite://./relative/path/data.db', 'sqlite://proj/app.db'),
    ('project/src/main.c', 'proj/app.py'),
    ('root=project', 'root=proj'),
    ('src/utils.py', 'proj/app.py'),
    ('src/main.py', 'proj/app.py'),
    ('src/core.py', 'proj/app.py'),
    ('src/app.py', 'proj/app.py'),
    ('src/models/', 'proj/tests/'),
    ('main.py', 'proj/app.py'),
    ('package.json', 'proj/data.json'),
    ('data.json', 'proj/data.json'),
    ('config.json', 'proj/data.json'),
    ('diff://app.py:backup/app.py', 'diff://proj/app.py:proj/app_old.py'),
    ('diff://app.py:git://app.py@HEAD~1', 'diff://proj/app.py:git://proj/app.py@HEAD~1'),
    ('diff://app.py:old.py/handle_request', 'diff://proj/app.py:proj/app_old.py/main'),
    ('markdown://sessions/', 'markdown://proj/'),
    ('patches://tests', 'patches://proj/tests'),
    ('./src', 'proj'),
    ('docs/', 'proj/'),
)
_PLACEHOLDER_RE = re.compile('|'.join(re.escape(p) for p, _ in SCHEMA_PLACEHOLDERS))
_PLACEHOLDER_MAP = dict(SCHEMA_PLACEHOLDERS)

# Examples that name content no shared fixture has (a host, a ref, a sheet, an env var, a JSON
# key). Their syntax is not checked here; a fixture that grew the content would be.
SCHEMA_UNRUNNABLE = (
    'diff://mysql://', 'diff://git://app.py@main', 'git://.@abc1234', 'git://.@main',
    'git://src/app.py@v1.0', 'element=load_config', 'sheet=Sales', 'env://DATABASE_URL',
    'json://data.json/users', 'json://package.json/', 'format=dot',
    # Depend on the interpreter running the suite: a venv, an installed `requests`.
    'python://venv', 'python://packages/requests',
)
# Also needs a live host / package / session beyond the recipe list's schemes.
SCHEMA_SKIP_SCHEMES = NEEDS_HOST + NEEDS_SESSION

# uri -> task naming why it fails today. Strict xfail: fixing one fails the run until deleted.
SCHEMA_KNOWN_VIOLATIONS: dict = {
    # An element diff's `type` is its verdict (added/removed/modified/unchanged), not a result type.
    'diff://app.py:old.py/handle_request': 'BACK-1637',
}


def _schema_examples():
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    params = []
    for scheme in sorted(list_supported_schemes()):
        schema = get_adapter_class(scheme).get_schema() or {}
        for example in schema.get('example_queries', []):
            uri = example['uri']
            marks = []
            if any(uri.startswith(s) for s in SCHEMA_SKIP_SCHEMES):
                marks.append(pytest.mark.skip(reason='needs a live host or recorded session'))
            elif any(u in uri for u in SCHEMA_UNRUNNABLE):
                marks.append(pytest.mark.skip(reason='names content the fixture does not have'))
            elif uri in SCHEMA_KNOWN_VIOLATIONS:
                marks.append(pytest.mark.xfail(
                    strict=True, reason=f'{SCHEMA_KNOWN_VIOLATIONS[uri]}: known violation'))
            params.append(pytest.param(example, marks=marks, id=f'{scheme}:{uri}'))
    return params


def _schema_query(uri):
    """One pass, so a replacement is never itself replaced (data.json -> proj/data.json)."""
    uri = _PLACEHOLDER_RE.sub(lambda m: _PLACEHOLDER_MAP[m.group(0)], uri)
    return uri.replace('://src', '://proj')


@pytest.mark.parametrize('example', _schema_examples())
def test_schema_example_runs_as_written(harness, example):
    _assert_runs_as_written(harness, _schema_query(example['uri']), example.get('output_type'))


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


def test_schema_examples_are_enumerated_and_mostly_run():
    """A positive control for the second source: an empty enumeration would pass vacuously."""
    params = _schema_examples()
    runnable = [p for p in params if not any(m.name == 'skip' for m in p.marks)]
    assert len(params) > 150 and len(runnable) > 100, (len(params), len(runnable))
