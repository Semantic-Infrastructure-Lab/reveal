"""architecture://: a relative subdirectory target is not doubled in next_commands.

The engine hands back cwd-relative files for a relative target
(`sub/pkg/core.py` for target `sub`); relativizing them as if they were
target-relative kept `sub/pkg/core.py`, and the next command spelled it under
the target again: `reveal sub/sub/pkg/core.py`.
"""

from pathlib import Path

from reveal.adapters.architecture import (
    _build_next_commands, _relativize_architecture_paths, _relativize_risks,
)


def test_relative_target_risk_files_are_target_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    risks = [{'type': 'load_bearing', 'file': 'sub/pkg/core.py', 'fan_in': 9},
             {'type': 'high_complexity_entry', 'file': 'sub/cli.py', 'complexity': 30}]
    _relativize_risks(risks, Path('sub'))
    assert [r['file'] for r in risks] == ['pkg/core.py', 'cli.py']
    cmds = _build_next_commands(Path('sub'), risks, {})
    assert 'reveal sub/pkg/core.py' in cmds
    assert 'reveal sub/cli.py --boundary' in cmds


def test_absolute_target_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'sub'
    risks = [{'type': 'load_bearing', 'file': str(target / 'pkg' / 'core.py'), 'fan_in': 9}]
    _relativize_risks(risks, target)
    assert risks[0]['file'] == 'pkg/core.py'
    report = {'facts': {'components': [{'component': '.', 'top_bridge': 'pkg/core.py'}]}}
    _relativize_architecture_paths(report, target)
    assert report['facts']['components'][0] == {'component': '.', 'top_bridge': 'pkg/core.py'}


def test_relative_target_facts_are_target_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = {'facts': {'entry_points': [{'file': 'sub/cli.py'}],
                        'core_abstractions': [{'file': 'sub/pkg/core.py'}],
                        'components': [{'component': 'sub/pkg', 'top_bridge': 'sub/pkg/core.py'}],
                        'circular_groups': [['sub/a.py', 'sub/b.py']]}}
    _relativize_architecture_paths(report, Path('sub'))
    facts = report['facts']
    assert facts['entry_points'][0]['file'] == 'cli.py'
    assert facts['core_abstractions'][0]['file'] == 'pkg/core.py'
    assert facts['components'][0] == {'component': 'pkg', 'top_bridge': 'pkg/core.py'}
    assert facts['circular_groups'] == [['a.py', 'b.py']]
