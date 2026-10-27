"""--sideeffects / --boundary --transitive follow call sites to definitions, not bare names (BACK-2098).

collect_effects_transitive kept its own name-keyed forward index, followed the first
candidate of a name and marked the name visited, so with two `helper`s it classified the
wrong one (or never reached the other). It now walks `calls.index.walk_callees`, which
resolves each call site through CallResolver and places definitions by (file, line, name).
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

WRITER = 'def helper():\n    with open("out.txt", "w") as fh:\n        fh.write("x")\n'
CLIENT = 'import requests\n\n\ndef helper():\n    requests.get("http://example.com")\n'
ROOTS = {
    'root_a.py': 'from wa import helper\n\n\ndef run_a():\n    helper()\n',
    'root_b.py': 'from wb import helper\n\n\ndef run_b():\n    helper()\n',
    'root_both.py': 'import wa\nimport wb\n\n\ndef run_both():\n    wa.helper()\n    wb.helper()\n',
    'root_amb.py': 'def run_amb():\n    helper()\n',
}


@pytest.fixture
def twins(tmp_path):
    (tmp_path / 'wa.py').write_text(WRITER, encoding='utf-8')
    (tmp_path / 'wb.py').write_text(CLIENT, encoding='utf-8')
    for name, text in ROOTS.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def _kinds(tmp_path, root_file, function, flag):
    out = _run_reveal_direct(str(tmp_path / root_file), function, flag, '--transitive', '--format', 'json').stdout
    findings = json.loads(out)['findings']
    return sorted(f['kind'] for f in findings if f.get('hop') == 1)


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('root_file, function, expected', [
    ('root_a.py', 'run_a', ['file']),
    ('root_b.py', 'run_b', ['http']),
])
def test_a_helper_named_by_import_is_the_one_classified(twins, flag, root_file, function, expected):
    assert _kinds(twins, root_file, function, flag) == expected


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_a_root_calling_both_same_named_helpers_gets_both_effects(twins, flag):
    assert _kinds(twins, 'root_both.py', 'run_both', flag) == ['file', 'http']


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_an_ambiguous_hop_is_declined_with_a_note_not_guessed(twins, flag):
    kinds = _kinds(twins, 'root_amb.py', 'run_amb', flag)
    assert kinds == []
    text = _run_reveal_direct(str(twins / 'root_amb.py'), 'run_amb', flag, '--transitive').stdout
    assert 'ambiguous' in text and 'helper' in text
    assert 'wa.py' in text and 'wb.py' in text
    data = json.loads(_run_reveal_direct(str(twins / 'root_amb.py'), 'run_amb', flag, '--transitive',
                                         '--format', 'json').stdout)
    assert any('ambiguous' in w and 'helper' in w for w in data['warnings'])


# Negative control: unique names. These outputs were captured from master before the change.
UNIQUE = {
    'top.py': ('from mid import step_one\n\n\ndef entry():\n    step_one()\n    log_it()\n\n\n'
               'def log_it():\n    import logging\n    logging.info("x")\n'),
    'mid.py': ('import requests\nfrom leaf import save\n\n\ndef step_one():\n'
               '    requests.get("http://example.com")\n    save()\n'),
    'leaf.py': 'def save():\n    with open("o.txt", "w") as fh:\n        fh.write("x")\n',
}
UNIQUE_SIDEEFFECTS = (
    '[hop 1] via entry → step_one\n'
    '  L6       http  requests.get("http://example.com")\n'
    '[hop 1] via entry → log_it\n'
    '  L11      log   logging.info("x")\n'
    '[hop 2] via entry → step_one → save\n'
    '  L2       file  open("o.txt"...)'
)


@pytest.fixture
def unique(tmp_path):
    for name, text in UNIQUE.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def _normalised(text):
    return text.replace('\r\n', '\n')


def test_unique_names_keep_the_sideeffects_text_byte_for_byte(unique):
    out = _run_reveal_direct(str(unique / 'top.py'), 'entry', '--sideeffects', '--transitive').stdout
    assert _normalised(out).rstrip('\n') == UNIQUE_SIDEEFFECTS


def test_unique_names_keep_the_boundary_effects_section(unique):
    out = _normalised(_run_reveal_direct(str(unique / 'top.py'), 'entry', '--boundary', '--transitive').stdout)
    assert UNIQUE_SIDEEFFECTS.replace('\n', '\n  ').join(['EFFECTS (--transitive, depth=2):\n  ', '']) in out


def test_the_ambiguity_note_lists_three_candidates_and_counts_the_rest():
    from reveal.adapters.ast.nav_effects import AmbiguousHop, ambiguous_hops_note

    note = ambiguous_hops_note([AmbiguousHop('f', 'get', [(f'm{i}.py', i) for i in range(1, 8)])])
    assert '7 candidates: m1.py:1, m2.py:2, m3.py:3 +4 more' in note
    assert 'm4.py' not in note
    assert ambiguous_hops_note([]) is None
