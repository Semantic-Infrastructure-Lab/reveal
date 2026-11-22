"""BACK-2623: surface's vocabulary under D20.

Preservation pins: the default answer on the subcommand, the URI and the API; the category filter; the per-directory
rollup and its depth; the source-only filter; the text-only per-category cap. They hold on every spelling that answers
today, before and after the vocabulary moves (an old spelling may add only its replaced-by note).
"""
import json

import pytest
from conftest import _run_reveal_direct as run

from reveal import api

APP = '''import os
import subprocess
import requests
from flask import Flask
app = Flask(__name__)


@app.route('/a')
def a():
    os.environ.get('A_KEY')
    os.environ.get('B_KEY')
    os.environ.get('C_KEY')
    subprocess.run(['ls'])
    return requests.get('http://x').text


@app.post('/b')
def b():
    with open('out.txt', 'w') as handle:
        handle.write('x')
    return 'ok'
'''
CLI = '''import argparse
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name')
    os.getenv('D_KEY')
    sqlite3.connect('x.db')
'''
TEST = '''import os


def test_a():
    os.environ.get('TEST_KEY')
'''


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """src/app (2 routes, 3 env reads, a launch, a client import, 2 writes), src/cli (an argument, an env read, a
    database import) and tests/ (one env read)."""
    for rel, body in (('src/app/server.py', APP), ('src/cli/main.py', CLI), ('tests/test_server.py', TEST)):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    done = run(*argv, '--format', 'json')
    return done.returncode, (json.loads(done.stdout) if done.stdout.strip().startswith('{') else None), done.stderr


def _text(*argv):
    done = run(*argv, '--format', 'text')
    return done.returncode, done.stdout, done.stderr


def _strip_notes(doc):
    doc = json.loads(json.dumps(doc))
    doc['meta']['warnings'] = [w for w in doc['meta']['warnings'] if w.get('type') != 'retired_spelling']
    return doc


def _counts(doc):
    return {category: len(rows) for category, rows in doc['surfaces'].items() if rows}


DEFAULT = {'cli': 1, 'http': 2, 'env': 5, 'network': 1, 'db': 1, 'fs': 2, 'subprocess': 1}


# --- preservation: what surface answers today, on every transport --------------------------------------------------

def test_the_default_answer_is_the_same_on_the_subcommand_the_uri_and_the_api(proj):
    code, sub, _ = _cli('surface', '.')
    assert code == 0 and sub['type'] == 'surface_scan' and sub['total'] == 13 and _counts(sub) == DEFAULT
    assert 'by_dir' not in sub and not [w for w in sub['meta']['warnings'] if w.get('type') == 'truncated']
    code, uri, _ = _cli('surface://.')
    assert code == 0 and _strip_notes(uri) == _strip_notes(sub)
    typed = api.query('surface', '.')
    assert typed['total'] == 13 and _counts(typed) == DEFAULT and 'by_dir' not in typed


def test_the_default_text_lists_every_entry_of_every_category(proj):
    code, out, _ = _text('surface', '.')
    assert code == 0 and 'Environment variables (5):' in out and 'TEST_KEY' in out
    assert 'Showing top' not in out and 'more (use' not in out


def test_one_category(proj):
    code, doc, _ = _cli('surface', '.', '--type', 'env')
    assert code == 0 and _counts(doc) == {'env': 5} and doc['total'] == 5
    assert _counts(api.query('surface', '.', type='env')) == {'env': 5}


def test_source_only_drops_the_test_files(proj):
    code, doc, _ = _cli('surface', '.', '--source-only')
    assert code == 0 and doc['total'] == 12 and _counts(doc)['env'] == 4
    assert 'TEST_KEY' not in {row['name'] for row in doc['surfaces']['env']}


def test_the_directory_rollup_and_its_depth(proj):
    code, doc, _ = _cli('surface', '.', '--by', 'dir')
    assert code == 0 and _counts(doc) == DEFAULT  # the rollup is added beside the unchanged categories
    assert [(row['dir'], row['total']) for row in doc['by_dir']] == [('src/app', 9), ('src/cli', 3), ('tests', 1)]
    code, folded, _ = _cli('surface', '.', '--by', 'dir', '--depth', '1')
    assert code == 0 and [(row['dir'], row['total']) for row in folded['by_dir']] == [('src', 12), ('tests', 1)]
    code, out, _ = _text('surface', '.', '--by', 'dir')
    assert code == 0 and 'By directory (3):' in out and 'Environment variables' not in out


def test_the_per_category_text_cap_leaves_json_complete(proj):
    _, whole, _ = _cli('surface', '.')
    code, capped, _ = _cli('surface', '.', '--top', '1')
    assert code == 0 and _strip_notes(capped) == _strip_notes(whole)
    code, out, _ = _text('surface', '.', '--top', '1')
    assert code == 0 and 'Environment variables (5):' in out and '… 4 more' in out
    assert 'C_KEY' not in out
    code, out, _ = _text('surface', '.', '--top', '0')  # 0 is every entry, as when omitted
    assert code == 0 and '… ' not in out and 'C_KEY' in out
