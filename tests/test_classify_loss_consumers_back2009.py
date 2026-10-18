"""Classify's real discovery loss survives existing presentation consumers."""

import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component


def project(tmp_path):
    root = tmp_path / 'project'
    child = root / 'included_child'
    child.mkdir(parents=True)
    (root / 'visible.py').write_text('VALUE = 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('VALUE = 2\n', encoding='utf-8')
    return root, child


def deny_child(monkeypatch, child):
    real = os.scandir

    def scandir(path):
        if Path(path) == child:
            raise PermissionError(13, 'controlled Classify child loss', str(child))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)


def loss_warning(payload):
    entries = [w for w in (payload.get('meta') or {}).get('warnings', [])
               if w.get('type') == 'analysis_incomplete']
    assert len(entries) == 1
    warning = entries[0]
    assert warning['count'] == 1 and warning['unit'] == 'directories'
    assert warning['directories'] == ['included_child']
    assert 'PermissionError' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    return warning


def test_classify_loss_survives_json_fields_and_item_budget(tmp_path, monkeypatch):
    root, child = project(tmp_path)
    deny_child(monkeypatch, child)
    result = run(f'classify://{root}', '--format', 'json', '--fields', 'files,summary',
                 '--max-items', '0')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['summary']['total'] == 1
    assert payload['summary']['excluded'] == 0
    assert payload['files'] == []
    loss_warning(payload)


def test_classify_human_and_json_artifact_disclose_loss_once(tmp_path, monkeypatch):
    root, child = project(tmp_path)
    artifact = tmp_path / 'classification.json'
    deny_child(monkeypatch, child)
    result = run(f'classify://{root}', '--also-json', str(artifact))
    assert result.returncode == 0, result.stderr
    assert 'visible.py' in result.stdout and 'hidden.py' not in result.stdout
    assert result.stdout.count('identified directory enumeration(s) failed') == 1
    payload = json.loads(artifact.read_text(encoding='utf-8'))
    assert payload['files'] == [{'file': 'visible.py', 'provenance': 'first_party'}]
    loss_warning(payload)


def test_classify_generic_mcp_query_discloses_loss_and_keeps_sibling(tmp_path, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query

    root, child = project(tmp_path)
    sibling = tmp_path / 'sibling'
    sibling.mkdir()
    (sibling / 'clean.py').write_text('VALUE = 3\n', encoding='utf-8')
    clean = reveal_query(f'classify://{sibling}')
    deny_child(monkeypatch, child)
    answer = reveal_query(f'classify://{root}')
    assert isinstance(answer, str)
    assert reveal_query(f'classify://{sibling}') == clean
    assert 'visible.py' in answer and 'hidden.py' not in answer
    assert answer.count('identified directory enumeration(s) failed') == 1
    assert 'PermissionError' in answer
