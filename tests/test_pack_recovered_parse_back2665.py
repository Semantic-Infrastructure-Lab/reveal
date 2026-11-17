"""pack names a file it parsed only through tree-sitter error recovery, and the answer is incomplete (BACK-2665).

COMMAND_MODEL 'Degraded input': a file the parser read only with error recovery is partial input on
every noun, named in meta.warnings with exit 3. Pack parses files in two places: the import graph that
``--architecture`` (fan-in) and ``--focus`` (graph relevance) build over the whole path, and the
structure outline ``--content`` shows for each key file. Both read the recovered file and Pack exited 0;
the import build's finding reached only the free-text ``relevance_warning``, and the outline's own
"Parse recovered" note only the content string. A plain pack ranks by name, size and path and parses
no file, so it has nothing to disclose.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

# Key-directory files (core/) are shown as structure under --content; one function's signature is broken.
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

PARSING_MODES = {
    'architecture': ['--architecture'],
    'focus': ['--focus', 'core'],
    'content': ['--content'],
}


def _tree(tmp_path, lang, *, broken, subdir='core'):
    spec = FIXTURES[lang]
    root = tmp_path / lang
    (root / subdir).mkdir(parents=True)
    for name, text in spec.items():
        if name != 'broken':
            (root / subdir / name).write_text(text.replace('{broken}', spec['broken'] if broken else ''),
                                              encoding='utf-8')
    return root


def _pack(*args):
    result = _run_reveal_direct(*args, '--format', 'json')
    return result.returncode, json.loads(result.stdout), result


def _warnings(answer, kind):
    return [w for w in answer['meta'].get('warnings', []) if w.get('type') == kind]


@pytest.mark.parametrize('mode', sorted(PARSING_MODES))
@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_parsing_modes_name_the_recovered_file_and_exit_3(tmp_path, lang, mode):
    root = _tree(tmp_path, lang, broken=True)
    code, answer, result = _pack('pack', root.as_posix(), *PARSING_MODES[mode])
    (recovered,) = _warnings(answer, 'parse_recovered')
    assert recovered['files'] == [f'{root.as_posix()}/core/b.{lang}'] and recovered['count'] == 1
    assert _warnings(answer, 'analysis_incomplete')
    assert code == 3, result.stderr[-500:]
    # The pack itself is still answered: every candidate selected, counts unchanged.
    assert answer['meta']['selected'] == answer['meta']['total_candidates'] == len(FIXTURES[lang]) - 1


@pytest.mark.parametrize('mode', sorted(PARSING_MODES))
@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_clean_sibling_still_exits_0_without_the_warning(tmp_path, lang, mode):
    root = _tree(tmp_path, lang, broken=False)
    code, answer, result = _pack('pack', root.as_posix(), *PARSING_MODES[mode])
    assert code == 0, result.stderr[-500:]
    assert not _warnings(answer, 'parse_recovered') and not _warnings(answer, 'analysis_incomplete')
    assert 'relevance_warning' not in answer['meta'] or mode == 'content'


def test_uri_form_discloses_it_too(tmp_path):
    root = _tree(tmp_path, 'c', broken=True)
    code, answer, result = _pack(f'pack://{root.as_posix()}?architecture=true')
    (recovered,) = _warnings(answer, 'parse_recovered')
    assert recovered['files'] == [f'{root.as_posix()}/core/b.c']
    assert code == 3, result.stderr[-500:]


def test_both_graph_signals_name_the_file_once(tmp_path):
    """--architecture and --focus each build the graph; the file is one finding, not two."""
    root = _tree(tmp_path, 'c', broken=True)
    code, answer, _ = _pack('pack', root.as_posix(), '--architecture', '--focus', 'core', '--content')
    (recovered,) = _warnings(answer, 'parse_recovered')
    assert recovered['files'] == [f'{root.as_posix()}/core/b.c'] and recovered['count'] == 1
    assert code == 3


def test_text_output_names_the_file_and_exits_3(tmp_path):
    root = _tree(tmp_path, 'ts', broken=True)
    result = _run_reveal_direct('pack', root.as_posix(), '--architecture')
    assert result.returncode == 3
    assert 'Selected 2 of 2 files' in result.stdout
    assert 'tree-sitter could not read' in result.stdout + result.stderr
    assert 'core/b.ts' in result.stdout + result.stderr


@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_plain_pack_parses_nothing_and_stays_complete(tmp_path, lang):
    """Control: a plain pack ranks by name, size and path; no parser reads the broken file."""
    root = _tree(tmp_path, lang, broken=True)
    code, answer, result = _pack('pack', root.as_posix())
    assert code == 0, result.stderr[-500:]
    assert not _warnings(answer, 'parse_recovered') and not _warnings(answer, 'analysis_incomplete')


def test_content_without_a_structure_tier_file_parses_nothing(tmp_path):
    """Control: --content shows low-priority files by name only, so their syntax is never read."""
    root = _tree(tmp_path, 'c', broken=True, subdir='misc')
    code, answer, result = _pack('pack', root.as_posix(), '--content')
    assert {entry['content_type'] for entry in answer['content']} == {'name_only'}
    assert code == 0, result.stderr[-500:]
    assert not _warnings(answer, 'parse_recovered')


def test_warning_spells_paths_with_slashes_and_names_each_file_once():
    """Windows spelling: the graph and the outlines may each report a file; one '/'-spelled entry."""
    from reveal.adapters.pack import _record_recovered_warning
    meta = {}
    _record_recovered_warning(['proj\\core\\b.c', 'proj/core/b.c', 'proj\\core\\b.c'], meta)  # noqa: win-path
    (warning,) = meta['warnings']
    assert warning['type'] == 'parse_recovered'
    assert warning['files'] == ['proj/core/b.c'] and warning['count'] == 1
    empty = {}
    _record_recovered_warning([], empty)
    assert empty == {}
