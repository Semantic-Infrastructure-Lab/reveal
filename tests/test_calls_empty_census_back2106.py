"""An empty language census withholds the calls confidence (BACK-2106, plan rule 8).

``meta.confidence`` is a file-weighted mean of measured per-language recall. With no source file
counted (an empty directory, a scope of non-code files, or a corpus under a gitignored tree) there is
nothing to weight, and the answer printed the 0.85 language-agnostic default as if it were measured.
It now carries no confidence and W-CALLS-12 says why; a non-empty census keeps its number.
"""
import json
import subprocess

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import confidence
from reveal.analyzers._capability_table import calls_extraction_confidence

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def codes(meta):
    return [w.get('code') for w in meta['warnings']]


def empty_census_scopes(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    prose = tmp_path / 'prose'
    write(prose / 'notes.txt', 'No supported source in this scope.\n')
    return {'empty': empty, 'prose': prose}


@pytest.mark.parametrize('scope', ['empty', 'prose'])
@pytest.mark.parametrize('query', ['rank=callers&top=1', 'callers=leaf', 'callees=leaf'])
def test_empty_census_withholds_confidence_and_names_why(tmp_path, scope, query):
    root = empty_census_scopes(tmp_path)[scope]
    assert confidence.language_census(str(root)) == {}
    meta = CallsAdapter(str(root), query).get_structure()['meta']
    assert 'confidence' not in meta
    assert meta['parse_mode'] == 'tree_sitter_full'
    decline = next(w for w in meta['warnings'] if w.get('code') == 'W-CALLS-12')
    assert decline['type'] == 'not_measured'
    assert decline['message'].startswith('Confidence withheld')


def test_build_meta_with_held_empty_census_withholds(tmp_path):
    root = empty_census_scopes(tmp_path)['empty']
    meta = confidence.build_meta(str(root), census={})
    assert meta['confidence'] is None and 'W-CALLS-12' in codes(meta)


def test_gitignored_corpus_withholds_and_keeps_scope_hidden(tmp_path):
    """The reported case: a corpus under a gitignored tree (samples/ in the reveal checkout)."""
    repo = tmp_path / 'repo'
    write(repo / '.gitignore', 'samples/\n')
    corpus = repo / 'samples' / 'proj'
    write(corpus / 'm.py', 'def a():\n    b()\n\ndef b():\n    pass\n')
    subprocess.run(['git', 'init', '-q', str(repo)], check=True, timeout=30)
    meta = CallsAdapter(str(corpus), 'rank=callers&top=1').get_structure()['meta']
    assert 'confidence' not in meta
    types = [w.get('type') for w in meta['warnings']]
    assert 'scope_hidden' in types and 'W-CALLS-12' in codes(meta)


def test_json_and_text_both_disclose(tmp_path):
    root = empty_census_scopes(tmp_path)['empty']
    as_json = run(f'calls://{root.as_posix()}?rank=callers&top=1', '--format', 'json')
    data = json.loads(as_json.stdout)
    assert 'confidence' not in data['meta']
    assert 'W-CALLS-12' in codes(data['meta'])
    as_text = run(f'calls://{root.as_posix()}?rank=callers&top=1')
    assert 'Confidence withheld' in as_text.stdout + as_text.stderr


# Negative controls: a census that counted files keeps its measured figure and gets no W-CALLS-12.

def test_nonempty_census_keeps_its_number(tmp_path):
    root = tmp_path / 'py'
    write(root / 'leaf.py', 'def leaf():\n    return 1\n')
    write(root / 'entry.py', 'from leaf import leaf\n\ndef entry():\n    return leaf()\n')
    meta = CallsAdapter(str(root), 'callers=leaf').get_structure()['meta']
    assert meta['confidence'] == calls_extraction_confidence('python')
    assert 'W-CALLS-12' not in codes(meta)


def test_held_nonempty_census_keeps_its_number(tmp_path):
    meta = confidence.build_meta(str(tmp_path), census={'python': 3, 'go': 1})
    expected = round((3 * calls_extraction_confidence('python') + calls_extraction_confidence('go')) / 4, 4)
    assert meta['confidence'] == expected and 'W-CALLS-12' not in codes(meta)


def test_no_call_edge_language_census_is_not_empty(tmp_path):
    """Shell files are counted by the census: the scope is not empty, so this change leaves it alone."""
    root = tmp_path / 'sh'
    write(root / 'run.sh', 'main() {\n  echo hi\n}\nmain\n')
    census = confidence.language_census(str(root))
    assert census, census
    meta = confidence.build_meta(str(root))
    assert 'W-CALLS-12' not in codes(meta) and meta['confidence'] is not None
