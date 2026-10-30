"""A single-file overview displays map paths from the file's parent directory."""
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal import api


@pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
@pytest.mark.parametrize('absolute', [False, True])
@pytest.mark.parametrize('file_target', [True, False])
def test_file_and_directory_targets_share_parent_relative_map_paths(tmp_path, monkeypatch, transport, absolute, file_target):
    root = tmp_path / 'project'
    root.mkdir()
    file = root / 'module & %.py'
    file.write_text('VALUE=1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    path = file if file_target else root
    target = path.as_posix() if absolute else path.relative_to(tmp_path).as_posix()
    uri = 'overview://' + quote(target, safe='/.:')
    if transport == 'api':
        body = api.query(uri)
    else:
        result = run(*(['overview', target] if transport == 'cli' else [uri]), '--format', 'json')
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
    assert body['source'] == body['path'] == target
    assert body['scope']['total_code_files'] == 1 and body['scope']['complete'] is True
    metadata = body['map']['metadata']
    assert metadata['scanned_files'] == 1
    assert metadata['files_failed_count'] == metadata['files_lost_count'] == 0
    assert metadata['scan_budget']['returned'] == metadata['scan_budget']['total'] == 1
    assert metadata['scan_budget']['exact'] is True
    assert body['map']['components']['rows'] == [{'component': '.', 'files': 1, 'internal': 0,
        'outgoing': 0, 'incoming': 0, 'cohesion': 0.0, 'top_bridge': None}]
    assert body['map']['fan_in']['total'] == body['map']['entrypoints']['total'] == body['map']['cycles']['total'] == 0
    assert root.as_posix() not in json.dumps(body['map'])
