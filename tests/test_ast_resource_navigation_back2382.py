"""Overview emits executable AST navigation for URI-escaped target paths."""
import json
import shlex
import sys
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.overview import OverviewAdapter


@pytest.mark.parametrize('name', ['project space', pytest.param('project?space',
    marks=pytest.mark.skipif(sys.platform == 'win32', reason="Windows forbids '?' in filenames"))])
def test_overview_ast_hint_uses_encoded_resource_and_preserves_scope(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    for function in ('keep', 'omit'):
        (root / (function + '.py')).write_text(f'def {function}():\n    return 1\n', encoding='utf-8')
    owner = OverviewAdapter(str(root), params={'top': 0, 'exclude': 'omit.py'})
    answer = owner.get_structure()
    steps = [shlex.split(step['command']) for step in answer['next_steps']
             if step['question'] == 'Function complexity ranking']
    assert len(steps) == 1
    command, = steps
    assert command[1] == 'ast://' + quote(root.as_posix(), safe='/.:') + '?type=function&sort=-complexity'
    assert 'cannot represent' not in answer['reading_note']
    response = run(*command[1:], '--format', 'json')
    assert response.returncode == 0, (response.stdout, response.stderr)
    body = json.loads(response.stdout)
    assert body['type'] == 'ast_query'
    assert {row['name'] for row in body['results']} == {'keep'}
