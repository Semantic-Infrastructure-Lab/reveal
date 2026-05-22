"""Tests for testability pressure analysis."""

from __future__ import annotations

from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.cli.commands.testability import create_testability_parser, run_testability
from reveal.testability.boundaries import collect_boundary_profiles
from reveal.testability.patches import group_patches, scan_patches
from reveal.testability.report import build_testability_report


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_scan_patches_detects_common_patch_forms(tmp_path):
    test_file = _write(tmp_path / 'tests' / 'test_service.py', '''
from unittest.mock import patch, mock

@patch("app.service._private_helper")
def test_decorator(mock_helper):
    pass

def test_context(monkeypatch):
    with patch("app.service.fetch_price"):
        with mock.patch.object(Client, "send"):
            monkeypatch.setattr("app.service.time.sleep", lambda _: None)
''')

    uses = scan_patches([test_file])

    targets = {u.target_raw for u in uses}
    assert "app.service._private_helper" in targets
    assert "app.service.fetch_price" in targets
    assert "Client.send" in targets
    assert "app.service.time.sleep" in targets
    assert any(u.is_private_target for u in uses)
    assert max(u.context_depth for u in uses) >= 1


def test_group_patches_by_target_and_test(tmp_path):
    test_file = _write(tmp_path / 'tests' / 'test_service.py', '''
from unittest.mock import patch

def test_one():
    with patch("app.service.fetch_price"):
        pass

def test_two():
    with patch("app.service.fetch_price"):
        pass
    with patch("app.service.notify"):
        pass
''')

    uses = scan_patches([test_file])
    by_target = group_patches(uses, group_by='target', min_count=1, limit=10)
    by_test = group_patches(uses, group_by='test', min_count=2, limit=10)

    assert by_target[0].key == 'app.service.fetch_price'
    assert by_target[0].patch_count == 2
    assert len(by_test) == 1
    assert by_test[0].key.endswith('::test_two')


def test_boundary_profiles_use_conservative_taxonomy(tmp_path):
    src = _write(tmp_path / 'src' / 'service.py', '''
import os
import requests
from pathlib import Path

def process(query, state):
    query.get("safe")
    response = requests.get("https://example.com")
    Path("out.txt").write_text(response.text)
    os.getenv("TOKEN")
    state.update({"ok": True})
''')

    profiles = collect_boundary_profiles(str(src.parent))
    process = next(p for p in profiles if p.function == 'process')

    assert 'network_client' in process.categories
    assert 'filesystem' in process.categories
    assert 'env_config' in process.categories
    assert 'mutation' in process.categories
    assert 'persistence' not in process.categories


def test_patches_adapter_returns_groups_and_json_shape(tmp_path):
    test_file = _write(tmp_path / 'tests' / 'test_service.py', '''
from unittest.mock import patch

def test_one():
    with patch("app.service.fetch_price"):
        pass
''')

    result = PatchesAdapter(str(test_file), 'group=target').get_structure()

    assert result['type'] == 'patches_scan'
    assert result['total_uses'] == 1
    assert result['groups'][0]['key'] == 'app.service.fetch_price'
    assert result['meta']['parse_mode'] == 'python_ast'


def test_build_testability_report_joins_patch_pressure_to_boundaries(tmp_path):
    _write(tmp_path / 'src' / 'service.py', '''
import requests
from pathlib import Path

def fetch_price():
    response = requests.get("https://example.com")
    Path("cache.txt").write_text(response.text)
    return response.text
''')
    _write(tmp_path / 'tests' / 'test_service.py', '''
from unittest.mock import patch

def test_one():
    with patch("service.fetch_price"):
        pass

def test_two():
    with patch("service.fetch_price"):
        pass
''')

    report = build_testability_report(
        str(tmp_path / 'src'),
        [str(tmp_path / 'tests')],
        min_patches=1,
        min_categories=2,
    )

    assert report['summary']['total_patch_uses'] == 2
    assert report['patch_hotspots'][0]['key'] == 'service.fetch_price'
    assert report['patch_hotspots'][0]['related_profiles']


def test_report_does_not_join_class_method_patch_to_same_named_methods(tmp_path):
    _write(tmp_path / 'src' / 'a.py', '''
import requests

class Adapter:
    def get_structure(self):
        return requests.get("https://example.com")
''')
    _write(tmp_path / 'src' / 'b.py', '''
import requests

class Adapter:
    def get_structure(self):
        return requests.get("https://example.org")
''')
    _write(tmp_path / 'tests' / 'test_a.py', '''
from unittest.mock import patch

def test_one():
    with patch("pkg.a.Adapter.get_structure"):
        pass
''')

    report = build_testability_report(
        str(tmp_path / 'src'),
        [str(tmp_path / 'tests')],
        min_patches=1,
        min_categories=1,
    )

    related = report['patch_hotspots'][0]['related_profiles']
    assert [Path(row['file']).name for row in related] == ['a.py']


def test_create_testability_parser_defaults():
    parser = create_testability_parser()
    args = parser.parse_args([])

    assert args.path == '.'
    assert args.top == 20
    assert args.min_patches == 3
    assert args.min_categories == 3


def test_run_testability_text_output(tmp_path):
    _write(tmp_path / 'src' / 'service.py', '''
import requests

def fetch_price():
    return requests.get("https://example.com").text
''')
    _write(tmp_path / 'tests' / 'test_service.py', '''
from unittest.mock import patch

def test_one():
    with patch("service.fetch_price"):
        pass
''')
    args = Namespace(
        path=str(tmp_path / 'src'),
        tests=[str(tmp_path / 'tests')],
        top=10,
        min_patches=1,
        min_categories=1,
        include_unresolved=True,
        format='text',
    )

    out = StringIO()
    with patch('sys.stdout', out):
        run_testability(args)

    text = out.getvalue()
    assert 'Testability:' in text
    assert 'service.fetch_price' in text
    assert 'Boundary Fan-Out Hotspots' in text


def test_suppressed_targets_excluded_by_default(tmp_path):
    test_file = _write(tmp_path / 'tests' / 'test_output.py', '''
from unittest.mock import patch

def test_one():
    with patch("sys.stdout"):
        pass

def test_two():
    with patch("sys.stderr"):
        pass

def test_three():
    with patch("app.service.fetch_price"):
        pass
''')

    uses = scan_patches([test_file])
    by_default = group_patches(uses, group_by='target')
    by_all = group_patches(uses, group_by='target', suppress=False)

    keys_default = {g.key for g in by_default}
    keys_all = {g.key for g in by_all}

    assert 'sys.stdout' not in keys_default
    assert 'sys.stderr' not in keys_default
    assert 'app.service.fetch_price' in keys_default

    assert 'sys.stdout' in keys_all
    assert 'sys.stderr' in keys_all

    # total_uses counts all patches regardless of suppression
    assert len(uses) == 3


def test_adapter_suppress_false_includes_stdlib_io(tmp_path):
    test_file = _write(tmp_path / 'tests' / 'test_output.py', '''
from unittest.mock import patch

def test_one():
    with patch("sys.stdout"):
        pass

def test_two():
    with patch("app.service.fetch_price"):
        pass
''')

    result_default = PatchesAdapter(str(test_file), 'group=target').get_structure()
    result_all = PatchesAdapter(str(test_file), 'group=target&suppress=false').get_structure()

    keys_default = {g['key'] for g in result_default['groups']}
    keys_all = {g['key'] for g in result_all['groups']}

    assert 'sys.stdout' not in keys_default
    assert 'sys.stdout' in keys_all
    # total_uses is always the full scan count
    assert result_default['total_uses'] == result_all['total_uses'] == 2
