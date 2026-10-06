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
AGENT_HELP.md and guides are inventoried, with discovery commands executed;
target-specific commands remain explicit named-fixture skips. Violations
that exist today are strict xfails naming their task, so a fix fails the run until its entry
is deleted. Text recipes run too, with positive matches for nine result families;
registered grep pipelines run without a shell, and multiline doc arguments stay intact.
"""

import json
import re
import shlex
import shutil
import subprocess

import pytest

from reveal.adapters.help import _EXAMPLE_RECIPES
from claude_session_fixture import build_claude_home
from codex_session_fixture import build_codex_home
from test_output_contract_compliance import _Harness, _build_tree

pytestmark = pytest.mark.contract

# Schemes whose recipes need a network host, a server's own files or credentials.
NEEDS_HOST = ('ssl://', 'nginx://', 'domain://', 'autossl://', 'cpanel://', 'letsencrypt://',
              'mysql://')
# Schemes whose recipes name a recorded session the fixture doesn't have (BACK-1594;
# claude:// has one: tests/claude_session_fixture.py).
NEEDS_SESSION = ()

# Placeholder -> fixture path, longest first; `src` is mapped separately below.
PLACEHOLDERS = (
    ('codex://SESSION-ID', 'codex://019e5cc5'),
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
    query = query.split(' | ')[0]  # first stage; _assert_text_as_written executes the remaining stages
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
    _enrich_recipe_tree(root)
    build_claude_home(root / 'home')
    build_codex_home(root / 'home')
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('DB_RECIPE_FIXTURE', 'fixture-db')
        yield _Harness(root)


def _enrich_recipe_tree(root):
    """Positive matches for documented claims, separate from the base contract fixture."""
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(30))
    padding = ''.join(f'    x += {i}\n' for i in range(110))
    (root / 'proj' / 'claims.py').write_text(
        'import requests\nfrom abc import ABC, abstractmethod\n'
        'class Boundary(ABC):\n    @abstractmethod\n    def run(self):\n        pass\n'
        'def auth_gate(x):\n    return x\n'
        'def error_handler(x):\n    return x\n'
        f'def query_complex(x):\n{branches}    return -1\n'
        f'def large_function(x):\n{padding}    return x\n'
        'def external_boundary():\n    return requests.get("https://example.invalid")\n',
        encoding='utf-8')
    (root / 'proj' / 'cycle_a.py').write_text('import cycle_b\n', encoding='utf-8')
    (root / 'proj' / 'cycle_b.py').write_text('import cycle_a\n', encoding='utf-8')
    (root / 'proj' / 'README.md').write_text(
        '---\ntitle: Fixture\ntype: guide\n---\n# Proj\n'
        'nginx deploy auth token\n\nSee [auth](auth.md) and [app](app.py).\n', encoding='utf-8')
    (root / 'proj' / 'auth.md').write_text('# Auth\nAuthentication token guide.\n', encoding='utf-8')


def _pipeline(query):
    """Split shell pipes without splitting quoted URI operators; never invoke a shell."""
    lexer = shlex.shlex(query, posix=True, punctuation_chars='|')
    lexer.whitespace_split = True
    stages = [[]]
    for token in lexer:
        if token == '|':
            stages.append([])
        else:
            stages[-1].append(token)
    assert all(stages), f'Empty pipeline stage: {query}'
    return stages


def _assert_text_as_written(harness, query):
    stages = _pipeline(query)
    argv = _argv(query)
    code, out, err, _ = harness.run_subcommand(argv[0], *argv[1:])
    problems = [line for line in err.splitlines()
                if PROBLEM_LINE.search(line) and not any(n in line for n in ENVIRONMENT_NOISE)]
    assert not problems, f"{query}: text stderr {problems[:3]}"
    assert code in FINDINGS_EXITS.get(argv[0], {0}), f"{query}: text exit {code}"
    assert out.strip(), f"{query}: text renderer printed nothing"
    for stage in stages[1:]:
        assert stage[0] == 'grep', f'Pipeline stage needs an explicit fixture: {stage}'
        if not shutil.which('grep'):
            pytest.skip('grep is unavailable on this CI platform; pipeline requires it')
        filtered = subprocess.run(stage, input=out, capture_output=True, text=True,
                                  encoding='utf-8', timeout=30)
        assert filtered.returncode == 0 and filtered.stdout.strip(), (
            f"{query}: pipeline matched nothing: {filtered.stderr}")
        out = filtered.stdout
    return out


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

    return payload


def _assert_positive_claim(query, payload):
    fields = {'ast_query': 'results', 'markdown_query': 'results',
              'circular_dependencies': 'cycles', 'contracts': 'abcs',
              'markdown_backlinks': 'linked_by', 'markdown_link_graph': 'nodes',
              'patches_scan': 'groups', 'calls_uncalled': 'entries',
              'hotspots_scan': 'function_hotspots'}
    field = fields.get(payload.get('type'))
    if field:
        assert payload.get(field), f'{query}: positive fixture matched nothing in {field}'


@pytest.mark.parametrize('recipe', _recipes())
def test_recipe_runs_as_written(harness, recipe):
    payload = _assert_runs_as_written(harness, recipe['query'], recipe.get('output_type'))
    _assert_positive_claim(recipe['query'], payload)
    _assert_text_as_written(harness, recipe['query'])


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
SCHEMA_KNOWN_VIOLATIONS: dict = {}


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


# -- third source: help://fields examples (FIELD_SELECTION_GUIDE.md, BACK-1607) -------------
# The guide's --fields examples answered `{}` (git://) and `results: [{}, ...]` (ast://), and
# named stats:// fields that don't exist; nothing ran them. Each one-line `--format=json`
# example runs here and must select something: no `matched no field` note (stderr), no
# empty answer, no list of empty objects.

# A syntax template, content the fixture doesn't have, or a shell variable set in a loop.
GUIDE_UNRUNNABLE = ('<uri>', 'users.json', '$')


def _guide_field_examples():
    from pathlib import Path

    import reveal
    guide = Path(reveal.__file__).parent / 'docs' / 'guides' / 'FIELD_SELECTION_GUIDE.md'
    commands = []
    for block in re.findall(r'```bash\n(.*?)```', guide.read_text(encoding='utf-8'), re.S):
        for line in block.replace('\\\n', ' ').splitlines():
            line = ' '.join(line.split())
            if line.startswith('reveal ') and '--fields' in line and '--format=json' in line:
                commands.append(line)
    params = []
    for command in dict.fromkeys(commands):
        marks = []
        if any(scheme in command for scheme in NEEDS_HOST):
            marks.append(pytest.mark.skip(reason='needs a live host'))
        elif any(token in command for token in GUIDE_UNRUNNABLE):
            marks.append(pytest.mark.skip(reason='names content the fixture does not have'))
        params.append(pytest.param(command, marks=marks, id=command))
    return params


@pytest.mark.parametrize('command', _guide_field_examples())
def test_guide_field_example_selects_something(harness, command):
    query = _schema_query(command)
    _assert_runs_as_written(harness, query, None)
    argv = _argv(query)
    _, out, _, _ = harness.run_subcommand(argv[0], *argv[1:], '--format', 'json')
    envelope = {'contract_version', 'type', 'source', 'source_type', 'meta'}
    payload = {k: v for k, v in json.loads(out).items() if k not in envelope}
    assert payload, f"{command}: selected nothing"
    for key, value in payload.items():
        assert not (isinstance(value, list) and value and all(item == {} for item in value)), (
            f"{command}: {key} is a list of empty objects")


def test_guide_field_examples_are_enumerated_and_mostly_run():
    params = _guide_field_examples()
    runnable = [p for p in params if not any(m.name == 'skip' for m in p.marks)]
    assert len(params) >= 12 and len(runnable) >= 8, (len(params), len(runnable))


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


def test_pipeline_and_positive_claim_guards_bite(harness):
    assert _pipeline("reveal 'ast://src?complexity>10' | grep query") == [
        ['reveal', 'ast://src?complexity>10'], ['grep', 'query']]
    with pytest.raises(AssertionError, match='pipeline matched nothing'):
        _assert_text_as_written(harness, "reveal env:// --format=grep | grep '^ENV_RECIPE_IMPOSSIBLE'" )
    with pytest.raises(AssertionError, match='positive fixture matched nothing'):
        _assert_positive_claim('negative control', {'type': 'ast_query', 'results': []})


# Fourth source: enumerate AGENT_HELP and guides, beginning with discovery commands.
# Target-specific commands remain visible skips until their named fixtures are added.
def _shell_reveal_commands(block):
    """Keep backslash continuations and quoted multiline arguments together."""
    pending = ''
    for line in block.replace('\\\n', ' ').splitlines():
        if not pending and not line.strip().startswith('reveal '):
            continue
        pending = pending + '\n' + line if pending else line.strip()
        try:
            tokens = shlex.split(pending, comments=True)
        except ValueError:
            continue  # an open quote can legally continue onto the next line
        yield pending, tokens
        pending = ''
    assert not pending, f'Unterminated documented command: {pending}'


def _documentation_commands():
    from pathlib import Path
    import reveal
    docs = Path(reveal.__file__).parent / 'docs'
    sources = [docs / 'AGENT_HELP.md', *sorted((docs / 'guides').glob('*.md'))]
    params = []
    discovery_flags = {'--adapters', '--languages', '--discover', '--agent-help',
                       '--help', '--help-all', '--profiles', '--language-info',
                       '--capabilities', '--explain-file'}
    for source in sources:
        for block in re.findall(r'```(?:bash|sh|shell)\n(.*?)```', source.read_text(encoding='utf-8'), re.S):
            for line, tokens in _shell_reveal_commands(block):
                if not tokens:
                    continue
                query = shlex.join(tokens)
                marks = []
                target = tokens[1]
                if target.startswith('help://') or target in discovery_flags:
                    for key, value in (('<topic>', 'ast'), ('<adapter>', 'ast'),
                                       ('<task>', 'codebase'), ('<lang>', 'python'),
                                       ('<file>', 'proj/app.py')):
                        query = query.replace(key, value)
                    if any(token in query for token in ('<', '$', '|')):
                        marks.append(pytest.mark.skip(reason='discovery template needs explicit shell/content fixture'))
                else:
                    marks.append(pytest.mark.skip(reason='target-specific documentation command needs named fixture (BACK-1365)'))
                params.append(pytest.param(query, marks=marks,
                    id=f'{source.name}:{len(params)}:{line.strip()}'))
    return params


@pytest.mark.parametrize('command', _documentation_commands())
def test_documentation_discovery_runs_as_written(harness, command):
    _assert_text_as_written(harness, command)


def test_documentation_command_inventory_is_not_vacuous():
    params = _documentation_commands()
    runnable = [p for p in params if not any(m.name == 'skip' for m in p.marks)]
    assert len(params) > 200 and len(runnable) > 40


def test_multiline_documentation_collector():
    commands = list(_shell_reveal_commands("reveal 'ast://src' | jq '[.results[] |\n {name}]'\n"))
    assert len(commands) == 1
    assert commands[0][1][-1] == '[.results[] |\n {name}]'
    with pytest.raises(AssertionError, match='Unterminated'):
        list(_shell_reveal_commands("reveal 'ast://unterminated"))


# A next-step block header; the commands follow on the next lines (BACK-1611 item 8).
_HINT_HEADER = re.compile(r'\s*(Next [Ss]teps|Next Commands|Next:|💡 Try:)')
_HINT_COMMAND = re.compile(r'^(?:Next:|💡 Try:)?\s*(reveal\s+\S.*?)(?:\s{2,}#.*)?$')


def _hint_commands(text):
    """`reveal ...` commands printed under next-step headers, comments and templates dropped."""
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines):
        if _HINT_HEADER.match(line):
            for candidate in lines[i:i + 6]:
                match = _HINT_COMMAND.match(candidate.strip())
                if match and '<' not in match.group(1):  # <table> and friends are templates
                    found.append(match.group(1))
    return list(dict.fromkeys(found))


def test_hint_extraction_keeps_commands_and_drops_templates_and_comments():
    text = ("Next steps\n  reveal check proj                  # Run quality rules\n"
            "  reveal 'imports://proj?circular'\n  reveal sqlite://x/<table>\nNext: reveal stats://p  # c\n")
    assert _hint_commands(text) == ["reveal check proj", "reveal 'imports://proj?circular'",
                                    'reveal stats://p']


def test_next_step_hints_in_recipe_output_run(harness):
    """The commands reveal itself suggests after a recipe's output run: no error line, no
    no-effect note, no crash. Exit 1 is a findings exit (check, deps, hotspots)."""
    hints = {}
    for param in _recipes() + _schema_examples():
        if param.marks:
            continue
        query = param.values[0].get('query') or _schema_query(param.values[0]['uri'])
        argv = _argv(query)
        _, out, _, _ = harness.run_subcommand(argv[0], *argv[1:])
        for command in _hint_commands(out):
            hints.setdefault(command, query)
    assert len(hints) >= 8, f'the inventory went vacuous: {sorted(hints)}'
    failures = []
    for command, source in sorted(hints.items()):
        argv = shlex.split(command)[1:]
        code, _, err, _ = harness.run_subcommand(argv[0], *argv[1:])
        problems = [line for line in err.splitlines()
                    if PROBLEM_LINE.search(line) and not any(n in line for n in ENVIRONMENT_NOISE)]
        if code not in (0, 1) or problems:
            failures.append(f'{command} (hinted after {source}): exit {code} {problems[:1]}')
    assert not failures, failures


FORMAT_CHOICES = re.compile(r'--format\s*\{([^}]*)\}')
FORMAT_REJECTED = re.compile(r'not supported by reveal|invalid choice')


def _subcommands(listing):
    """Subcommand names from the 'Subcommands' block that `reveal --help-all` prints."""
    block = listing.split('Subcommands (reveal <subcommand> --help for details):', 1)[1]
    block = block.split('\n\n', 1)[0]
    return re.findall(r'^\s+reveal (\w+)\b', block, re.MULTILINE)


def _rejected_format_choices(harness, name, target):
    """Format values subcommand `name`'s usage line advertises but the command rejects."""
    _, help_text, _, _ = harness.run_subcommand(name, '--help')
    match = FORMAT_CHOICES.search(help_text)
    if not match:
        return None
    rejected = []
    for choice in match.group(1).split(','):
        extra = ['--from', 'main'] if name == 'trace' else [target]
        _, _, err, _ = harness.run_subcommand(name, *extra, '--format', choice.strip())
        if FORMAT_REJECTED.search(err):
            rejected.append(choice.strip())
    return rejected


def test_usage_line_format_choices_are_accepted(harness):
    """`--format {a,b}` in a subcommand's usage line is a claim: every listed value runs
    (BACK-1611 item 6; the 10-01 audit found `typed,grep` listed on 10 subcommands that
    rejected them)."""
    from reveal.main import main
    from contextlib import redirect_stdout
    from io import StringIO
    out = StringIO()
    with redirect_stdout(out), pytest.raises(SystemExit):
        main(['reveal', '--help-all'])
    names = _subcommands(out.getvalue())
    assert len(names) >= 10, f'the subcommand inventory went vacuous: {names}'
    target = str(harness.root)
    checked = {n: _rejected_format_choices(harness, n, target) for n in names}
    assert sum(1 for v in checked.values() if v is not None) >= 10, checked
    assert not {n: v for n, v in checked.items() if v}, checked


def test_usage_line_format_gate_bites(harness):
    """Negative control: a usage line advertising a format the command rejects is caught."""
    class Lying:
        def run_subcommand(self, name, *argv):
            if argv == ('--help',):
                return 0, 'usage: reveal deps [--format {text,json,grep}]', '', []
            return harness.run_subcommand(name, *argv)

    assert _rejected_format_choices(Lying(), 'deps', str(harness.root)) == ['grep']
    assert _rejected_format_choices(harness, 'deps', str(harness.root)) == []
