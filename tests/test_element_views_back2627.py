"""BACK-2627: element views -- what must not change while their spelling moves to ``--view``.

Preservation pins. Every element view reveal answers today, on every fixture language of the conformance matrix plus
TSX, for a named element, a line range and the whole file (flat), keeps its complete answer: the JSON answer (findings,
meta and warnings; the envelope is checked in code) and the text stdout, both as digests in
``tests/fixtures/element_views_back2627/<language>.json`` with the finding rows spelled out so a change reads as a diff.
An intended change is accepted by regenerating and reviewing the diff like code::

    REVEAL_UPDATE_GOLDEN=1 pytest tests/test_element_views_back2627.py -k complete_answer

A case may hold more than one accepted answer when tree-sitter-language-pack releases parse its fixture differently
(Zig does; ``REVEAL_UPDATE_GOLDEN=variant`` run on each interpreter adds a release's answer, tagged ``pack``).

A retirement note is the designed difference of a legacy spelling, so it is set aside: these pins stay green when the
current flags start noting their ``--view`` replacement. Cases a ruled bug fix changes on purpose are not pinned here
(their REDs are): ``--narrow`` on an unannotated variable (E2: the decline moves into JSON), a variable view on an
element where the variable is absent (E1, rule 9), ``--inputs`` text (E16), and the depth a fix adds to boundary's
transitive JSON (E8).
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

import pytest

from conftest import _run_reveal_direct as run, without_retirement_notes
from test_conformance_matrix import EXPECTED, EXTENSIONS

pytestmark = pytest.mark.conformance

GOLDEN_DIR = Path(__file__).parent / 'fixtures' / 'element_views_back2627'
UPDATE = {'1': 'replace', 'variant': 'variant'}.get(os.environ.get('REVEAL_UPDATE_GOLDEN', ''))  # see _write_golden
LANGUAGES = [*sorted(EXPECTED), 'tsx']

# Every current element view, in its current canonical spelling. ``{var}`` is the language's probe variable.
VIEWS = {
    'boundary': ['--boundary'],
    'boundary-transitive': ['--boundary', '--transitive'],
    'inputs': ['--inputs'],
    'outputs': ['--outputs'],
    'callsites': ['--callsites'],
    'effects': ['--effects'],
    'effects-transitive': ['--effects', '--transitive'],
    'effects-loops': ['--effects', '--in-loops'],
    'effects-state': ['--effects', '--state'],
    'flow': ['--flow'],
    'flow-if': ['--flow=if'],
    'flow-loop': ['--flow=loop'],
    'flow-try': ['--flow=try'],
    'flow-if-try': ['--flow=if,try'],
    'exits': ['--exits'],
    'varflow': ['--varflow', '{var}'],
    'cross-calls': ['--varflow', '{var}', '--cross-calls'],
    'keys': ['--keys', '{var}'],
}
VARIABLE_VIEWS = {'varflow', 'cross-calls', 'keys'}
# The loop/state answers are empty on most entry functions; each fixture's loop element carries them.
LOOP_ELEMENT_VIEWS = {'effects-loops', 'effects-state', 'flow-loop'}
TEXT_UNPINNED = {'inputs'}  # E16: the text labels every non-builtin input PARAM; its fix changes this text


def target(language):
    """(checkout path, entry element, probe range, probe variable, loop element or None) of a fixture language."""
    if language == 'tsx':
        return 'tests/fixtures/smoke/tsx/sample.tsx', 'processOrder', '13-13', 'count', None
    expected = EXPECTED[language]
    probe = expected['mutations_probe']
    path = f'tests/fixtures/conformance/{language}/sample.{EXTENSIONS[language]}'
    return path, expected['entry_function'], probe['range'], probe['var'], expected.get('batch_element')


@pytest.fixture(scope='module')
def copies(tmp_path_factory):
    """language -> a private copy of its fixture. Transitive views walk the project root, which from the checkout
    is the whole repository (its answers would follow unrelated files); each copy is a project of one file."""
    found = {}
    for language in LANGUAGES:
        checkout = Path(__file__).resolve().parent.parent / target(language)[0]
        copy = tmp_path_factory.mktemp(language) / checkout.name
        copy.write_bytes(checkout.read_bytes())
        found[language] = copy.as_posix()
    return found


def cases(language):
    """case id -> argv after the path. Variable views run where the variable occurs (the probe range is its write)."""
    _, element, selected, var, loop_element = target(language)
    found = {}
    for view, flags in VIEWS.items():
        flags = [flag.replace('{var}', var) for flag in flags]
        found[f'{view}/named'] = [element, *flags]
        found[f'{view}/range'] = [':' + selected, *flags]
        found[f'{view}/flat'] = flags
        if view in LOOP_ELEMENT_VIEWS and loop_element:
            found[f'{view}/loop-element'] = [loop_element, *flags]
    line = ':' + selected.split('-')[0]
    found['scope/line'] = [line, '--scope']
    found['around/line'] = [line, '--around', '2']
    return found


def _portable(value, path):
    """*value* with the copy's directory spelled ``<DIR>`` (both separators) and no carriage returns: smoke fixtures
    carry no eol attribute, so a Windows checkout may hand the parser CRLF text."""
    if isinstance(value, str):
        folder = PurePosixPath(path).parent.as_posix()  # *path* is a copy's as_posix() spelling
        for spelling in (folder, folder.replace('/', '\\')):
            value = value.replace(spelling, '<DIR>')
        return value.replace('\r', '')
    if isinstance(value, list):
        return [_portable(item, path) for item in value]
    if isinstance(value, dict):
        return {key: _portable(item, path) for key, item in value.items()}
    return value


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()[:16]


def _row(finding) -> str:
    tag = next((str(finding[key]) for key in ('kind', 'keyword', 'key', 'function', 'callee') if key in finding), 'line')
    line = next((finding[key] for key in ('line', 'line_start', 'from_line') if key in finding), '?')
    return f'{tag}:{line}'


def answer_body(stdout, path, case):
    """The JSON answer without its envelope constants (asserted here) and without retirement notes."""
    from reveal.utils.path_utils import to_posix

    answer = without_retirement_notes(json.loads(stdout))
    assert answer['type'] == 'element_view' and answer['source_type'] == 'file', case
    assert to_posix(answer['source']) == path and to_posix(answer['meta']['file']) == path, case
    meta = {key: value for key, value in answer['meta'].items() if key != 'file'}
    if case.startswith('boundary-transitive/'):
        meta = {key: value for key, value in meta.items() if 'depth' not in key}  # E8 adds the effective depth
    body = {key: value for key, value in answer.items()
            if key not in ('contract_version', 'type', 'source', 'source_type', 'meta')}
    return _portable({**body, 'meta': meta}, path)


def pin(path, case, argv):
    """What one case answers: exit, finding rows and digests of the JSON body and the text stdout."""
    as_json = run(path, *argv, '--format', 'json')
    assert as_json.returncode == 0, (case, as_json.stderr)
    body = answer_body(as_json.stdout, path, case)
    entry = {'exit': as_json.returncode, 'rows': [_row(f) for f in body.get('findings', [])], 'json': _digest(body)}
    if case.split('/')[0] not in TEXT_UNPINNED:
        text = run(path, *argv)
        assert text.returncode == 0, (case, text.stderr)
        entry['text'] = _digest(_portable(text.stdout, path))
    return entry


def _pack_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version('tree-sitter-language-pack')
    except PackageNotFoundError:
        return 'none'


def _accepts(variants, entry) -> bool:
    return any({key: value for key, value in variant.items() if key != 'pack'} == entry for variant in variants)


def _write_golden(file, answers, previous):
    """``REVEAL_UPDATE_GOLDEN=1`` records this run's answers as the only accepted ones; ``=variant`` adds each answer
    the file does not accept yet as another accepted variant, tagged with this run's language-pack version (a
    grammar release can parse a fixture differently: Zig, measured between pack 1.25.0 and 1.23.1/1.22.1/1.8.1)."""
    if UPDATE == 'variant':
        answers = {case: previous.get(case, []) + ([] if _accepts(previous.get(case, []), entry) else
                                                   [{**entry, 'pack': _pack_version()}])
                   for case, entry in answers.items()}
    else:
        answers = {case: [entry] for case, entry in answers.items()}
    lines = [f'  {json.dumps(case)}: {json.dumps(entry, sort_keys=True)}' for case, entry in answers.items()]
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('{\n' + ',\n'.join(lines) + '\n}\n', encoding='utf-8')


@pytest.mark.parametrize('language', LANGUAGES)
def test_every_view_keeps_its_complete_answer(copies, language):
    path = copies[language]
    answers = {case: pin(path, case, argv) for case, argv in cases(language).items()}
    golden = GOLDEN_DIR / f'{language}.json'
    if UPDATE:
        _write_golden(golden, answers, json.loads(golden.read_text(encoding='utf-8')) if golden.exists() else {})
        return
    assert golden.exists(), f'missing {golden.name}: run with REVEAL_UPDATE_GOLDEN=1'
    expected = json.loads(golden.read_text(encoding='utf-8'))
    assert sorted(answers) == sorted(expected)
    changed = {case: {'accepted': expected[case], 'now': answers[case]}
               for case in answers if not _accepts(expected[case], answers[case])}
    if changed:
        case = next(iter(changed))
        current = run(path, *cases(language)[case], '--format', 'json').stdout
        pytest.fail(f'{len(changed)} element-view answers changed on tree-sitter-language-pack {_pack_version()} '
                    '(accept with REVEAL_UPDATE_GOLDEN=1 after review):\n'
                    + json.dumps(changed, indent=1) + f'\nfirst changed case {case} answers now:\n{current}')


def test_every_pin_is_a_real_answer():
    """The pins are not a matrix of empty answers: each view finds rows somewhere, and the loop views on the loop
    element (in-loops is empty on most entry functions)."""
    found = {}
    for language in LANGUAGES:
        golden = json.loads((GOLDEN_DIR / f'{language}.json').read_text(encoding='utf-8'))
        for case, variants in golden.items():
            found.setdefault(case.split('/')[0], 0)
            found[case.split('/')[0]] += all(variant['rows'] for variant in variants)
    assert all(found.values()), {view: count for view, count in found.items() if not count}
    assert set(found) == {*VIEWS, 'scope', 'around'}


# -- X8: --inputs and boundary's inputs are not the same answer ---------------------------------------------------

def _inputs_and_boundary(path, positionals):
    inputs = json.loads(run(path, *positionals, '--inputs', '--format', 'json').stdout)
    boundary = json.loads(run(path, *positionals, '--boundary', '--format', 'json').stdout)
    return inputs, boundary


@pytest.mark.parametrize('mode', ['named', 'flat'])
@pytest.mark.parametrize('language', LANGUAGES)
def test_inputs_differs_from_boundary_inputs_exactly_so(copies, language, mode):
    """The difference a ``--view boundary`` note for ``--inputs`` would have to erase (X8; ruled at S3b): the same
    variables, but ``meta.flag`` inputs, ``kind`` dep for boundary's input, a ``first_write_line`` key on builtins
    that boundary omits, every row in line order where boundary lists inputs before builtins, and none of
    boundary's effect rows."""
    inputs, boundary = _inputs_and_boundary(copies[language], [target(language)[1]] if mode == 'named' else [])
    assert (inputs['meta']['flag'], boundary['meta']['flag']) == ('inputs', 'boundary')
    assert {f['kind'] for f in inputs['findings']} <= {'dep', 'builtin'}
    assert all('first_write_line' in f for f in inputs['findings'])
    reads = [f for f in boundary['findings'] if f['kind'] in ('input', 'builtin', 'superglobal')]
    assert all('first_write_line' not in f for f in reads if f['kind'] == 'builtin')

    def as_boundary(finding):
        finding = {**finding, 'kind': 'input' if finding['kind'] == 'dep' else finding['kind']}
        if finding['kind'] == 'builtin':
            finding.pop('first_write_line')
        return finding

    key = lambda f: (f['line'], f['var'], f['kind'])  # noqa: E731
    assert sorted(map(as_boundary, inputs['findings']), key=key) == sorted(reads, key=key)
    assert [f['line'] for f in inputs['findings']] == sorted(f['line'] for f in inputs['findings'])
    kinds = [f['kind'] for f in reads]
    assert kinds == sorted(kinds, key=lambda kind: kind == 'builtin')  # inputs, then builtins
    assert len(boundary['findings']) - len(reads) == sum(f['kind'] not in ('input', 'builtin', 'superglobal')
                                                       for f in boundary['findings'])


def test_inputs_and_boundary_differ_in_row_order_and_text_sections(copies):
    """Measured on Python's whole file: the same 18 reads in a different order, and text that sections boundary
    (INPUTS/BUILTINS/EFFECTS) but labels each inputs row (INPUT/BUILTIN since E16; PARAM before)."""
    path = copies['python']
    inputs, boundary = _inputs_and_boundary(path, [])
    assert [f['var'] for f in inputs['findings']] != [f['var'] for f in boundary['findings'][:18]]
    inputs_text = run(path, 'process_order', '--inputs').stdout
    boundary_text = run(path, 'process_order', '--boundary').stdout
    assert inputs_text.splitlines()[0].split()[:2] == ['INPUT', 'order']
    assert [line for line in boundary_text.splitlines() if line and not line.startswith(' ')] == [
        'INPUTS (undefined reads):', 'BUILTINS:', 'EFFECTS:']


# -- current answers of the views whose new home waits on Scott (X5 vars, X6 callsites, X7 outputs) ---------------

@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'sample.py'
    path.write_text('def handle(value: int | str | None, items):\n'
                    '    total = len(items)\n'
                    '    config = {"k": total}\n'
                    '    if value is None:\n'
                    '        return config["k"]\n'
                    '    if isinstance(value, str):\n'
                    '        return send(value, config.get("k"))\n'
                    '    return value + total\n', encoding='utf-8')
    return path.as_posix()


def _json(*argv):
    response = run(*argv, '--format', 'json')
    assert response.returncode == 0, response.stderr
    return json.loads(response.stdout)


def test_narrow_on_an_annotated_variable(source):
    answer = _json(source, 'handle', '--narrow', 'value')
    assert answer['meta']['flag'] == 'narrow' and answer['meta']['var'] == 'value'
    assert answer['meta']['warnings'] == []
    assert answer['findings'] == [
        {'kind': 'ENTRY', 'line': 1, 'type_set': ['None', 'int', 'str'], 'depth': 0},
        {'kind': 'IF', 'line': 4, 'type_set': ['None'], 'depth': 0},
        {'kind': 'NARROW', 'line': 6, 'type_set': ['int', 'str'], 'depth': 0},
        {'kind': 'IF', 'line': 6, 'type_set': ['str'], 'depth': 0},
        {'kind': 'NARROW', 'line': 8, 'type_set': ['int'], 'depth': 0},
    ]


def test_keys_varflow_and_cross_calls_answers(source):
    keys = _json(source, 'handle', '--keys', 'config')
    assert keys['meta']['flag'] == 'keys'
    assert keys['findings'] == [{'key': 'k', 'kind': 'READ', 'line': 5, 'access': 'subscript'},
                                {'key': 'k', 'kind': 'READ', 'line': 7, 'access': 'call'}]  # the literal's key is no access
    flow = _json(source, 'handle', '--varflow', 'total')
    events = [{'kind': 'WRITE', 'line': 2}, {'kind': 'READ', 'line': 3}, {'kind': 'READ', 'line': 8}]
    assert flow['meta']['flag'] == 'varflow' and flow['findings'] == events
    frames = _json(source, 'handle', '--varflow', 'total', '--cross-calls')
    assert frames['meta']['flag'] == 'cross_varflow'
    assert frames['findings'] == [{'depth': 0, 'function': 'handle', 'var': 'total', 'from_line': 1, 'to_line': 8,
                                   'events': events, 'callouts': []}]


def test_present_variable_with_no_key_access_is_a_genuine_zero(source):
    answer = _json(source, 'handle', '--keys', 'total')
    assert answer['findings'] == [] and answer['meta']['var'] == 'total'


def test_callsites_and_outputs_answers(source):
    sites = [{'line': 2, 'callee': 'len', 'first_arg': 'items', 'has_more_args': False},
             {'line': 6, 'callee': 'isinstance', 'first_arg': 'value', 'has_more_args': True},
             {'line': 7, 'callee': 'send', 'first_arg': 'value', 'has_more_args': True},
             {'line': 7, 'callee': 'config.get', 'first_arg': '"k"', 'has_more_args': False}]
    calls = _json(source, 'handle', '--callsites')
    assert calls['meta']['flag'] == 'callsites' and calls['findings'] == sites
    ranged = _json(source, 'handle', '--callsites', '7-7')
    assert (ranged['meta']['from_line'], ranged['meta']['to_line']) == (7, 7)
    assert ranged['findings'] == sites[2:]
    assert _json(source, 'handle', '--outputs')['findings'] == []  # empty over a whole function, by design
    assert _json(source, ':2-3', '--outputs')['findings'] == [
        {'kind': 'mutation', 'var': 'total', 'line': 2, 'next_read_line': 8},
        {'kind': 'mutation', 'var': 'config', 'line': 3, 'next_read_line': 5}]


# =================================================================================================================
# REDs (step 2b). Each asserts the ruled answer through an existing entry point (CLI, MCP reveal_nav, MCP reveal_run)
# and fails on the current code; the test after it is an unaffected sibling that passes. Rulings: geteno-1121 X1-X15
# (rule 9 = plan section 5 rule 9; D6 = one exit contract; Applicability / One answer per request / Conflicting values
# = COMMAND_MODEL "Cross-noun rules").
# =================================================================================================================

ABSENT = 'no_such_var'


def _refused(response, *names):
    """An invalid request (D6): exit 2, no element-view answer, and the message names each of *names*."""
    said = response.stdout + response.stderr
    assert response.returncode == 2, (response.returncode, said[:400])
    assert '"element_view"' not in response.stdout, response.stdout[:400]
    for name in names:
        assert name in said, (name, said[:400])


def _tool_error(result, *names):
    from reveal.mcp_server import _ToolFailure
    assert isinstance(result, _ToolFailure), str(result)[:400]
    for name in names:
        assert name in result, (name, str(result)[:400])


def _tool_answer(result):
    from reveal.mcp_server import _ToolFailure
    assert not isinstance(result, _ToolFailure), str(result)[:400]
    return result


def _python(copies):
    return copies['python'], target('python')[1]


@pytest.fixture(scope='module')
def others(tmp_path_factory):
    """Files with no fixture in the checkout: an untested language (Elixir), a fallback grammar (R), a CSV and an
    office document (a minimal .docx)."""
    import zipfile

    folder = tmp_path_factory.mktemp('others')
    (folder / 'x.ex').write_text('defmodule Shop do\n  def process_order(order) do\n    result = validate(order)\n'
                                 '    File.write("orders.log", result)\n    result\n  end\nend\n', encoding='utf-8')
    (folder / 'x.r').write_text('process_order <- function(order) {\n  result <- validate(order)\n'
                                '  write(result, file = "orders.log")\n  result\n}\n', encoding='utf-8')
    (folder / 'x.csv').write_text('a,b\n1,2\n', encoding='utf-8')
    with zipfile.ZipFile(folder / 'x.docx', 'w') as document:
        document.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                          'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        document.writestr('word/document.xml', '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats'
                          '.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hi</w:t></w:r></w:p></w:body>'
                          '</w:document>')
    return {path.suffix: path.as_posix() for path in folder.iterdir()}


# -- E1, X14 (rule 9): a variable that matches nothing is not a zero -----------------------------------------------

@pytest.mark.parametrize('language', LANGUAGES)
def test_absent_variable_exits_2_naming_it_and_the_element(copies, language):
    element = target(language)[1]
    _refused(run(copies[language], element, '--varflow', ABSENT, '--format', 'json'), ABSENT, element)


@pytest.mark.parametrize('language', ['python', 'typescript', 'go'])
@pytest.mark.parametrize('view', [['--keys', ABSENT], ['--narrow', ABSENT], ['--varflow', ABSENT, '--cross-calls']],
                         ids=['keys', 'narrow', 'cross-calls'])
def test_absent_variable_exits_2_on_every_variable_view(copies, language, view):
    element = target(language)[1]
    _refused(run(copies[language], element, *view, '--format', 'json'), ABSENT, element)


@pytest.mark.parametrize('language', LANGUAGES)
def test_sibling_present_variable_answers(copies, language):
    _, element, _, var, _ = target(language)
    response = run(copies[language], element, '--varflow', var, '--format', 'json')
    assert response.returncode == 0 and json.loads(response.stdout)['findings']


def test_absent_variable_is_a_tool_error_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    path, element = _python(copies)
    _tool_error(reveal_nav(path, element, 'varflow', ABSENT), ABSENT)
    _tool_error(reveal_run([path, element, '--varflow', ABSENT, '--format', 'json']), ABSENT)


def test_sibling_present_variable_answers_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    path, element = _python(copies)
    assert 'WRITE' in _tool_answer(reveal_nav(path, element, 'varflow', 'result'))
    assert json.loads(_tool_answer(reveal_run([path, element, '--varflow', 'result', '--format', 'json'])))['findings']


# -- E3, X14 (rule 9): a line range outside the file, or reversed, matches nothing ---------------------------------

NOWHERE = [
    pytest.param([':900-950', '--boundary'], ('900',), id='range-past-end'),
    pytest.param([':30-10', '--boundary'], ('30', '10'), id='range-reversed'),
    pytest.param(['{element}', '--boundary', '--range', '900-950'], ('900',), id='element-range-past-end'),
    pytest.param(['{element}', '--callsites', '900-950'], ('900',), id='callsites-range-past-end'),
    pytest.param([':900-950', '--exits'], ('900',), id='exits'),
    pytest.param([':900-950', '--flow'], ('900',), id='flow'),
    pytest.param([':900-950', '--effects'], ('900',), id='effects'),
    pytest.param([':900-950', '--inputs'], ('900',), id='inputs'),
]


@pytest.mark.parametrize('argv,names', NOWHERE)
def test_lines_that_match_nothing_exit_2(copies, argv, names):
    path, element = _python(copies)
    _refused(run(path, *[word.replace('{element}', element) for word in argv], '--format', 'json'), *names)


@pytest.mark.parametrize('argv', [[':13-13', '--boundary'], ['process_order', '--boundary', '--range', '13-14'],
                                  ['process_order', '--callsites', '13-14'], [':40-49', '--exits']])
def test_sibling_lines_inside_the_file_answer(copies, argv):
    response = run(copies['python'], *argv, '--format', 'json')
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout)['type'] == 'element_view'


def test_lines_that_match_nothing_are_a_tool_error_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    path = copies['python']
    _tool_error(reveal_nav(path, ':900-950', 'boundary'), '900')
    _tool_error(reveal_run([path, ':900-950', '--boundary', '--format', 'json']), '900')
    _tool_answer(reveal_nav(path, ':13-13', 'boundary'))  # sibling


# -- E2, X14: narrow on an unannotated variable is a decline the JSON carries ---------------------------------------

def test_narrow_decline_is_a_json_warning_with_the_text_sentence(copies):
    path, element = _python(copies)
    sentence = "No annotation for 'order' — cannot narrow"
    assert run(path, element, '--narrow', 'order').stdout.strip() == sentence  # the text says it today
    response = run(path, element, '--narrow', 'order', '--format', 'json')
    assert response.returncode == 0
    answer = json.loads(response.stdout)
    assert answer['findings'] == []
    assert any(sentence in warning.get('message', '') for warning in answer['meta']['warnings']), answer['meta']


def test_narrow_decline_is_a_json_warning_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    path, element = _python(copies)
    answer = json.loads(_tool_answer(reveal_run([path, element, '--narrow', 'order', '--format', 'json'])))
    assert any("No annotation for 'order'" in warning.get('message', '') for warning in answer['meta']['warnings'])


# (sibling: test_narrow_on_an_annotated_variable above -- an annotated variable narrows with no warning)


# -- E4: a callsites range that is not a range ---------------------------------------------------------------------

@pytest.mark.parametrize('spelling', [['--callsites', 'abc'], ['--callsites=abc']])
def test_callsites_garbage_range_exits_2_naming_it(copies, spelling):
    path, element = _python(copies)
    _refused(run(path, element, *spelling, '--format', 'json'), 'abc')


def test_sibling_callsites_range_selects_lines(copies):
    path, element = _python(copies)
    answer = json.loads(run(path, element, '--callsites', '13-14', '--format', 'json').stdout)
    assert (answer['meta']['from_line'], answer['meta']['to_line']) == (13, 14)


def test_callsites_garbage_range_is_a_tool_error_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    path, element = _python(copies)
    _tool_error(reveal_nav(path, element, 'callsites', 'abc'), 'abc')
    _tool_error(reveal_run([path, element, '--callsites', 'abc', '--format', 'json']), 'abc')
    _tool_answer(reveal_nav(path, element, 'callsites', '13-14'))  # sibling


# -- E5: an empty variable name ------------------------------------------------------------------------------------

@pytest.mark.parametrize('view', ['varflow', 'keys', 'narrow'])
def test_empty_variable_name_exits_2_naming_the_view(copies, view):
    path, element = _python(copies)
    _refused(run(path, element, '--' + view, '', '--format', 'json'), view)


def test_empty_variable_name_is_a_tool_error_on_reveal_run(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    path, element = _python(copies)
    _tool_error(reveal_run([path, element, '--varflow', '', '--format', 'json']), 'varflow')


@pytest.mark.parametrize('view', ['varflow', 'keys', 'narrow'])
def test_sibling_reveal_nav_already_refuses_an_empty_variable_name(copies, view):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav
    path, element = _python(copies)
    _tool_error(reveal_nav(path, element, view, ''), view)


# -- E8: the transitive depth stated is the depth used -------------------------------------------------------------

def _depth_values(meta):
    return [value for key, value in meta.items() if 'depth' in key]


def test_boundary_transitive_states_the_clamped_depth(copies):
    path, element = _python(copies)
    text = run(path, element, '--boundary', '--transitive', '--depth', '9').stdout
    assert 'depth=9' not in text and 'depth=5' in text, [line for line in text.splitlines() if 'depth' in line]
    answer = json.loads(run(path, element, '--boundary', '--transitive', '--depth', '9', '--format', 'json').stdout)
    assert _depth_values(answer['meta']) == [5], answer['meta']


def test_boundary_transitive_json_states_the_default_depth_for_zero(copies):
    path, element = _python(copies)
    answer = json.loads(run(path, element, '--boundary', '--transitive', '--depth', '0', '--format', 'json').stdout)
    assert _depth_values(answer['meta']) == [2], answer['meta']


@pytest.mark.parametrize('given,stated', [('3', '3'), ('0', '2')])
def test_sibling_boundary_transitive_text_states_depths_up_to_five(copies, given, stated):
    path, element = _python(copies)
    assert f'depth={stated}' in run(path, element, '--boundary', '--transitive', '--depth', given).stdout


# -- E9, X15: invalid requests exit 2, not 1 (D6) -----------------------------------------------------------------

@pytest.mark.parametrize('fixture', ['formats/ini/sample.ini', 'formats/xml/pom.xml', 'formats/jsonl/sample.jsonl',
                                     'formats/nginx/nginx.conf', 'xlsx/dynamic_arrays.xlsx'])
def test_files_without_tree_sitter_analysis_exit_2(fixture):
    _refused(run(f'tests/fixtures/{fixture}', '--boundary', '--format', 'json'))


@pytest.mark.parametrize('suffix', ['.csv', '.docx'])
def test_csv_and_office_documents_exit_2(others, suffix):
    _refused(run(others[suffix], '--boundary', '--format', 'json'))


@pytest.mark.parametrize('argv,names', [
    pytest.param(['{element}', '--scope'], ('scope',), id='scope-named-element'),
    pytest.param(['--around', '3'], ('around',), id='around-without-line'),
    pytest.param(['{element}', '--boundary', '--range', 'abc'], ('abc',), id='range-not-a-range'),
])
def test_requests_missing_or_malformed_lines_exit_2(copies, argv, names):
    path, element = _python(copies)
    _refused(run(path, *[word.replace('{element}', element) for word in argv], '--format', 'json'), *names)


def test_sibling_structure_only_language_and_line_views_answer_as_today(copies):
    assert run('tests/fixtures/formats/sql/sample.sql', '--boundary').returncode == 2
    for flags in (['--scope'], ['--around', '3']):
        response = run(copies['python'], ':13', *flags, '--format', 'json')
        assert response.returncode == 0 and json.loads(response.stdout)['findings']


# -- E10: negative context lines -----------------------------------------------------------------------------------

def test_negative_around_exits_2(copies):
    _refused(run(copies['python'], ':13', '--around', '-1', '--format', 'json'), 'around')


def test_sibling_zero_around_is_the_target_line(copies):
    answer = json.loads(run(copies['python'], ':13', '--around', '0', '--format', 'json').stdout)
    assert [(f['line'], f['is_target']) for f in answer['findings']] == [(13, True)]


def test_negative_around_is_a_tool_error_on_mcp(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav
    _tool_error(reveal_nav(copies['python'], ':13', 'around', '-1'), 'around')
    _tool_answer(reveal_nav(copies['python'], ':13', 'around', '0'))  # sibling


# -- E11, X15: formats the views do not apply to decline; untested languages name their tier ----------------------

DATA_FORMATS = ['formats/markdown/sample.md', 'formats/json/sample.json', 'formats/yaml/sample.yaml',
                'formats/toml/pyproject.toml', 'formats/graphql/sample.graphql', 'formats/protobuf/sample.proto']


@pytest.mark.parametrize('view', [['--boundary'], ['--flow'], ['--varflow', 'name']], ids=['boundary', 'flow', 'varflow'])
@pytest.mark.parametrize('fixture', DATA_FORMATS, ids=lambda fixture: fixture.rsplit('.', 1)[1])
def test_data_formats_decline_with_exit_2(fixture, view):
    _refused(run(f'tests/fixtures/{fixture}', *view, '--format', 'json'))


def test_data_format_decline_is_a_tool_error_on_mcp():
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    _tool_error(reveal_run(['tests/fixtures/formats/markdown/sample.md', '--boundary', '--format', 'json']))
    _tool_error(reveal_nav('tests/fixtures/formats/markdown/sample.md', ':1-5', 'boundary'))
    _tool_error(reveal_nav('tests/fixtures/formats/sql/sample.sql', ':1-5', 'boundary'))  # sibling: structure-only


TIER_VIEWS = [['--boundary'], ['--inputs'], ['--outputs'], ['--callsites'], ['--effects'], ['--flow'], ['--exits'],
              ['--varflow', 'result']]


def _warnings(response):
    assert response.returncode == 0, response.stderr
    return [w for w in json.loads(response.stdout)['meta']['warnings'] if w.get('type') != 'retired_spelling']


TIER_CASES = [pytest.param(suffix, view, id=f'{name}-{view[0][2:]}')
              for suffix, name in (('.ex', 'elixir-untested'), ('.r', 'r-fallback')) for view in TIER_VIEWS
              if (suffix, view[0]) != ('.ex', '--varflow')]  # Elixir varflow names its tier today: the sibling below


@pytest.mark.parametrize('suffix,view', TIER_CASES)
def test_untested_languages_answer_with_one_tier_warning_on_every_view(others, suffix, view):
    warnings = _warnings(run(others[suffix], *view, '--format', 'json'))
    assert len(warnings) == 1, warnings


def test_sibling_elixir_varflow_names_its_tier_and_verified_languages_carry_none(others, copies):
    assert len(_warnings(run(others['.ex'], '--varflow', 'result', '--format', 'json'))) == 1
    path, element = _python(copies)
    for view in TIER_VIEWS:
        argv = [element, *view]
        assert _warnings(run(path, *argv, '--format', 'json')) == [], view


# -- E12: a format the view cannot render is not silently text -----------------------------------------------------

UNRENDERED = [['--boundary'], ['--boundary', '--transitive'], ['--inputs'], ['--outputs'], ['--callsites'],
              ['--effects'], ['--effects', '--in-loops'], ['--effects', '--state'], ['--varflow', 'result'],
              ['--keys', 'result']]


@pytest.mark.parametrize('form', ['grep', 'typed'])
@pytest.mark.parametrize('view', UNRENDERED, ids=lambda view: '-'.join(word.strip('-') for word in view))
def test_grep_and_typed_are_not_silently_text(copies, view, form):
    path, element = _python(copies)
    text = run(path, element, *view)
    other = run(path, element, *view, '--format', form)
    assert not (other.returncode == 0 and other.stdout == text.stdout), f'--format {form} printed the text answer'


@pytest.mark.parametrize('form', ['grep', 'typed'])
@pytest.mark.parametrize('view', ['--flow', '--exits'])
def test_sibling_flow_and_exits_refuse_grep_and_typed(copies, view, form):
    path, element = _python(copies)
    _refused(run(path, element, view, '--format', form), form)


# -- E16: the inputs text labels a function and a module PARAM ------------------------------------------------------

def _labels(path, element):
    return {line.split()[1]: line.split()[0] for line in run(path, element, '--inputs').stdout.splitlines() if line}


def test_inputs_text_does_not_call_a_function_or_module_a_parameter(copies):
    path, element = _python(copies)
    labels = _labels(path, element)
    assert labels['validate'] != 'PARAM' and labels['os'] != 'PARAM', labels


def test_sibling_inputs_text_labels_builtins_and_json_says_dep(copies):
    path, element = _python(copies)
    assert _labels(path, element)['open'] == 'BUILTIN'
    findings = json.loads(run(path, element, '--inputs', '--format', 'json').stdout)['findings']
    assert {f['var']: f['kind'] for f in findings}['validate'] == 'dep'


# -- shared owner (cli/parser.py validate_navigation_args): a bad --head/--tail/--range exits 2 on every path read ---

@pytest.mark.parametrize('argv', [['--range', 'abc'], ['--range', '20-10'], ['--head', '-1'], ['--tail', '-1'],
                                  ['--head', '2', '--tail', '2']], ids=lambda argv: ''.join(argv))
def test_invalid_path_read_slices_exit_2_like_the_nouns(copies, argv):
    """D6: an invalid invocation exits 2. The path read exited 1 here while ``reveal ast`` and ``ast://`` exit 2 for the
    same slice (tests/test_legacy_slice_flags_back2673.py); the code element and the file listing share the check."""
    for positionals in ([], ['process_order']):
        response = run(copies['python'], *positionals, *argv)
        assert response.returncode == 2, (positionals, response.stderr)


def test_sibling_valid_path_read_slices_answer(copies):
    for argv in (['--range', '1-2'], ['--head', '2'], ['--tail', '2']):  # --range counts outline items
        assert run(copies['python'], *argv).returncode == 0, argv


def test_decline_messages_spell_the_path_with_forward_slashes(monkeypatch):
    """The structure-only and not-code declines name the file as reveal spells paths everywhere (to_posix), so a
    Windows backslash path reads the same as the other nav diagnostics. Red control: a backslash spelling."""
    from reveal import file_handler
    from reveal.capabilities import get_capability_for_extension
    from reveal.errors import NavRequestValidationError

    class Analyzer:
        path = 'docs\\guide.md'

    for extension in ('.md', '.sql'):
        capability = get_capability_for_extension(extension)
        monkeypatch.setattr('reveal.capabilities.get_capability', lambda analyzer, found=capability: found)
        with pytest.raises(NavRequestValidationError) as raised:
            file_handler._validate_nav_request(Analyzer(), None, object())
        assert '`reveal docs/guide.md`' in str(raised.value), str(raised.value)
