"""calls:// names a file tree-sitter read only through error recovery, and the answer is incomplete (BACK-2658).

COMMAND_MODEL 'Degraded input': a file the parser read only with error recovery is partial input on
every noun, named in meta.warnings with exit 3. ast://, metrics:// and imports:// already exited 3 on
these files; calls:// exited 0 and named nothing, although its index reads AST's own structures, which
carry the flag. Recovery can swallow whole regions (BACK-756), so a clean exit 0 could be a short caller
list, and an empty answer is not proof that a name is undefined.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

# One definition of b, two callers c and d, and a function whose signature tree-sitter has to recover.
FIXTURES = {
    'py': {
        'a.py': 'def b():\n    return 1\n',
        'b.py': 'from a import b\n\n\ndef c():\n    return b()\n\n\n{broken}def d():\n    return b()\n',
        'broken': 'def broken(:\n    pass\n\n\n',
    },
    'c': {
        'a.c': 'int b(void) { return 1; }\n',
        'a.h': 'int b(void);\n',
        'b.c': '#include "a.h"\nint c(void) { return b(); }\n{broken}int d(void) { return b(); }\n',
        'broken': 'int broken(int x { return x; }\n',
    },
    'ts': {
        'a.ts': 'export function b(): number { return 1; }\n',
        'b.ts': 'import { b } from "./a";\nexport function c(): number { return b(); }\n'
                '{broken}export function d(): number { return b(); }\n',
        'broken': 'export function broken(x: number { return x; }\n',
    },
}


def _tree(tmp_path, lang, *, broken):
    spec = FIXTURES[lang]
    root = tmp_path / lang
    root.mkdir(parents=True)
    for name, text in spec.items():
        if name != 'broken':
            (root / name).write_text(text.replace('{broken}', spec['broken'] if broken else ''), encoding='utf-8')
    return root


def _calls(root, query):
    result = _run_reveal_direct(f'calls://{root.as_posix()}?{query}', '--format', 'json')
    return result.returncode, json.loads(result.stdout), result


def _warnings(answer, kind):
    return [w for w in answer['meta']['warnings'] if w.get('type') == kind]


@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_callers_names_the_recovered_file_and_exits_3(tmp_path, lang):
    root = _tree(tmp_path, lang, broken=True)
    code, answer, result = _calls(root, 'callers=b')
    (recovered,) = _warnings(answer, 'parse_recovered')
    assert recovered['files'] == [f'{root.as_posix()}/b.{lang}'] and recovered['count'] == 1
    assert _warnings(answer, 'analysis_incomplete')
    assert code == 3, result.stderr[-500:]
    # The callers tree-sitter did recover are still listed: a lower bound, not a failure.
    assert sorted(c['caller'] for level in answer['levels'] for c in level['callers']) == ['c', 'd']


@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_clean_sibling_still_exits_0_without_the_warning(tmp_path, lang):
    root = _tree(tmp_path, lang, broken=False)
    code, answer, result = _calls(root, 'callers=b')
    assert code == 0, result.stderr[-500:]
    assert not _warnings(answer, 'parse_recovered') and not _warnings(answer, 'analysis_incomplete')
    assert sorted(c['caller'] for level in answer['levels'] for c in level['callers']) == ['c', 'd']


@pytest.mark.parametrize('query', ['callees=c', 'callers=b&depth=2', 'sort=-callers', 'uncalled'])
def test_every_index_mode_discloses_it(tmp_path, query):
    # The forward source (callees), the deeper callers walk, ranking and uncalled each build their
    # answer from the same collection; C has no Python reference parse to disclose it another way.
    root = _tree(tmp_path, 'c', broken=True)
    code, answer, result = _calls(root, query)
    assert [w['files'] for w in _warnings(answer, 'parse_recovered')] == [[f'{root.as_posix()}/b.c']]
    assert code == 3, result.stderr[-500:]


@pytest.mark.parametrize('lang', ['c', 'py'])
def test_undefined_name_is_not_claimed_absent_when_a_file_was_recovered(tmp_path, lang):
    clean = _tree(tmp_path / 'clean', lang, broken=False)
    code, answer, _ = _calls(clean, 'callers=no_such_name')
    assert code == 2 and answer.get('error')  # control: a complete tree may say the name is undefined
    broken = _tree(tmp_path / 'broken', lang, broken=True)
    code, answer, result = _calls(broken, 'callers=no_such_name')
    # A recovered region may hold the definition (BACK-756): an empty, incomplete answer, not "not found".
    assert code == 3, result.stderr[-500:]
    assert not answer.get('error') and _warnings(answer, 'parse_recovered')


def test_a_cached_index_still_names_the_file(tmp_path):
    from reveal.api import query

    root = _tree(tmp_path, 'c', broken=True)
    uri = f'calls://{root.as_posix()}?callers=b'
    first, second = query(uri), query(uri)  # the second request revalidates and reuses the index
    for answer in (first, second):
        assert [w['files'] for w in _warnings(answer, 'parse_recovered')] == [[f'{root.as_posix()}/b.c']]


def test_text_output_names_the_file(tmp_path):
    root = _tree(tmp_path, 'c', broken=True)
    result = _run_reveal_direct(f'calls://{root.as_posix()}?callers=b')
    assert result.returncode == 3
    assert 'could not read' in result.stdout + result.stderr and 'b.c' in result.stdout + result.stderr


def test_modules_shim_keeps_its_exit_code_and_disclosure(tmp_path):
    # BACK-2181 (Q8): the retired ?modules shim keeps exit 0 until the cut; it already names the file.
    root = _tree(tmp_path, 'c', broken=True)
    code, answer, result = _calls(root, 'modules')
    assert code == 0, result.stderr[-500:]
    assert _warnings(answer, 'partial_parse') and not _warnings(answer, 'parse_recovered')
