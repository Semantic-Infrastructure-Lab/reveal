"""Every ``meta.warnings`` entry a producer builds names its kind in ``type`` (BACK-2282c, BACK-2148).

``code`` stays beside it as the optional stable catalog id (``W-CALLS-1``). The readers
(``outcome_of``, ``note_warning``'s dedupe, the renderers' skip lists, ``collect_meta_warnings``)
key on ``type``, so an entry with only a ``code`` is invisible to them.

``tests/test_output_contract_compliance.py`` (invariant 11) checks the entries a fixture run
produces. Several producers need a partial scan, a broken file or an nginx text a small fixture
cannot give, so this file checks the source: a dict literal whose ``code`` is a warning code
must carry a ``type``.
"""
import ast
from pathlib import Path

import pytest

import reveal
from reveal.utils.results import note_warning

# Warning codes that are not 'W-...' catalog ids: the kind is the code.
_KIND_CODES = frozenset({'retired_spelling', 'not_applicable', 'unbalanced_braces', 'language_not_scanned'})


def _is_warning_code(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.startswith('W-') or node.value in _KIND_CODES
    return isinstance(node, ast.Name) and node.id.startswith('W_')  # W_CAP_PYTHON_ONLY


def _untyped_warning_literals(source, filename='<source>'):
    """(line, code) of each dict literal in `source` that has a warning ``code`` and no ``type``."""
    found = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value: v for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if 'code' in keys and _is_warning_code(keys['code']) and 'type' not in keys:
            code = keys['code']
            found.append((node.lineno, code.value if isinstance(code, ast.Constant) else code.id))
    return found


def test_every_warning_literal_in_the_package_has_a_type():
    root = Path(reveal.__file__).parent
    untyped = []
    for path in sorted(root.rglob('*.py')):
        for line, code in _untyped_warning_literals(path.read_text(encoding='utf-8'), str(path)):
            untyped.append(f'{path.relative_to(root).as_posix()}:{line} {code}')
    assert untyped == [], 'meta.warnings entries with a code and no type: ' + ', '.join(untyped)


def test_the_literal_check_bites():
    """Positive control: a code-only warning is found; a typed one, an error and a spread are not."""
    source = (
        "a = {'code': 'W-X-1', 'message': 'm'}\n"
        "b = {'type': 'k', 'code': 'W-X-2', 'message': 'm'}\n"
        "c = {'code': 'E_X', 'message': 'm'}\n"
        "d = {'code': W_CAP_X, 'message': 'm'}\n"
        "e = {'code': 'retired_spelling', 'message': 'm'}\n"
        "f = {**b, 'message': 'n'}\n")
    assert _untyped_warning_literals(source) == [(1, 'W-X-1'), (4, 'W_CAP_X'), (5, 'retired_spelling')]


def test_note_warning_keeps_two_coded_entries_of_one_type():
    """Entries sharing a kind but not a code are distinct caveats; only a true repeat is dropped."""
    result = {}
    note_warning(result, {'type': 'analysis_limit', 'code': 'W-CALLS-2', 'message': 'a'})
    note_warning(result, {'type': 'analysis_limit', 'code': 'W-CALLS-3', 'message': 'b'})
    note_warning(result, {'type': 'analysis_limit', 'code': 'W-CALLS-3', 'message': 'b'})
    assert [w['code'] for w in result['meta']['warnings']] == ['W-CALLS-2', 'W-CALLS-3']
