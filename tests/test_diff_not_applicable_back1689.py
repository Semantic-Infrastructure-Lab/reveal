"""BACK-1689: diff:// compares functions, classes and imports only. A pair of resources that
carry none of them (sqlite, env, JSON, YAML, Markdown) is declined as not-applicable (exit 0,
applicable=False, a reason naming the resource) instead of printing "No structural changes
detected" -- a false clean."""

import json
import sqlite3
import subprocess
import sys

import pytest


def _reveal(cwd, *args):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.fixture
def files(tmp_path):
    (tmp_path / 'a.json').write_text('{"a": 1}', encoding='utf-8')
    (tmp_path / 'b.json').write_text('{"b": 2}', encoding='utf-8')
    (tmp_path / 'a.yaml').write_text('a: 1\n', encoding='utf-8')
    (tmp_path / 'b.yaml').write_text('b: 2\n', encoding='utf-8')
    (tmp_path / 'a.md').write_text('# One\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# Two\n', encoding='utf-8')
    for name, table in (('a.db', 'x'), ('b.db', 'y')):
        con = sqlite3.connect(str(tmp_path / name))
        con.execute(f'create table {table}(i int)')
        con.commit()
        con.close()
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def f():\n    return 1\n\ndef g():\n    return 2\n',
                                   encoding='utf-8')
    (tmp_path / 'empty1.py').write_text('', encoding='utf-8')
    (tmp_path / 'empty2.py').write_text('', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('uri', [
    'diff://a.json:b.json',
    'diff://a.yaml:b.yaml',
    'diff://a.md:b.md',
    'diff://sqlite://a.db:sqlite://b.db',
    'diff://env://:env://PATH',
])
def test_non_code_pair_is_declined_not_called_clean(files, uri):
    proc = _reveal(files, uri, '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope['applicable'] is False
    assert 'functions, classes and imports' in envelope['reason']
    assert 'summary' not in envelope


def test_non_code_pair_text_does_not_say_no_changes(files):
    proc = _reveal(files, 'diff://a.json:b.json')
    assert proc.returncode == 0
    assert 'No structural changes detected' not in proc.stdout


def test_one_non_code_side_is_declined(files):
    proc = _reveal(files, 'diff://a.py:b.json', '--format', 'json')
    assert proc.returncode == 0
    assert json.loads(proc.stdout)['applicable'] is False


def test_element_form_is_declined_too(files):
    proc = _reveal(files, 'diff://a.json:b.json/a', '--format', 'json')
    assert json.loads(proc.stdout)['applicable'] is False


# Negative controls: code diffs behave as before.
def test_real_code_diff_still_reports_the_change(files):
    proc = _reveal(files, 'diff://a.py:b.py', '--format', 'json')
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result.get('applicable', True) is not False
    assert result['summary']['functions']['added'] == 1


def test_unchanged_code_is_still_clean(files):
    proc = _reveal(files, 'diff://a.py:a.py')
    assert proc.returncode == 0
    assert 'No structural changes detected' in proc.stdout


def test_empty_code_files_are_still_comparable(files):
    proc = _reveal(files, 'diff://empty1.py:empty2.py')
    assert proc.returncode == 0
    assert 'No structural changes detected' in proc.stdout


def test_directory_diff_still_works(files):
    proc = _reveal(files, f'diff://{files}:{files}', '--format', 'json')
    assert proc.returncode == 0
    assert json.loads(proc.stdout).get('applicable', True) is not False
