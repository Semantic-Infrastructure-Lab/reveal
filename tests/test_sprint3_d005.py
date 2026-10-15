"""D005 cached accounting must distinguish skipped, partial and complete scans."""
import json
import pickle
from pathlib import Path
import pytest
from reveal.rules.duplicates.D005 import D005, _project_index, get_scan_budgets, get_scan_disclosures, _clear_index
from reveal.rules.scan_caches import _d005_init_worker

pytestmark = pytest.mark.component


def project(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="scan"\n', encoding='utf-8')
    for i in range(3):
        (tmp_path / f'f{i}.py').write_text('NAMES = ["a", "b", "c", "d", "e"]\n', encoding='utf-8')
    return sorted(tmp_path.glob('*.py'))


def test_cap_is_skipped_with_lower_bound_and_survives_worker_cache(tmp_path, monkeypatch):
    files = project(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '1')
    assert D005().check(str(files[0]), None, '') == []
    row, = get_scan_budgets(files)
    assert row['limit'] == 1 and row['total'] == 2 and row['returned'] == 1
    assert row['exact'] is False and row['analyzed_files'] == 0 and row['skipped']
    cache = pickle.loads(pickle.dumps(dict(_project_index)))
    _clear_index(); _d005_init_worker(cache)
    assert get_scan_budgets(files) == [row]
    assert 'skipping cross-file scan' in get_scan_disclosures()[0]


def test_parse_failure_retains_good_claims_and_discloses_partial_scan(tmp_path):
    files = project(tmp_path)
    bad = tmp_path / 'bad.py'; bad.write_text('def broken(\n', encoding='utf-8')
    detections = D005().check(str(files[0]), None, '')
    assert detections
    row, = get_scan_budgets(files)
    assert row['exact'] and row['total'] == 4 and row['analyzed_files'] == 3
    assert row['failed_files'] == 1 and not row['skipped']
    assert any('bad.py' in d and 'incomplete' in d for d in get_scan_disclosures())


def test_directory_json_carries_rule_accounting_independently_of_display_cap(tmp_path, monkeypatch):
    from conftest import _run_reveal_direct
    project(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '1')
    result = _run_reveal_direct('check', str(tmp_path), '--select', 'D005', '--format', 'json', '--max-items', '0')
    data = json.loads(result.stdout)
    row, = [r for r in data['summary']['scan_budgets'] if r['rule'] == 'D005']
    assert row['skipped'] and row['analyzed_files'] == 0
    assert data['summary']['scan_disclosures']


def test_unreadable_file_is_counted_and_disclosed(tmp_path, monkeypatch):
    files = project(tmp_path)
    read = Path.read_text
    def unreadable(path, *args, **kwargs):
        if path == files[1]:
            raise PermissionError('recorded unreadable source')
        return read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', unreadable)
    D005().check(str(files[0]), None, '')
    row, = get_scan_budgets(files)
    assert row['total'] == 3 and row['failed_files'] == 1 and row['analyzed_files'] == 2
    assert any('f1.py' in d and 'PermissionError' in d for d in get_scan_disclosures())
