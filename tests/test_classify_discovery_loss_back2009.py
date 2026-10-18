"""Classify must qualify required directory loss without changing population policy."""

import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.classify import ClassifyAdapter, ClassifyRenderer, _classify_directory
from reveal.utils.exclusions import exclusion_scope


def make_tree(root, *, survivors=True):
    child = root / 'included_child'
    child.mkdir(parents=True)
    (child / 'hidden.py').write_text('hidden = 1\n', encoding='utf-8')
    if survivors:
        (root / 'visible.py').write_text('visible = 1\n', encoding='utf-8')
    return child


def deny(monkeypatch, children, *, unknown=False):
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) in children:
            attempts.append(Path(path))
            if unknown:
                raise PermissionError('controlled unknown enumeration location')
            raise PermissionError(13, 'controlled Classify child denial', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def warning(result):
    warnings = result.get('meta', {}).get('warnings', [])
    found = [item for item in warnings if item.get('type') == 'analysis_incomplete']
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize('survivors', [False, True])
@pytest.mark.parametrize('file_request', [False, True])
def test_real_loss_is_qualified_and_same_adapter_recovers(tmp_path, monkeypatch, survivors, file_request):
    root = tmp_path / 'affected'
    child = make_tree(root, survivors=survivors)
    # A file request analyzes its parent just like the existing Classify owner.
    selected = root / 'visible.py' if file_request and survivors else root
    adapter = ClassifyAdapter(str(selected))
    clean = adapter.get_structure()
    with monkeypatch.context() as context:
        attempts = deny(context, {child})
        result = adapter.get_structure()
        assert attempts
        assert result['summary']['total'] == int(survivors)
        assert result['summary']['excluded'] == 0
        assert result['files'] == ([{'file':'visible.py', 'provenance':'first_party'}] if survivors else [])
        loss = warning(result)
        assert loss['count'] == 1
        assert loss['unit'] == 'directories'
        assert loss['directories'] == ['included_child']
        assert 'PermissionError' in loss['message']
        assert 'missing file population is unknown' in loss['message']
        assert not any(key.startswith('_') for key in result)
    assert adapter.get_structure() == clean


@pytest.mark.parametrize('survivors', [False, True])
def test_real_loss_text_warning_is_visible_once(tmp_path, monkeypatch, capsys, survivors):
    root = tmp_path / 'affected'
    child = make_tree(root, survivors=survivors)
    deny(monkeypatch, {child})
    result = ClassifyAdapter(str(root)).get_structure()
    ClassifyRenderer.render_structure(result)
    output = capsys.readouterr()
    assert (output.out + output.err).count('missing file population is unknown') == 1
    assert 'PermissionError' in output.out + output.err


def test_unknown_location_remains_loss_with_zero_identified_directories(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child = make_tree(root)
    deny(monkeypatch, {child}, unknown=True)
    loss = warning(ClassifyAdapter(str(root)).get_structure())
    assert loss['count'] == 0
    assert loss['directories'] == []
    assert loss['unknown_directory_events'] == 1
    assert 'PermissionError' in loss['message']


def test_multiple_failed_directories_keep_shared_display_bound(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    root.mkdir()
    children = {root / f'included_{number}' for number in range(7)}
    for child in children:
        child.mkdir()
        (child / 'hidden.py').write_text('x = 1\n', encoding='utf-8')
    deny(monkeypatch, children)
    result = ClassifyAdapter(str(root)).get_structure()
    assert result['summary']['total'] == 0
    loss = warning(result)
    assert loss['count'] == 7
    assert len(loss['directories']) == 5
    assert 'and 2 more' in loss['message']


@pytest.mark.parametrize('extra', [(), ('--head','1'), ('--fields','summary'), ('--exclude','visible.py')])
def test_cli_projection_retains_loss_json_artifact_and_legacy_zero_exit(tmp_path, monkeypatch, extra):
    root = tmp_path / 'affected'
    child = make_tree(root)
    artifact = tmp_path / 'answer.json'
    deny(monkeypatch, {child})
    # Text plus sidecar exercises the artifact owner; global JSON intentionally has no sidecar.
    text = _run_reveal_direct(f'classify://{root.as_posix()}', '--also-json', str(artifact), *extra)
    assert text.returncode == 0
    assert (text.stdout + text.stderr).count('missing file population is unknown') == 1
    loss = warning(json.loads(artifact.read_text(encoding='utf-8')))
    assert loss['count'] == 1
    machine = _run_reveal_direct(f'classify://{root.as_posix()}', '--format', 'json', *extra)
    assert machine.returncode == 0
    result = json.loads(machine.stdout)
    assert warning(result) == loss
    if extra == ('--exclude','visible.py'):
        assert result['summary']['total'] == 0
        assert result['summary']['excluded'] == 0


def test_clean_and_intentionally_excluded_siblings_are_exactly_unchanged(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child = make_tree(root)
    sibling = tmp_path / 'healthy'
    make_tree(sibling)
    baseline = ClassifyAdapter(str(sibling)).get_structure()
    with exclusion_scope(root, ['included_child/']):
        excluded = ClassifyAdapter(str(root)).get_structure()
        attempts = deny(monkeypatch, {child})
        assert ClassifyAdapter(str(root)).get_structure() == excluded
        assert attempts == []
    assert ClassifyAdapter(str(sibling)).get_structure() == baseline
    assert 'meta' not in baseline
    assert baseline['contract_version'] == '1.0'


def test_unsupported_files_remain_policy_exclusions_not_operational_loss(tmp_path):
    (tmp_path / 'style.css').write_text('body {}\n', encoding='utf-8')
    result = ClassifyAdapter(str(tmp_path)).get_structure()
    assert result['files'] == []
    assert result['summary']['excluded'] == 1
    assert result['summary']['excluded_by_extension'] == {'.css':1}
    assert 'meta' not in result


def test_private_helper_still_returns_existing_pair_and_clean_order(tmp_path):
    make_tree(tmp_path / 'clean')
    rows, excluded = _classify_directory(tmp_path / 'clean')
    assert [row['file'] for row in rows] == ['visible.py', 'included_child/hidden.py']
    assert excluded == {}
