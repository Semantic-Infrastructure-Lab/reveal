"""Element views JSON: the effects view names its view in ``meta.flag``, not a retiring word (BACK-2796, D16).

``--view effects``, ``--view effects --in-loops`` and ``--view effects --state`` answered ``meta.flag`` ``sideeffects``,
``fanout`` and ``statewrites``: the old flags' words, in the canonical answer's envelope. ``meta.flag`` is ``effects`` and
``meta.mode`` names the selection (``ordinary``, ``loops``, ``state``: D10's modes), on every spelling: an old flag
answers the same document plus its replaced-by note. The other views keep their ``meta.flag``.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api

SOURCE = '''import logging

log = logging.getLogger(__name__)


class Store:
    def save(self, items):
        total = 0
        for item in items:
            log.info("saving %s", item)
            self.count = total
            total += helper(item)
        return total


def helper(item):
    print(item)
    return 1
'''

EFFECTS = [(['--view', 'effects'], 'ordinary', '--sideeffects'),
           (['--view', 'effects', '--in-loops'], 'loops', '--fanout'),
           (['--view', 'effects', '--state'], 'state', '--statewrites')]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(*argv):
    run = _run_reveal_direct('m.py', 'Store.save', *argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _without_notes(document):
    meta = dict(document['meta'])
    meta['warnings'] = [w for w in meta['warnings'] if w.get('type') != 'retired_spelling']
    return {**document, 'meta': meta}


@pytest.mark.parametrize('flags, mode, legacy', EFFECTS, ids=[mode for _, mode, _ in EFFECTS])
def test_the_effects_view_names_its_view_and_its_mode(fx, flags, mode, legacy):
    meta = _json(*flags)['meta']
    assert (meta['flag'], meta.get('mode')) == ('effects', mode)


def test_the_transitive_effects_view_names_its_view(fx):
    meta = _json('--view', 'effects', '--transitive')['meta']
    assert (meta['flag'], meta.get('mode')) == ('effects', 'ordinary')


def test_the_python_api_answers_the_same_names(fx):
    meta = api.element('m.py', 'Store.save', view='effects', in_loops=True)['meta']
    assert (meta['flag'], meta.get('mode')) == ('effects', 'loops')


@pytest.mark.parametrize('flags, mode, legacy', EFFECTS, ids=[legacy for *_, legacy in EFFECTS])
def test_an_old_effects_flag_answers_the_same_document_with_its_note(fx, flags, mode, legacy):
    old = _json(legacy)
    assert [w['field'] for w in old['meta']['warnings'] if w.get('type') == 'retired_spelling'] == [f'flag:{legacy}']
    assert _without_notes(old) == _json(*flags)


@pytest.mark.parametrize('flags, name', [(['--view', 'boundary'], 'boundary'), (['--view', 'flow'], 'flow'),
                                         (['--view', 'exits'], 'exits'), (['--inputs'], 'inputs'),
                                         (['--varflow', 'total'], 'varflow')])
def test_sibling_the_other_views_keep_their_flag_and_carry_no_mode(fx, flags, name):
    meta = _json(*flags)['meta']
    assert meta['flag'] == name and 'mode' not in meta
