"""BACK-2146: ``hotspots=true`` ranks the filtered population, not the ``limit``/``offset`` page of files.

``limit`` and ``offset`` page the ``files`` list. The hotspot ranking was computed from that page, so
``?hotspots=true&sort=lines&limit=1`` ranked only the smallest file and answered "no hotspots" for a
tree whose busiest file is one: the answer to one question depended on a paging control, and the
shortened ranking was not recorded as a cut.
"""
import json

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component

BUSY = 'def busy(x):\n' + ''.join(f'    if x == {n}:\n        x += {n}\n' for n in range(14)) + '    return x\n'


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'tiny.py').write_text('X = 1\n', encoding='utf-8')
    (root / 'plain.py').write_text('def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n', encoding='utf-8')
    (root / 'busy.py').write_text(BUSY, encoding='utf-8')
    return root


def answer(query):
    result = run(f'metrics://proj?churn=false&{query}', '--format', 'json', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def ranked(doc):
    return [(h['file'], h['hotspot_score']) for h in doc['hotspots']]


@pytest.mark.parametrize('paging', ['sort=lines&limit=1', 'sort=lines&limit=1&offset=1', 'sort=lines&offset=2', 'sort=-lines&limit=1'])
def test_paging_the_files_does_not_change_the_hotspot_ranking(project, paging):
    whole = answer('hotspots=true')
    assert [file for file, _ in ranked(whole)] == ['busy.py'], 'positive control: the tree has a hotspot'
    page = answer(f'hotspots=true&{paging}')
    assert len(page['files']) < len(whole['files']), 'the paging control cut the files'
    assert ranked(page) == ranked(whole)


def test_the_page_is_still_cut_and_said_so(project):
    """Negative control: limit still pages the files list and records the cut."""
    page = answer('hotspots=true&sort=lines&limit=1')
    assert [row['file'] for row in page['files']] == ['tiny.py']
    cuts = [w for w in page['meta']['warnings'] if w.get('type') == 'truncated' or w.get('field') == 'files']
    assert cuts and cuts[0]['field'] == 'files'


def test_top_still_cuts_the_ranking_and_says_so(project):
    """Negative control: the ranking's own cap is unchanged."""
    (project / 'busy2.py').write_text(BUSY.replace('busy', 'busy2'), encoding='utf-8')
    capped = answer('hotspots=true&top=1')
    assert len(capped['hotspots']) == 1
    assert any(w.get('field') == 'hotspots' for w in capped['meta']['warnings'])
