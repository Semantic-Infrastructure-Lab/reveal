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
    (INPUTS/BUILTINS/EFFECTS) but labels each inputs row."""
    path = copies['python']
    inputs, boundary = _inputs_and_boundary(path, [])
    assert [f['var'] for f in inputs['findings']] != [f['var'] for f in boundary['findings'][:18]]
    inputs_text = run(path, 'process_order', '--inputs').stdout
    boundary_text = run(path, 'process_order', '--boundary').stdout
    assert inputs_text.splitlines()[0].split()[:2] == ['PARAM', 'order']
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
