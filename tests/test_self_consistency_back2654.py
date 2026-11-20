"""Reveal's own spellings follow its rules (BACK-2654 Step 5, COMMAND_MODEL "Cross-noun rules and conformance").

Every URI or command reveal itself prints or builds must run under the cross-noun rules without an invalid-request
exit 2 and without a retirement note: a hint that teaches a retired spelling, or one the rules reject, sends the reader
to a note or an error, and a spelling reveal builds for itself breaks at the cut. Everything is collected from its
producers, never from a hand list:

- printed: next-step hints, breadcrumbs and every other line of each declared noun's answers (text and JSON, the
  default request, each canonical view or mode, and requests that make a noun print its cut hints), the file route's
  breadcrumbs, the help pages (``--agent-help``, ``help://``, ``help://quick``, ``help://examples/<task>``,
  ``help://<noun>`` and ``help://schemas/<noun>`` in text and JSON, each subcommand's ``--help``), each declared
  control's ``examples`` and the MCP tool descriptions. Each command found is mapped onto the recipe harness's fixture
  (placeholders and paths, as the recipe gate maps them), run with ``--format json`` and judged by the answer itself:
  ``meta.errors`` naming ``invalid_request`` with exit 2, or a ``retired_spelling`` entry in ``meta.warnings``. "Not
  found" answers are not judged: they say the fixture lacks the name, not that the spelling is wrong. A bare flag in a
  hint or help line ("use --verbose for the full text") is checked against the noun's retired CLI spellings.
- built: the query fragment each global flag injects into a declared noun's URI, and the queries and typed parameters
  a noun builds for the nouns it composes in-process. No note is printed for those (notes come from the spelling the
  caller typed), so they are judged at the one binder every declared noun goes through: a request typed canonically
  must bind no legacy spelling.

A retired scheme's own help and answers may name that scheme, and a legacy control's own example may spell it (each is
that row's note); the other exemptions are written below with their reasons. The generated row family for bare
shared-control keys on the open-field nouns (``param:NOUN.NAME``: ``markdown://docs?kind=guide`` now notes
``where=kind=guide``) is not in RETIREMENTS; the binder check and the retired-names doc ratchet both read it
(``invocation.generated_retirements``).
"""
import asyncio
import json
import re
import shlex

import pytest

from conftest import is_request_note
from test_example_recipes_run import PLACEHOLDERS, harness  # noqa: F401  (the module-scoped fixture)
from claude_session_fixture import SESSION_NAMES
from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.adapters.factory import uses_bound_query_call
from reveal.adapters.help import _EXAMPLE_RECIPES
from reveal.cli.invocation import COMMANDS, RETIREMENTS, SWITCHES
from reveal.cli.routing.declared import declared_adapter_class

pytestmark = pytest.mark.contract


def _declared_nouns():
    subcommands = {name for name, spec in COMMANDS.items() if spec.declared_adapter}
    bound = {scheme for scheme in list_supported_schemes() if uses_bound_query_call(get_adapter_class(scheme))}
    return sorted(subcommands | bound)


NOUNS = _declared_nouns()
SUBCOMMANDS = [noun for noun in NOUNS if noun in COMMANDS]
_RETIRED_SCHEMES = {noun for noun in NOUNS if f'scheme:{noun}' in RETIREMENTS}
_SCHEMES = '|'.join(sorted(NOUNS, key=len, reverse=True))
URI = re.compile(rf"(?<![\w/.-])(?:{_SCHEMES})://[^\s'\"`|]*")
COMMAND = re.compile(rf"(?<![\w/.-])reveal\s+(?:{_SCHEMES})(?=\s|$)[^\n`|#\\]*")
# Prose that ends a command quoted in a sentence: "reveal calls <path> --callers NAME - CLI subcommand form".
_PROSE_END = re.compile(r'\s(?:[-\u2014]|or|and|instead|then)(?:\s|$)|\s\(|\s{2,}\S|[,;](?:\s|$)|\.\s|\.$')
# A sentence that shows a request in order to say it is refused: its exit 2 is the point, not a fault.
_REFUSED = re.compile(r'\bexits? 2\b')

_ANSWER_TARGETS = {'claude': 'sessions', 'codex': '', 'json': 'proj/data.json'}
_DEFAULT_ARGS = {'calls': ('--callers', 'main'), 'trace': ('--from', 'main')}
_DEFAULT_QUERY = {'calls': 'callers=main', 'trace': 'from=main'}
# Requests that make a noun print its cut hints ("... 45 more chars, use ... for the full text"): a low snippet budget,
# and every session view of a session whose texts outgrow each fixed display cut (``long_session``).
_LONG_VIEWS = ('', '/messages', '/message/0', '/message/1', '/message/2', '/exchanges', '/prompts', '/thinking',
               '/tools', '/errors', '/workflow', '/timeline', '/digest', '?tools=Bash', '/messages?detail=raw',
               '/prompts?detail=raw', '/message')
_CUT_SURFACES = (('claude://session/infernal-earth-0118/messages', '--max-snippet-chars', '10'),
                 ('claude://session/infernal-earth-0118?tools=Bash', '--max-snippet-chars', '10'),
                 *((f'claude://session/long-session{view}',) for view in _LONG_VIEWS))
_FILE_ROUTE = (('proj/app.py',), ('proj/app.py', 'main'), ('proj/README.md',), ('proj/data.json',), ('proj',),
               ('proj/app.py', '--check'))

@pytest.fixture(scope='module')
def long_session(harness):
    """A recorded session in the harness's Claude home whose prompt, answer, thinking, tool output and Bash command
    each outgrow the display cuts, so the session views print their "N more chars" hints."""
    from claude_session_fixture import PROJECT_DIR, _record, _tool_result, _tool_use, _write_jsonl
    text = 'a long line of session text ' * 40
    turns = [
        ('user', {'role': 'user', 'content': text}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [
            {'type': 'thinking', 'thinking': text}, {'type': 'text', 'text': text},
            _tool_use('t1', 'Bash', command='echo ' + 'x' * 400)], 'usage': {'input_tokens': 1, 'output_tokens': 1}}),
        ('user', {'role': 'user', 'content': [_tool_result('t1', text, is_error=True)]}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [{'type': 'text', 'text': text}],
                       'usage': {'input_tokens': 1, 'output_tokens': 1}}),
    ]
    _write_jsonl(harness.home / '.claude' / 'projects' / PROJECT_DIR / 'long-session.jsonl',
                 [_record(kind, 'long-session', i, message) for i, (kind, message) in enumerate(turns)])
    return harness


# --- collecting ---------------------------------------------------------------------------------------------

def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _texts(out, err):
    """The answer's text: stdout and stderr, and each string of a JSON answer (so a quoted next step is whole)."""
    texts = [out, err]
    try:
        texts.extend(_strings(json.loads(out)))
    except ValueError:
        pass
    return texts


def _found_in(text):
    """Each declared-noun URI and ``reveal NOUN ...`` command in *text*, as printed."""
    found = [match.group(0) for match in URI.finditer(text)]
    for match in COMMAND.finditer(text):
        found.append(_PROSE_END.split(match.group(0), maxsplit=1)[0])
    return found


def _add(found, text, surface):
    for line in text.split('\n'):
        for command in _found_in(line):
            sources = found.setdefault(command.rstrip('.:;,)'), [])
            if (surface, line) not in sources:
                sources.append((surface, line))


def _collect(harness, surfaces):
    """{printed command: [(a surface that printed it, its line), ...]} for each argv in *surfaces*."""
    found = {}
    for argv in surfaces:
        _, out, err, _ = harness.run_subcommand(argv[0], *argv[1:])
        for text in _texts(out, err):
            _add(found, text, ' '.join(argv))
    return found


def _operation_requests(noun):
    """The noun's canonical answers beside its default: each view value and each boolean operation control."""
    adapter = declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)
    queries = []
    sharing = [scheme for scheme in list_supported_schemes()
               if getattr(get_adapter_class(scheme), 'PARAM_SPECS', None) is adapter.PARAM_SPECS] or [noun]
    for spec in adapter.PARAM_SPECS:
        if spec.role != 'operation' or any(f'param:{s}.{spec.name}' in RETIREMENTS for s in (noun, *sharing)):
            continue
        if spec.choices:
            queries.extend(f'{spec.name}={choice}' for choice in spec.choices)
        elif spec.type == 'boolean':
            queries.append(spec.name)
    return queries


def _answer_surfaces():
    surfaces = []
    for noun in NOUNS:
        target = _ANSWER_TARGETS.get(noun, 'proj')
        base = _DEFAULT_QUERY.get(noun)
        uri = f'{noun}://{target}' + (f'?{base}' if base else '')
        surfaces += [(uri,), (uri, '--format', 'json')]
        for query in _operation_requests(noun):
            surfaces.append((f'{noun}://{target}?' + '&'.join(filter(None, (base, query))), '--format', 'json'))
        if noun in COMMANDS:
            argv = (noun, target or '.', *_DEFAULT_ARGS.get(noun, ()))
            surfaces += [argv, (*argv, '--format', 'json'), (*argv, '--nosuchflag')]
        # A refused or typo'd request prints the noun's teaching: the supported controls, a "did you mean" hint.
        for typo in ('nosuchkey=1', 'functions'):
            surfaces.append((f'{noun}://{target}?' + '&'.join(filter(None, (base, typo))),))
    return surfaces + list(_CUT_SURFACES) + list(_FILE_ROUTE)


def _help_surfaces():
    surfaces = [('--help',), ('--help-all',), ('--agent-help',), ('help://',), ('help://quick',), ('help://examples',)]
    surfaces += [(f'help://examples/{task}',) for task in sorted(_EXAMPLE_RECIPES)]
    for noun in NOUNS:
        surfaces += [(f'help://{noun}',), (f'help://{noun}', '--format', 'json'),
                     (f'help://schemas/{noun}', '--format', 'json')]
    return surfaces + [(noun, '--help') for noun in SUBCOMMANDS]


# Where a control example's fragment runs: Codex's examples are a session's controls; Claude's carry their own
# resource (``/messages?detail=raw``) or none (``?tools=Bash``: each Claude resource is tried, see _candidates).
_EXAMPLE_TARGETS = {'codex': '019e5cc5', 'claude': ''}


def _spec_examples():
    """Each declared control's ``examples`` (shown in help://schemas): a fragment runs on the noun's URI."""
    found = {}
    for noun in NOUNS:
        adapter = declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)
        for spec in adapter.PARAM_SPECS:
            for example in spec.examples:
                if '://' in example:
                    printed = example
                elif example.startswith('/'):
                    printed = f'{noun}://session/infernal-earth-0118{example}'
                else:
                    printed = f"{noun}://{_EXAMPLE_TARGETS.get(noun, 'src')}?{example.lstrip('?')}"
                found.setdefault(printed, []).append((f'help://schemas/{noun} {spec.name}', example))
    return found


def _mcp_descriptions():
    import reveal.mcp_server as mcp_server
    tools = asyncio.run(mcp_server.mcp.list_tools())
    found = {}
    for tool in tools:
        _add(found, tool.description or '', f'MCP {tool.name}')
    return found


# --- mapping onto the fixture -------------------------------------------------------------------------------

# Values that name something in the printed example's project (a function, a file) -> the fixture's own name.
# Every other value is kept as printed, so a value outside a control's choices still fails.
_NAMED_VALUES = {'callers': 'main', 'callees': 'main', 'root': 'main', 'target': 'main', 'from': 'main',
                 'element': 'main', 'importers': 'app.py', 'backlinks': 'README.md', 'tests': 'proj/tests'}
# A placeholder value (``N``, ``<fn>``, ``EXPR``, an empty ``?match=``) by the control's declared type.
_PLACEHOLDER = re.compile(r'^(?:<[^>]*>|[A-Z][A-Z_-]*|\.\.\.|\u2026|)$')
_PLACEHOLDER_VALUES = {'where': 'name=main', 'since': '2026-01-01', 'until': '2030-01-01', 'against': 'HEAD',
                       'match': 'hello', 'search': 'hello', 'contains': 'hello', 'kind': 'function',
                       **{name: '2' for name in ('depth', 'limit', 'offset', 'top', 'min', 'lines', 'complexity')}}


def _spec(noun, key):
    adapter = declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)
    key = key.replace('_', '-')
    return next((spec for spec in getattr(adapter, 'PARAM_SPECS', ())
                 if key in {s.replace('_', '-') for s in (spec.name, *spec.aliases)}
                 or key in {(f.lstrip('-')) for f in (spec.cli.flags if spec.cli else ())}), None)


def _value(noun, key, value):
    """A runnable value: a placeholder becomes one of the control's own values, a project name the fixture's."""
    spec = _spec(noun, key)
    name = spec.name if spec else key
    if name in _NAMED_VALUES and noun not in ('claude', 'codex') and not (spec and spec.choices):
        return _NAMED_VALUES[name]
    if not _PLACEHOLDER.match(value):
        return value
    if spec is not None and spec.choices:
        return str(spec.choices[0])
    if spec is not None and spec.type in ('integer', 'number'):
        return '2'
    if spec is not None and spec.type == 'boolean':
        return 'true'
    if name == 'where' and spec is not None and spec.fields:
        return f'{spec.fields[0]}~=main'
    return _PLACEHOLDER_VALUES.get(name, 'main')


def _target(noun, path):
    """The fixture resource a printed path stands for: the resource kind is kept (a session's sub-resource, a file
    versus a directory, an element), the names are the fixture's."""
    path = path.strip().rstrip('/')
    if noun == 'claude':
        parts = path.split('/')  # noqa: win-path (a claude:// URI path, never a filesystem path)
        if parts[0] == 'session' and len(parts) > 1:
            name = parts[1] if parts[1] in SESSION_NAMES else 'infernal-earth-0118'
            rest = ['1' if part.isdigit() else part for part in parts[2:]]
            return '/'.join(['session', name, *rest])
        return path or 'sessions'
    if noun == 'codex':
        return re.sub(r'^(?:<[^>]*>|SESSION-ID)', '019e5cc5', path)
    if noun == 'json':
        return 'proj/data.json'
    name, colon, element = path.partition(':')
    if re.search(r'\.md$', name):
        resource = 'proj/README.md'
    elif re.search(r'\.\w{1,4}$', name) and not name.startswith('<'):
        resource = 'proj/app.py'
    else:
        resource = '.' if noun == 'git' else 'proj'
    return resource + (':main' if colon and element else '')


def _query(noun, query):
    """The printed query with placeholder keys (``<query>``, ``params``) dropped and values made runnable."""
    pairs = []
    for part in filter(None, query.split('&')):
        match = re.match(r'^(!?[\w.-]+)(!=|~=|>=|<=|=|>|<)?(.*)$', part)
        if not match or (match.group(1) in ('query', 'params') and not match.group(2)):
            continue  # a template's placeholder (``?<query>``, ``[?params]``)
        key, op, value = match.groups()
        pairs.append(key + (op + _value(noun, key, value) if op else ''))
    return '&'.join(pairs)


def _uri_argv(printed):
    scheme, _, rest = printed.partition('://')
    rest = rest.replace('[', '').replace(']', '').rstrip('\\')
    if rest.startswith((')', '*', '?*')) or '\\' in rest:  # a syntax pattern quoted in prose, not a request
        return None
    path, _, query = rest.partition('?')
    path, _, ref = path.partition('@')
    if scheme in ('claude', 'codex') and re.search(r'[<{]', path):
        return None  # a resource template (``claude://<resource>``): the kinds are listed beside it
    target = _target(scheme, path)
    if scheme == 'git' and ref:
        target += '@v1'
    query = _query(scheme, query)
    return [f'{scheme}://{target}' + (f'?{query}' if query else '')]


def _command_argv(printed):
    try:
        tokens = shlex.split(printed)[1:]
    except ValueError:
        return None
    noun, rest = tokens[0], tokens[1:]
    if not rest or rest[0].startswith('[') or rest[0] in ('is', 'was'):
        return None  # the noun named in a sentence or a usage line, not a request
    path = '' if rest[0].startswith('-') else rest.pop(0)
    path, _, ref = path.partition('@') if noun == 'git' else (path, '', '')
    argv, flag = [noun, (_target(noun, path) or '.') + ('@v1' if ref else '')], None
    for token in rest:
        if token.startswith('['):
            break
        if token.startswith('-'):
            flag, eq, value = token.lstrip('-').partition('=')
            argv.append(f'--{flag}={_value(noun, flag, value)}' if eq else token)
            flag = None if eq else flag
        else:
            argv.append(_value(noun, flag or '', token))
            flag = None
    return argv


def _argv(printed):
    """The printed command as runnable argv on the fixture, or None for a template that names no request."""
    for placeholder, path in PLACEHOLDERS:
        printed = printed.replace(placeholder, path)
    if '://' in printed.split()[0]:
        return _uri_argv(printed) if printed.partition('://')[2].strip() else None
    return _command_argv(printed)


def _json_argv(argv):
    """*argv* with ``--format json`` as its only format and no file output."""
    kept, skip = [], False
    for token in argv:
        if skip:
            skip = False
        elif token in ('--format', '--output'):
            skip = True
        elif not token.startswith(('--format=', '--output=')):
            kept.append(token)
    return [*kept, '--format', 'json']


# --- judging ------------------------------------------------------------------------------------------------

def _own_scheme_note(field, surface):
    """A retired scheme's own help and answers name it, and a legacy control's own schema example spells it: the
    note is that scheme's or that control's row."""
    kind, _, name = field.partition(':')
    if kind == 'param':
        noun, _, param = name.partition('.')
        return surface == f'help://schemas/{noun} {param}' or _read_only_under(noun, surface, param)
    return kind in ('scheme', 'subcommand') and name in _RETIRED_SCHEMES and re.search(
        rf'(?:help://(?:schemas/)?{name}\b|^{name}(?:://|\s))', surface)


def _read_only_under(noun, surface, operation):
    """Whether the control whose schema example *surface* is, is read only by the answer the legacy *operation*
    selects (calls ``kind`` by ``uncalled``, ``external`` by ``modules``; BACK-2656): its example can only run there, and
    that operation's own note is the honest answer."""
    prefix = f'help://schemas/{noun} '
    control = _spec(noun, surface[len(prefix):]) if surface.startswith(prefix) else None
    adapter = declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)
    selected = getattr(adapter, 'result_type_for', None)
    return bool(control and control.answers and selected and set(control.answers) == {selected({operation: True})})


def _raw_problems(harness, argv):
    """(kind, field, message) for each fault of the answer to *argv*: an invalid request, a retirement note."""
    code, out, _, _ = harness.run_subcommand(*_json_argv(argv))
    try:
        doc = json.loads(out)
    except ValueError:
        doc = {}
    meta = doc.get('meta') or {} if isinstance(doc, dict) else {}
    problems = []
    errors = [e for e in meta.get('errors') or [] if isinstance(e, dict)]
    if code == 2 and any(e.get('code') == 'invalid_request' for e in errors):
        problems.append(('invalid request', '', str(doc.get('error'))))
    for warning in meta.get('warnings') or []:
        # The URI request's own note is not a printed spelling's fault: reveal's own hints and examples still teach URI forms
        # (BACK-2713), counted by test_doc_uri_requests_only_fall (BACK-2716).
        if isinstance(warning, dict) and warning.get('code') == 'retired_spelling' and not is_request_note(warning):
            problems.append(('note', warning.get('field', ''), str(warning.get('message'))))
    return problems


def _excused(problem, surface):
    kind, field, _ = problem
    return kind == 'note' and _own_scheme_note(field, surface)


def _problems(harness, argv, surface):
    """The faults of *argv*'s answer as printed by *surface*, one line each."""
    return [f'{kind}: {message}' for kind, field, message in _raw_problems(harness, argv)
            if not _excused((kind, field, message), surface)]


# A Claude query printed without its resource (``claude://?tools=Bash``) answers on one of these.
_CLAUDE_RESOURCES = ('session/infernal-earth-0118', 'sessions', 'search', 'history', 'config',
                     'session/infernal-earth-0118/files')
# A control example of a noun that needs an operation runs beside one of its operations (calls ``detail`` reads
# callees only, ``limit`` the ranking).
# Every calls mode: a control example runs on the first answer that reads it (BACK-2656 refuses it elsewhere).
_OPERATIONS = {'calls': ('callers=main', 'callees=main', 'sort=-callers', 'uncalled', 'modules'), 'trace': ('from=main',)}


def _candidates(printed, examples=False):
    """The runnable argv for *printed*: one; one per Claude resource for a resource-less Claude query; one per
    operation for a calls or trace control example (*examples*) printed without its operation."""
    if printed.startswith('claude://?'):
        return [a for a in (_argv(f'claude://{resource}{printed[9:]}') for resource in _CLAUDE_RESOURCES) if a]
    scheme, _, rest = printed.partition('://')
    path, _, query = rest.partition('?')
    keys = [re.split(r'[=<>~!]', part)[0] for part in query.split('&') if part]
    if examples and scheme in _OPERATIONS and keys and not any(
            getattr(_spec(scheme, key), 'role', None) == 'operation' for key in keys):
        return [a for a in (_argv(f'{scheme}://{path}?{op}&{query}') for op in _OPERATIONS[scheme]) if a]
    argv = _argv(printed)
    return [argv] if argv else []


def _judge(harness, found, examples=False):
    """The problems of every printed command in *found*, one line each, and how many ran. A resource-less query
    is judged on the first resource that takes it."""
    failures, ran = [], {}
    for printed, sources in sorted(found.items()):
        candidates = _candidates(printed, examples)
        for argv in candidates:  # each request runs once; every printed spelling of it is judged
            if tuple(argv) not in ran:
                ran[tuple(argv)] = _raw_problems(harness, argv)
        for surface, line in sources if candidates else ():
            failures.extend(_verdict(printed, surface, line, candidates, ran))
    return failures, len(ran)


def _verdict(printed, surface, line, candidates, ran):
    """The failure lines of one printed command on one surface."""
    judged = [(argv, [f'{p[0]}: {p[2]}' for p in ran[tuple(argv)] if not _excused(p, surface)])
              for argv in candidates]
    argv, problems = next(((a, p) for a, p in judged if not any(x.startswith('invalid') for x in p)), judged[0])
    return [f'{surface} prints {printed!r} (ran {" ".join(argv)}): {problem}' for problem in problems
            if not (problem.startswith('invalid request') and _REFUSED.search(line))]


# --- the tests ----------------------------------------------------------------------------------------------

def test_hints_and_lines_in_every_declared_answer_follow_the_rules(long_session):
    """Next steps, breadcrumbs and every other command a declared noun's answer prints (and the file route's)."""
    failures, ran = _judge(long_session, _collect(long_session, _answer_surfaces()))
    assert ran >= 18, f'the inventory went vacuous: {ran} commands'
    assert not failures, '\n'.join(failures)


def test_help_examples_follow_the_rules(harness):
    """Every command a help page prints: --agent-help, help://, help://<noun> and its schema, each --help."""
    failures, ran = _judge(harness, _collect(harness, _help_surfaces()))
    assert ran >= 200, f'the inventory went vacuous: {ran} commands'
    assert not failures, '\n'.join(failures)


def test_control_examples_follow_the_rules(harness):
    """Each declared control's examples (help://schemas shows them under query_params)."""
    failures, ran = _judge(harness, _spec_examples(), examples=True)
    assert ran >= 100, f'the inventory went vacuous: {ran} commands'
    assert not failures, '\n'.join(failures)


def test_mcp_descriptions_follow_the_rules(harness):
    failures, ran = _judge(harness, _mcp_descriptions())
    assert ran >= 4, f'the inventory went vacuous: {ran} commands'
    assert not failures, '\n'.join(failures)


# A sentence that names an old spelling to say it is old (the retired-names ratchet's REPLACED_BY_CONTEXT, plus
# "legacy", the word the schemas use for a declared legacy entry).
_RETIREMENT_CONTEXT = re.compile(r'retired|retiring|deprecated|replaced|replaces|renamed|legacy|no longer|\(was\b|\bwas:|'
                                 r'formerly|instead of|\bnote:', re.IGNORECASE)


def _retired_spellings(noun):
    """{pattern: spelling} for the noun's note-stage RETIREMENTS rows: each CLI flag, each bare query key in a hint
    ("add ?full"), the global ``--verbose`` (rule 4), and each switch's legacy flag (rule 15: a hint teaches
    ``--group off``, never ``--no-group``; the rows are generated from SWITCHES)."""
    spellings = {'--verbose', *(switch.legacy_flag for switch in SWITCHES.values())}
    for key, row in RETIREMENTS.items():
        if key.startswith(f'param:{noun}.') and row.stage == 'note':
            spellings.update(re.findall(r'(?<![\w-])--[\w-]+', row.old))
            spellings.add('?' + key.partition('.')[2])
    return {(rf'(?<![\w-]){re.escape(s)}(?![\w-])' if s.startswith('--') else rf'[?&]{re.escape(s[1:])}(?![\w-])'): s
            for s in spellings}


def _owner(surface, line):
    """The declared noun a printed line speaks for: the noun of a ``reveal NOUN`` command it prints (testability's page
    teaches ``reveal patches ... --top``, Patches' own pressure cap, BACK-2673), else its surface's noun, else the noun
    the line names as a URI."""
    command = re.search(rf"reveal\s+({_SCHEMES})\b(?!://)", line)
    if command:
        return command.group(1)
    head = surface.split()[0]
    for noun in NOUNS:
        if head in (noun, f'help://{noun}', f'help://schemas/{noun}') or head.startswith(f'{noun}://'):
            return noun
    named = re.search(rf"\b({_SCHEMES})://", line)
    return named.group(1) if named else None


def _retired_flag_lines(harness, surfaces):
    failures = []
    for argv in surfaces:
        surface = ' '.join(argv)
        _, out, err, _ = harness.run_subcommand(argv[0], *argv[1:])
        for text in _texts(out, err):
            for line in text.split('\n'):
                noun = _owner(surface, line)
                if noun is None or _RETIREMENT_CONTEXT.search(line):
                    continue
                for pattern, spelling in sorted(_retired_spellings(noun).items()):
                    if re.search(pattern, line) and not URI.search(line):  # a URI is the judge's to run
                        failures.append(f'{surface} names {spelling} for {noun}: {line.strip()[:160]}')
    return sorted(set(failures))


def test_no_hint_or_help_page_names_a_retired_flag_of_its_noun(long_session):
    """A bare flag in a hint or a help line ("use --verbose for the full text") is not a command the judge can run:
    each declared noun's answers and help page, and the shared pages' lines that name a noun, must not name a retired
    CLI spelling of that noun outside a sentence that says it is retired. Declarations are not teaching: each
    subcommand's ``--help`` option list and the schemas' ``cli_flags`` list every flag the parser still accepts."""
    pages = [argv for argv in _help_surfaces() if argv[-1] != '--help' and not argv[0].startswith('help://schemas/')
             and argv[-1] != 'json']
    failures = _retired_flag_lines(long_session, _answer_surfaces() + pages)
    assert not failures, '\n'.join(failures)


def _flag_values():
    """Each global flag that injects a query fragment, with a value it takes (FLAG_SPECS is the producer)."""
    from reveal.cli.routing.flag_specs import FLAG_SPECS
    samples = {'since': '2020-01-01', 'until': '2030-01-01', 'sort': 'name', 'limit': '2'}
    for spec in FLAG_SPECS:
        if spec.option in ('--verbose', '--hotspots'):  # each is a retired spelling with its own row: noted as typed
            continue
        value = samples.get(spec.dest)
        yield (spec.option, value) if value else (spec.option,)


def _legacy_key(declarations, key, scheme):
    """The retired row *key* spells on a noun with *declarations*, or None: a declared legacy entry, a standalone
    legacy control with its RETIREMENTS row, or the generated bare shared-name family."""
    from reveal.cli.invocation import generated_retirements
    if any(entry.name == key for spec in declarations for entry in getattr(spec, 'legacy', ())):
        return f'param:{scheme}.{key}'
    row = f'param:{scheme}.{key}'
    return row if row in RETIREMENTS or row in generated_retirements() else None


@pytest.fixture
def bindings(monkeypatch):
    """Every request binding the next runs make, as (scheme, keys spelled): the one binder every declared noun and
    every composed child goes through (``query_binding.prepare_declared_params``)."""
    from reveal.utils import query_binding
    owners = {}
    for scheme in list_supported_schemes():
        specs = getattr(get_adapter_class(scheme), 'PARAM_SPECS', None)
        if isinstance(specs, tuple):
            owners.setdefault(id(specs), scheme)
    recorded = []
    real = query_binding.prepare_declared_params

    def recording(declarations, source, transport, **kwargs):
        declarations = tuple(declarations)
        if isinstance(source, str):
            keys = [re.split(r'!=|~=|>=|<=|=|>|<', part)[0] for part in source.split('&') if part]
        else:  # a typed source: each key as the flag that carried it spelled it (Calls keeps --limit in dest top)
            spelled = kwargs.get('spelled') or {}
            keys = [spelled[key][2:].replace('-', '_') if str(spelled.get(key, '')).startswith('--') else key
                    for key in source]
        recorded.append((declarations, owners.get(id(declarations)), keys))
        return real(declarations, source, transport, **kwargs)

    monkeypatch.setattr(query_binding, 'prepare_declared_params', recording)
    return recorded


def _fresh_run(harness, *argv):
    """``reveal *argv`` through main, uncached: the binder runs again even when an earlier test ran this argv."""
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO
    from reveal.main import main
    with harness._hermetic(), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        try:
            main(['reveal', *argv])
        except SystemExit:
            pass


# Built legacy spellings kept until a ruling or the cut, (noun typed, noun bound, legacy key) -> reason.
# CUT_READINESS: empty at the cut.
_RETIRED_COMPOSITIONS = {
    **{('hotspots', 'metrics', key): "the retired hotspots noun is built on metrics' legacy hotspots operation and its "
                                     'legacy top, which answer differently from view=hotspots (rule 16, BACK-2654 note '
                                     '#9): all three are deleted together at the cut'
       for key in ('hotspots', 'top')},
}


def _built_legacy(bindings, harness, requests):
    """Each legacy spelling bound while *requests* (canonical as typed) ran: reveal built it."""
    failures, seen = [], len(bindings)
    for argv in requests:
        start = len(bindings)
        _fresh_run(harness, *argv)
        parent = argv[0].partition('://')[0]
        for declarations, scheme, keys in bindings[start:]:
            for key in keys:
                row = _legacy_key(declarations, key, scheme or '?')
                if row and (parent, scheme, key) not in _RETIRED_COMPOSITIONS:
                    failures.append(f'reveal {" ".join(argv)} binds {key!r} ({row}) on {scheme or "a sub-declaration"}')
    assert len(bindings) > seen, 'nothing bound: the binder moved'
    return sorted(set(failures))


def test_the_binding_recorder_sees_a_legacy_spelling(bindings, harness):
    """Positive control: a legacy spelling typed by the caller is seen at the binder."""
    assert _built_legacy(bindings, harness, [('ast://proj?type=function', '--format', 'json')])
    assert _built_legacy(bindings, harness, [('ast://proj?kind=function', '--format', 'json')]) == []


def test_injected_flag_fragments_are_canonical(bindings, harness):
    """A global flag reaching a declared noun's URI is injected as the control's canonical spelling: the request
    answers, or is refused for the flag the user typed, and never binds a legacy spelling reveal built."""
    requests = []
    for noun in NOUNS:
        target = _ANSWER_TARGETS.get(noun, 'proj')
        base = _DEFAULT_QUERY.get(noun)
        uri = f'{noun}://{target}' + (f'?{base}' if base else '')
        requests += [(uri, *flag, '--format', 'json') for flag in _flag_values()]
    assert len(requests) >= 5 * len(NOUNS)
    failures = _built_legacy(bindings, harness, requests)
    assert not failures, '\n'.join(failures)


def test_composed_queries_are_canonical(bindings, harness):
    """The queries and typed parameters a noun builds for the nouns it runs in-process (its compositions) spell each
    control canonically: no note is printed for them today, and each legacy spelling is deleted at the cut, so a
    composed one would break the parent then."""
    failures = _built_legacy(bindings, harness, _answer_surfaces())
    assert not failures, '\n'.join(failures)


def test_the_collector_reads_hints_and_maps_placeholders():
    """The collector's controls: a quoted URI, a command cut at its prose, a template mapped onto the fixture."""
    text = ("Next: reveal 'ast://src/?kind=function&sort=-complexity'\n"
            "  reveal calls <path> --callers NAME - CLI subcommand form\n"
            "reveal hotspots is deprecated; use reveal metrics <path> --view hotspots (files)\n")
    found = _found_in(text)
    assert 'ast://src/?kind=function&sort=-complexity' in found
    assert 'reveal calls <path> --callers NAME' in found
    assert _argv('reveal calls <path> --callers NAME') == ['calls', 'proj', '--callers', 'main']
    assert _argv('reveal hotspots is deprecated') is None
    assert _argv('ast://src/?depth>N') == ['ast://proj?depth>2']
    assert _argv('claude://session/NAME/messages?limit=3') == ['claude://session/infernal-earth-0118/messages?limit=3']


def test_the_judge_bites(harness):
    """Positive controls: a legacy spelling and a rejected key are problems; a canonical spelling is not."""
    # (a standalone legacy row keeps its own note; a covered one is the URI request's note, which is no fault, BACK-2716)
    assert any('note:' in p for p in _problems(harness, ['ast://proj?calls=helper'], 'test'))
    assert _problems(harness, ['ast://proj?type=function'], 'test') == []
    assert any('invalid request' in p for p in _problems(harness, ['metrics://proj?bogus=1'], 'test'))
    assert _problems(harness, ['ast://proj?kind=function'], 'test') == []
    # the generated family: a bare shared-control key on an open-field noun notes where=
    # (that note is now the URI request's one note, which names --where; it is no printed-spelling fault, BACK-2716)
    assert _problems(harness, ['ast://proj?depth>1'], 'test') == []
    _, out, _, _ = harness.run_subcommand(*_json_argv(['ast://proj?depth>1']))
    assert any(is_request_note(w) and '--where' in w['message'] for w in json.loads(out)['meta']['warnings'])
    # a retired scheme's own help may name it; another surface may not
    assert _problems(harness, ['deps://proj'], 'help://deps') == []
    assert _problems(harness, ['deps://proj'], 'overview://proj')
