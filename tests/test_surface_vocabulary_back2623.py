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


# --- the D20 vocabulary: canonical words, and each old word answering as before with its note ---------------------

ROWS = {'type': '--kind KIND', 'source_only': '--tests exclude', 'by': '--view dir', 'depth': '--dir-depth N',
        'top': '--limit N, which caps each category in JSON and text; 0 is uncapped'}


def _noted(doc, word):
    return [w['replacement'] for w in doc['meta']['warnings'] if w.get('field') == f'param:surface.{word}']


def test_kind_is_the_category_filter_and_type_its_noted_legacy_word(proj):
    code, new, _ = _cli('surface', '.', '--kind', 'env')
    assert code == 0 and _counts(new) == {'env': 5}
    code, old, _ = _cli('surface', '.', '--type', 'env')
    assert code == 0 and _noted(old, 'type') == [ROWS['type']] and _strip_notes(old) == _strip_notes(new)
    assert _text('surface', '.', '--type', 'env')[1] == _text('surface', '.', '--kind', 'env')[1]
    assert _cli('surface', '.', '--kind', 'bogus')[0] == 2


def test_tests_exclude_is_source_only_and_source_only_its_noted_legacy_flag(proj):
    code, new, _ = _cli('surface', '.', '--tests', 'exclude')
    assert code == 0 and new['total'] == 12
    code, old, _ = _cli('surface', '.', '--source-only')
    assert code == 0 and _noted(old, 'source_only') == [ROWS['source_only']]
    assert _strip_notes(old) == _strip_notes(new)
    assert _strip_notes(_cli('surface', '.', '--tests', 'include')[1]) == _strip_notes(_cli('surface', '.')[1])
    code, _, err = _cli('surface', '.', '--tests', 'only')  # surface has no tests-only answer
    assert code == 2 and 'include' in err and 'exclude' in err


def test_the_directory_rollup_is_a_view_and_by_its_noted_legacy_word(proj):
    code, new, _ = _cli('surface', '.', '--view', 'dir')
    assert code == 0 and [row['dir'] for row in new['by_dir']] == ['src/app', 'src/cli', 'tests']
    code, old, _ = _cli('surface', '.', '--by', 'dir')
    assert code == 0 and _noted(old, 'by') == [ROWS['by']] and _strip_notes(old) == _strip_notes(new)
    assert _text('surface', '.', '--by', 'dir')[1] == _text('surface', '.', '--view', 'dir')[1]
    assert _cli('surface', '.', '--view', 'dir', '--by', 'dir')[0] == 0  # one selection, spelled twice


def test_dir_depth_folds_the_rollup_and_depth_is_its_noted_legacy_word(proj):
    code, new, _ = _cli('surface', '.', '--view', 'dir', '--dir-depth', '1')
    assert code == 0 and [(row['dir'], row['total']) for row in new['by_dir']] == [('src', 12), ('tests', 1)]
    code, old, _ = _cli('surface', '.', '--view', 'dir', '--depth', '1')
    assert code == 0 and _noted(old, 'depth') == [ROWS['depth']] and _strip_notes(old) == _strip_notes(new)
    assert _strip_notes(_cli('surface://.?view=dir&dir_depth=1')[1]) == _strip_notes(new)  # the underscore alias


@pytest.mark.parametrize('argv', [['--depth', '2'], ['--dir-depth', '2'], ['--top', '1', '--dir-depth', '1']])
def test_the_rollup_depth_without_the_rollup_view_exits_2_naming_it(proj, argv):
    """B1: --depth N without the rollup was read and ignored (the answer byte-identical, exit 0)."""
    code, _, err = _cli('surface', '.', *argv)
    assert code == 2 and 'view' in err and 'dir' in err, err


def test_limit_cuts_each_category_in_json_and_text_with_the_cut_marker(proj):
    code, doc, _ = _cli('surface', '.', '--limit', '1')
    assert code == 0 and doc['total'] == 13  # the uncut count
    assert {category: len(rows) for category, rows in doc['surfaces'].items()} == {
        category: min(1, count) for category, count in {**dict.fromkeys(doc['surfaces'], 0), **DEFAULT}.items()}
    cuts = {w['field']: (w['shown'], w['total']) for w in doc['meta']['warnings'] if w.get('type') == 'truncated'}
    assert cuts == {'surfaces.http': (1, 2), 'surfaces.env': (1, 5), 'surfaces.fs': (1, 2)}
    code, out, _ = _text('surface', '.', '--limit', '1')
    assert code == 0 and 'Environment variables (5):' in out and '… 4 more' in out and 'C_KEY' not in out
    assert out.count('showing 1 of 5') <= 1  # one disclosure of each cut, not a second one under the rows
    assert _strip_notes(_cli('surface', '.', '--limit', '0')[1]) == _strip_notes(_cli('surface', '.')[1])


def test_limit_cuts_the_rollup_rows_in_the_rollup_view(proj):
    code, doc, _ = _cli('surface', '.', '--view', 'dir', '--limit', '1')
    assert code == 0 and [row['dir'] for row in doc['by_dir']] == ['src/app']
    assert ('by_dir', 1, 3) in {(w['field'], w['shown'], w['total']) for w in doc['meta']['warnings']
                                if w.get('type') == 'truncated'}


def test_top_stays_a_text_only_legacy_cap_with_its_note(proj):
    _, whole, _ = _cli('surface', '.')
    code, old, _ = _cli('surface', '.', '--top', '1')
    assert code == 0 and _noted(old, 'top') == [ROWS['top']] and _strip_notes(old) == _strip_notes(whole)


@pytest.mark.parametrize('argv', [['--top', '1', '--all'], ['--top', '1', '--limit', '2'], ['--top', '2', '--limit', '2'],
                                  ['--limit', '1', '--all'], ['--type', 'env', '--kind', 'cli'],
                                  ['--source-only', '--tests', 'include']])
def test_two_settings_of_one_thing_exit_2(proj, argv):
    """B2: --top 1 --all dropped --all; top caps text where limit caps the answer, so the two are never one setting."""
    code, _, err = _cli('surface', '.', *argv)
    assert code == 2, err


def test_all_on_its_own_is_the_uncapped_default(proj):
    assert _strip_notes(_cli('surface', '.', '--all')[1]) == _strip_notes(_cli('surface', '.')[1])


def test_the_api_takes_the_canonical_words(proj):
    assert _counts(api.query('surface', '.', kind='env')) == {'env': 5}
    assert api.query('surface', '.', tests='exclude')['total'] == 12
    assert [row['dir'] for row in api.query('surface', '.', view='dir', dir_depth=1)['by_dir']] == ['src', 'tests']
    assert len(api.query('surface', '.', limit=1)['surfaces']['env']) == 1


def test_a_uri_query_is_noted_with_the_canonical_request(proj):
    code, doc, _ = _cli('surface://.?type=env&source_only=true')
    assert code == 0
    request = [w['message'] for w in doc['meta']['warnings'] if 'surface:// request' in w.get('message', '')]
    assert request and 'reveal surface . --kind env --tests exclude' in request[0], request


def test_no_replacement_names_a_retiring_spelling():
    from reveal.cli.invocation import RETIREMENTS
    retiring = ('--type', '--source-only', '--by ', '--depth', '--top', 'source_only', 'by=', 'top=')
    for word, replacement in ROWS.items():
        row = RETIREMENTS[f'param:surface.{word}']
        assert row.replacement == replacement and row.stage == 'note'
        assert not any(old in row.replacement for old in retiring), (word, row.replacement)
    assert RETIREMENTS['param:surface.top'].standalone
