"""BACK-2624: contracts' vocabulary under D20.

--implementations on|off is the switch (--no-implementations its legacy flag); --implementations-limit N is the
nested cap (--impls its legacy flag). The old words answer as before, each with its note, and two spellings of one
control that disagree exit 2. The nested cap is never the result limit: JSON keeps every implementer.
"""
import json
import textwrap

import pytest
from conftest import _run_reveal_direct as run

from reveal import api
from reveal.errors import RequestValidationError


@pytest.fixture
def project(tmp_path):
    body = ['from abc import ABC, abstractmethod', '', '', 'class Base(ABC):', '    @abstractmethod',
            '    def go(self): ...', '']
    for n in range(8):
        body += ['', f'class Impl{n}(Base):', '    def go(self): return 1', '']
    (tmp_path / 'mod.py').write_text('\n'.join(body), encoding='utf-8')
    return tmp_path


def _cli(*argv):
    response = run(*argv, '--format', 'json')
    return response.returncode, (json.loads(response.stdout) if response.stdout.strip() else None), response.stderr


def _noted(answer, key):
    return [w for w in answer['meta']['warnings'] if w.get('field') == key]


def _impls(answer):
    return answer['abcs'][0]['implementations']


def test_implementations_off_removes_the_edges_and_on_keeps_them(project):
    assert len(_impls(api.query('contracts', str(project)))) == 8
    assert _impls(api.query('contracts', str(project), implementations=False)) == []
    code, off, _ = _cli('contracts', str(project), '--implementations', 'off')
    assert code == 0 and _impls(off) == [] and off['meta']['warnings'] == []
    code, on, _ = _cli('contracts', str(project), '--implementations', 'on')
    assert code == 0 and len(_impls(on)) == 8


def test_no_implementations_is_the_same_answer_with_a_note(project):
    _, new, _ = _cli('contracts', str(project), '--implementations', 'off')
    code, old, _ = _cli('contracts', str(project), '--no-implementations')
    assert code == 0
    assert [w['replacement'] for w in _noted(old, 'param:contracts.no_implementations')] == ['--implementations off']
    old['meta']['warnings'] = new['meta']['warnings'] = []
    assert old == new


def test_implementations_limit_caps_the_text_only_and_impls_is_the_same_cap_with_a_note(project):
    code, new, _ = _cli('contracts', str(project), '--implementations-limit', '2')
    assert code == 0 and new['impls_cap'] == 2 and len(_impls(new)) == 8  # JSON keeps every implementer
    code, old, _ = _cli('contracts', str(project), '--impls', '2')
    assert code == 0 and old['impls_cap'] == 2
    assert [w['replacement'] for w in _noted(old, 'param:contracts.impls')] == ['--implementations-limit N']
    assert _noted(new, 'param:contracts.impls') == []
    text = run('contracts', str(project), '--implementations-limit', '2').stdout
    assert 'and 6 more' in text and '--implementations-limit 0 lists all' in text


@pytest.mark.parametrize('argv,message', [
    (['--impls', '3', '--implementations-limit', '4'], 'conflict'),
    (['--no-implementations', '--implementations', 'on'], 'conflict'),
])
def test_two_spellings_that_disagree_exit_2(project, argv, message):
    response = run('contracts', str(project), *argv, '--format', 'json')
    assert response.returncode == 2 and message in response.stderr, response.stderr


def test_the_uri_form_takes_the_canonical_words_without_a_word_note(project):
    answer = api.query(f'contracts://{project}?implementations=off&implementations_limit=1')
    assert _impls(answer) == [] and answer['impls_cap'] == 1
    # the contracts:// request carries its own request note (BACK-2716); no word of it is noted
    assert [w for w in answer['meta']['warnings'] if w['field'].startswith('param:')] == []
    with pytest.raises(RequestValidationError, match='implementations_limit'):
        api.query(f'contracts://{project}?implementations_limit=-1')
