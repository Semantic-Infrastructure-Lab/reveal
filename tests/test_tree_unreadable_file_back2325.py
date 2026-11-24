"""A directory's tree that could not read one of its files says so and exits 3 (D6), as ``ast``, ``metrics`` and
``--grep`` do on the same tree (BACK-2520), ruling B1 of BACK-2325.

``reveal du`` (``du`` holding a mode-000 file) exited 0 and its JSON entry carried ``str(OSError)``, the errno and the
path (``PermissionError: [Errno 13] Permission denied: 'du/locked.py'``), against the ``failure_of`` rule (BACK-2249).
The entry now carries the cause alone, the document an ``analysis_failed`` warning naming the file (and the
``analysis_incomplete`` marker every incomplete answer carries), and the text tree a warning line after the body.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct

pytestmark = [
    pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows'),
    pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file'),
]


@pytest.fixture
def trees(tmp_path, monkeypatch):
    for name in ('d', 'du'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'a.py').write_text('x = 1\n', encoding='utf-8')
    locked = tmp_path / 'du' / 'locked.py'
    locked.write_text('y = 2\n', encoding='utf-8')
    os.chmod(locked, 0)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    os.chmod(locked, 0o644)


def test_the_json_tree_discloses_the_lost_file_and_exits_3(trees):
    run = _run_reveal_direct('du', '--format', 'json')
    assert run.returncode == 3, run.stderr
    document = json.loads(run.stdout)
    entry = next(e for e in document['entries'] if e['name'] == 'locked.py')
    assert entry['error'] == 'PermissionError: Permission denied'
    warnings = document['meta']['warnings']
    lost = next(w for w in warnings if w['type'] == 'analysis_failed')
    assert lost['files'] == ['locked.py'] and lost['count'] == 1
    assert 'du/' not in json.dumps(lost) and 'Errno' not in json.dumps(lost)
    assert any(w['type'] == 'analysis_incomplete' for w in warnings)


def test_the_text_tree_discloses_the_lost_file_and_exits_3(trees):
    run = _run_reveal_direct('du')
    assert run.returncode == 3
    assert '⚠ 1 file(s) could not be analyzed completely (PermissionError)' in run.stdout
    assert '└── locked.py' in run.stdout and 'Errno' not in run.stdout


@pytest.mark.parametrize('argv', [['d'], ['d', '--format', 'json']])
def test_sibling_a_readable_tree_exits_0_with_no_warning(trees, argv):
    run = _run_reveal_direct(*argv)
    assert run.returncode == 0, run.stderr
    assert 'could not be analyzed' not in run.stdout
    if '--format' in argv:
        assert json.loads(run.stdout)['meta']['warnings'] == []


def test_sibling_grep_on_the_same_tree_already_exits_3(trees):
    assert _run_reveal_direct('du', '--grep', 'x').returncode == 3


@pytest.mark.parametrize('name, lost', [('d', False), ('du', True)])
def test_mcp_reveal_structure_answers_the_tree_and_says_what_it_lost(trees, name, lost):
    """MCP reads the listing's Answer (its facts, its result as a dict): an incomplete tree is a result that says so,
    never a tool error (COMMAND_MODEL "Transports")."""
    from reveal import mcp_server
    out = mcp_server.reveal_structure(name)
    assert not isinstance(out, mcp_server._ToolFailure)
    assert f'{name}/' in out and ('could not be analyzed completely' in out) is lost
