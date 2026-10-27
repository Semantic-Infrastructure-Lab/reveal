"""BACK-2258: a layer config in the wrong shape reported "No violations", exit 0.

`LayerConfig.from_dict` read only name/paths/allow_imports/deny_imports, so a `rules:`/`can_import:`
config (the shape the imports guide once taught), a misspelled key, or a layer with neither allow nor
deny enforced nothing and read as an architecture that passes. Each now fails naming where to look
(LayerConfigError, exit 3), like the other malformed-layer shapes (BACK-1059).
"""
import os
import subprocess
import sys

import pytest

from reveal.analyzers.imports.layers import LayerConfig, LayerConfigError

_LAYER = {'name': 'domain', 'paths': ['models'], 'deny_imports': ['db']}


@pytest.mark.parametrize('config, wanted', [
    pytest.param({'architecture': {'layers': [_LAYER], 'rules': [{'layer': 'domain', 'can_import': []}]}},
                 r"architecture.*'rules'", id='architecture-rules'),
    pytest.param({'architecture': {'layers': [dict(_LAYER, can_import=[])]}},
                 r"layers\[0\].*'can_import'", id='layer-can-import'),
    pytest.param({'architecture': {'layers': [{'name': 'd', 'paths': ['m'], 'allows_imports': ['x']}]}},
                 r"layers\[0\].*'allows_imports'.*allow_imports", id='misspelled-allow-suggests-the-key'),
    pytest.param({'architecture': {'layers': [{'name': 'd', 'paths': ['m']}]}},
                 r"layers\[0\].*neither.*allow_imports.*deny_imports", id='layer-enforces-nothing'),
    pytest.param({'architecture': {'layers': [{'name': 'd', 'paths': ['m'], 'allow_imports': []}]}},
                 r"layers\[0\].*neither a non-empty allow_imports", id='empty-allow-list-enforces-nothing'),
])
def test_wrong_shape_fails_naming_its_source(config, wanted):
    with pytest.raises(LayerConfigError, match=r'/p/\.reveal\.yaml.*' + wanted):
        LayerConfig.from_dict(config, source='/p/.reveal.yaml')


@pytest.mark.parametrize('layer', [
    pytest.param({'name': 'a', 'paths': ['a'], 'allow_imports': ['b']}, id='allow-only'),
    pytest.param({'name': 'a', 'paths': ['a'], 'deny_imports': ['b']}, id='deny-only'),
    pytest.param({'name': 'a', 'paths': ['a'], 'allow_imports': [], 'deny_imports': ['b']}, id='empty-allow-with-deny'),
])
def test_valid_layers_still_load(layer):
    assert [x.name for x in LayerConfig.from_dict({'architecture': {'layers': [layer]}}).layers] == ['a']


_PROJECT_CONFIG = """root: true
architecture:
  layers:
    - name: domain
      paths: [models]
  rules:
    - {layer: domain, can_import: []}
"""


def _project(tmp_path, config):
    for pkg in ('src', 'src/models', 'src/db'):
        (tmp_path / pkg).mkdir(exist_ok=True)
        (tmp_path / pkg / '__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'src/db/session.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'src/models/user.py').write_text('from src.db import session\n', encoding='utf-8')
    (tmp_path / '.reveal.yaml').write_text(config, encoding='utf-8')
    return tmp_path


def _violations(cwd):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', 'imports://src?violations'], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60, env=env)


def test_wrong_shape_config_is_not_reported_as_no_violations(tmp_path):
    r = _violations(_project(tmp_path, _PROJECT_CONFIG))
    assert 'No violations' not in r.stdout, r.stdout
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "'rules'" in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_right_shape_config_still_finds_the_violation(tmp_path):
    config = _PROJECT_CONFIG.split('  rules:')[0].replace('paths: [models]', 'paths: [models]\n      deny_imports: [db]')
    r = _violations(_project(tmp_path, config))
    assert r.returncode == 1 or 'domain' in r.stdout, (r.returncode, r.stdout, r.stderr)
    assert 'No violations' not in r.stdout, r.stdout
