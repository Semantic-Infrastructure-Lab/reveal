"""Long-lived requests see edited source, and disclosures belong to their request."""
from pathlib import Path
import pytest
from reveal import mcp_server as m

pytestmark = pytest.mark.component


def project(tmp_path):
    (tmp_path / 'pyproject.toml').touch()
    file = tmp_path / 'demo.py'; file.write_text('value = 1\n', encoding='utf-8')
    return file


def test_cycle_removed_between_direct_and_registered_requests(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    project(tmp_path)
    a = tmp_path / 'a.py'; b = tmp_path / 'b.py'
    a.write_text('import b\n', encoding='utf-8'); b.write_text('import a\n', encoding='utf-8')
    assert 'Circular dependency' in m.reveal_check(str(tmp_path), select='I002')
    b.write_text('value = 2\n', encoding='utf-8')
    assert m.reveal_check(str(tmp_path), select='I002') == 'No issues found.'
    registered = m.mcp._tool_manager._tools['reveal_check'].fn
    b.write_text('import a\n', encoding='utf-8')
    assert 'Circular dependency' in registered(path=str(tmp_path), select='I002')
    b.write_text('value = 2\n', encoding='utf-8')
    assert registered(path=str(tmp_path), select='I002') == 'No issues found.'


def test_d005_removed_duplicate_does_not_keep_cached_findings(tmp_path):
    project(tmp_path)
    files = [tmp_path / f'f{i}.py' for i in range(3)]
    for file in files:
        file.write_text('NAMES = ["a", "b", "c", "d", "e"]\n', encoding='utf-8')
    assert '[D005]' in m.reveal_check(str(tmp_path), select='D005')
    for i, file in enumerate(files):
        file.write_text(f'VALUE = {i}\n', encoding='utf-8')
    assert m.reveal_check(str(tmp_path), select='D005') == 'No issues found.'


def test_typeddict_index_refreshes_on_next_request(tmp_path):
    from reveal.rules.types.T006 import _project_facts
    file = project(tmp_path)
    types = tmp_path / 'types_.py'
    types.write_text('from typing import TypedDict\nclass Before(TypedDict):\n value: str\n', encoding='utf-8')
    before = _project_facts(str(file))
    types.write_text('from typing import TypedDict\nclass After(TypedDict):\n value: int\n', encoding='utf-8')
    assert _project_facts(str(file)) == before  # Demonstrates the stale owner.
    m.reveal_check(str(file), select='C901')
    assert _project_facts(str(file)) != before


def test_reverse_import_index_refreshes_on_next_request(tmp_path):
    from reveal.rules.maintainability.M102 import M102
    file = project(tmp_path); consumer = tmp_path / 'consumer.py'
    consumer.write_text('import demo\n', encoding='utf-8')
    before = M102()._collect_all_imports(tmp_path)
    assert 'demo' in before
    consumer.write_text('import other\n', encoding='utf-8')
    assert M102()._collect_all_imports(tmp_path) == before
    m.reveal_check(str(file), select='C901')
    after = M102()._collect_all_imports(tmp_path)
    assert 'other' in after and 'demo' not in after


def test_python_inventory_refreshes_on_next_request(tmp_path):
    from reveal.analyzers.imports.python import _python_project_inventory
    file = project(tmp_path)
    before = _python_project_inventory(tmp_path)
    (tmp_path / 'added.py').write_text('value=2\n', encoding='utf-8')
    assert _python_project_inventory(tmp_path) == before
    m.reveal_check(str(file), select='C901')
    assert 'added' in _python_project_inventory(tmp_path)[0]


def test_global_config_refreshes_on_next_request(tmp_path, monkeypatch):
    from reveal import config
    file = project(tmp_path); monkeypatch.chdir(tmp_path)
    yaml = tmp_path / '.reveal.yaml'; yaml.write_text('rules:\n  E501:\n    max_length: 20\n', encoding='utf-8')
    config._config = None; config.RevealConfig.reset_request_cache()
    assert config.get_config().get_rule_config('E501', 'max_length') == 20
    yaml.write_text('rules:\n  E501:\n    max_length: 200\n', encoding='utf-8')
    assert config.get_config().get_rule_config('E501', 'max_length') == 20
    m.reveal_check(str(file), select='C901')
    assert config.get_config().get_rule_config('E501', 'max_length') == 200


def test_cap_is_disclosed_and_does_not_leak_to_second_project(tmp_path, monkeypatch):
    roots = [tmp_path / name for name in ('capped', 'clean')]
    for root in roots:
        root.mkdir(); project(root)
    (roots[0] / 'extra.py').write_text('import demo\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '1')
    answer = m.reveal_check(str(roots[0]), select='I002')
    assert 'skipping circular-dependency' in answer and 'No issues found' not in answer
    assert m.reveal_check(str(roots[1]), select='I002') == 'No issues found.'


def test_review_does_not_borrow_another_projects_disclosure(tmp_path):
    roots = [tmp_path / name for name in ('broken', 'clean')]
    for root in roots:
        root.mkdir(); project(root)
    (roots[0] / 'bad.py').write_text('def broken(\n', encoding='utf-8')
    assert 'bad.py' in m.reveal_review(str(roots[0]), select='D005')
    answer = m.reveal_review(str(roots[1]), select='D005')
    assert str(roots[0]) not in answer and 'bad.py' not in answer


def test_d005_many_parse_failures_are_bounded(tmp_path):
    from reveal.rules.duplicates.D005 import D005, get_scan_disclosures
    file = project(tmp_path)
    for i in range(12):
        (tmp_path / f'bad{i}.py').write_text('def broken(\n', encoding='utf-8')
    D005().check(str(file), None, file.read_text(encoding='utf-8'))
    disclosures = get_scan_disclosures([file])
    assert len(disclosures) <= 7
    assert any('7 more' in d for d in disclosures)
    assert any('12' in d and 'incomplete' in d for d in disclosures)


@pytest.mark.skipif(__import__('sys').platform == 'win32', reason='symlink mutation control requires POSIX')
def test_path_resolution_refreshes_on_next_request(tmp_path):
    from reveal.config import _cached_resolve
    file = project(tmp_path)
    first = tmp_path / 'first'; second = tmp_path / 'second'
    first.mkdir(); second.mkdir()
    link = tmp_path / 'link'; link.symlink_to(first, target_is_directory=True)
    assert _cached_resolve(link) == first
    link.unlink(); link.symlink_to(second, target_is_directory=True)
    assert _cached_resolve(link) == first
    m.reveal_check(str(file), select='C901')
    assert _cached_resolve(link) == second
