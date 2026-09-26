"""BACK-1495: overview's Architecture section ignored --exclude.

stats/scope honored it, but the import graph behind fan_in/entrypoints/components
walked every file: `--exclude c.py` left c.py in fan_in and the component file count.
"""
import json
import os
import subprocess
import sys

import pytest

ENV = {**os.environ, 'REVEAL_DISK_CACHE': '0'}


@pytest.fixture
def tree(tmp_path):
    for name in ('a,b.py', 'c.py', 'd.py'):
        (tmp_path / name).write_text("def f():\n    return 1\n", encoding='utf-8')
    (tmp_path / 'e.min.js').write_text("var x=1;\n", encoding='utf-8')
    return tmp_path


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main', *args], capture_output=True,
                          text=True, encoding='utf-8', env=ENV)


def fan_in_files(proc):
    assert proc.returncode == 0, proc.stderr
    return sorted(e['file'] for e in json.loads(proc.stdout)['architecture']['fan_in'])


@pytest.mark.parametrize('form', ['subcommand', 'uri_flag', 'uri_query'])
def test_architecture_drops_excluded_file(tree, form):
    args = {
        'subcommand': ['overview', str(tree), '--exclude', 'c.py'],
        'uri_flag': [f'overview://{tree}', '--exclude', 'c.py'],
        'uri_query': [f'overview://{tree}?exclude=c.py'],
    }[form]
    assert fan_in_files(run_reveal(*args, '--format', 'json')) == ['a,b.py', 'd.py', 'e.min.js']


def test_unexcluded_baseline_lists_all(tree):
    assert fan_in_files(run_reveal('overview', str(tree), '--format', 'json')) == [
        'a,b.py', 'c.py', 'd.py', 'e.min.js']


def test_comma_pattern_reaches_architecture(tree):
    proc = run_reveal('overview', str(tree), '--exclude', 'a,b.py', '--format', 'json')
    assert fan_in_files(proc) == ['c.py', 'd.py', 'e.min.js']


def test_glob_pattern_drops_matching_files(tree):
    proc = run_reveal('overview', str(tree), '--exclude', '*.min.js', '--format', 'json')
    assert fan_in_files(proc) == ['a,b.py', 'c.py', 'd.py']


def test_component_file_count_follows_exclude(tree):
    proc = run_reveal('overview', str(tree), '--exclude', 'c.py', '--format', 'json')
    comps = json.loads(proc.stdout)['architecture']['components']
    assert sum(c['files'] for c in comps) == 3


def test_imports_uri_honors_file_exclude(tree):
    proc = run_reveal(f'imports://{tree}?rank=fan-in', '--exclude', 'c.py', '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    assert 'c.py' not in proc.stdout
    assert 'd.py' in proc.stdout
