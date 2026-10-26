"""BACK-2236: `imports://…?violations` crashed in text ("Requested output failed: 'file'", exit 3).

The renderer, and the output schema, read file/line/message; the rows carry from_file, to_file,
layer and reason (no line number).
"""
import json
import os
import subprocess
import sys

import pytest

_CONFIG = """root: true
architecture:
  layers:
    - name: domain
      paths: [models]
      deny_imports: [db]
"""


@pytest.fixture()
def project(tmp_path):
    for pkg in ('src', 'src/models', 'src/db'):
        (tmp_path / pkg).mkdir(exist_ok=True)
        (tmp_path / pkg / '__init__.py').write_text('')
    (tmp_path / 'src/db/session.py').write_text('x = 1\n')
    (tmp_path / 'src/models/user.py').write_text('from src.db import session\n')
    (tmp_path / '.reveal.yaml').write_text(_CONFIG)
    return tmp_path


def _reveal(cwd, *args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True,
                          text=True, encoding='utf-8', timeout=60, env=env)


def test_text_lists_each_violation_instead_of_crashing(project):
    r = _reveal(project, 'imports://src?violations')
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert 'Requested output failed' not in r.stdout + r.stderr
    assert 'models/user.py -> db/session.py  [domain] domain layer cannot import from db' in r.stdout


def test_json_rows_use_the_documented_schema_fields(project):
    data = json.loads(_reveal(project, 'imports://src?violations', '--format=json').stdout)
    assert data['count'] >= 1
    assert set(data['violations'][0]) == {'from_file', 'to_file', 'layer', 'reason'}


def test_fail_on_findings_exits_1_when_there_are_violations(project):
    r = _reveal(project, 'imports://src?violations', '--fail-on', 'findings')
    assert r.returncode == 1, (r.stdout, r.stderr)


def test_the_schema_declares_the_fields_the_rows_carry():
    from reveal.adapters.imports import ImportsAdapter
    schema = next(t for t in ImportsAdapter.get_schema()['output_types'] if t['type'] == 'layer_violations')
    props = schema['schema']['properties']['violations']['items']['properties']
    assert set(props) == {'from_file', 'to_file', 'layer', 'reason'}
