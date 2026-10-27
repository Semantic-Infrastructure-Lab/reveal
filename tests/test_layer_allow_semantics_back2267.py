"""Layer allow_imports semantics (BACK-2267).

absent allow_imports = no allow list; present (even empty) = an allow list; a layer's own
files are always allowed, so `allow_imports: []` reads "imports nothing outside this layer".
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import reveal
from reveal.analyzers.imports.layers import LayerConfig, LayerConfigError, LayerRule

ROOT = Path('/proj')
PACKAGE_ROOT = Path(reveal.__file__).resolve().parent.parent


def _rule(**kw):
    return LayerRule(name='domain', paths=['src/domain'], **kw)


def _violates(rule, src, dst):
    return rule.is_violation(ROOT / src, ROOT / dst, ROOT)[0]


def test_empty_allow_list_forbids_every_file_outside_the_layer():
    rule = _rule(allow_imports=[])
    assert _violates(rule, 'src/domain/a.py', 'src/infra/db.py') is True
    reason = rule.is_violation(ROOT / 'src/domain/a.py', ROOT / 'src/infra/db.py', ROOT)[1]
    assert 'domain' in reason and 'outside' in reason


def test_empty_allow_list_still_allows_the_layers_own_files():
    assert _violates(_rule(allow_imports=[]), 'src/domain/a.py', 'src/domain/b.py') is False


def test_allow_list_does_not_flag_the_layers_own_files():
    rule = _rule(allow_imports=['src/shared'])
    assert _violates(rule, 'src/domain/a.py', 'src/domain/b.py') is False
    assert _violates(rule, 'src/domain/a.py', 'src/shared/u.py') is False
    assert _violates(rule, 'src/domain/a.py', 'src/infra/db.py') is True


def test_absent_allow_list_restricts_nothing():
    assert _violates(_rule(deny_imports=['src/infra']), 'src/domain/a.py', 'src/shared/u.py') is False


def test_deny_still_wins_over_the_layers_own_files_and_allow_list():
    rule = _rule(allow_imports=['src/infra'], deny_imports=['src/infra'])
    assert _violates(rule, 'src/domain/a.py', 'src/infra/db.py') is True


def _config(layer):
    return {'architecture': {'layers': [layer]}}


def test_empty_allow_list_alone_is_a_valid_layer():
    cfg = LayerConfig.from_dict(_config({'name': 'd', 'paths': ['m'], 'allow_imports': []}))
    assert cfg.layers[0].allow_imports == []


def test_missing_allow_list_is_none_not_empty():
    cfg = LayerConfig.from_dict(_config({'name': 'd', 'paths': ['m'], 'deny_imports': ['x']}))
    assert cfg.layers[0].allow_imports is None


@pytest.mark.parametrize('layer, wanted', [
    ({'name': 'd', 'paths': ['m']}, r'neither.*allow_imports.*deny_imports'),
    ({'name': 'd', 'paths': ['m'], 'deny_imports': []}, r'neither.*allow_imports.*deny_imports'),
    ({'name': 'd', 'paths': ['m'], 'allow_imports': None}, r"allow_imports.*empty.*\[\]"),
    ({'name': 'd', 'paths': ['m'], 'allow_imports': 'src/x'}, r"allow_imports.*list"),
    ({'name': 'd', 'paths': ['m'], 'allow_imports': [1]}, r"allow_imports.*strings"),
])
def test_bad_shapes_fail_naming_the_key(layer, wanted):
    with pytest.raises(LayerConfigError, match=wanted):
        LayerConfig.from_dict(_config(layer), source='/p/.reveal.yaml')


def test_imports_violations_end_to_end(tmp_path):
    for d in ('src/domain', 'src/infra'):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / '__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'src' / '__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'src/domain/a.py').write_text('from src.domain import b\nfrom src.infra import db\nimport os\n',
                                              encoding='utf-8')
    (tmp_path / 'src/domain/b.py').write_text('X = 1\n', encoding='utf-8')
    (tmp_path / 'src/infra/db.py').write_text('Y = 1\n', encoding='utf-8')
    (tmp_path / '.reveal.yaml').write_text(
        'architecture:\n  layers:\n    - name: domain\n      paths: [src/domain]\n      allow_imports: []\n',
        encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=str(PACKAGE_ROOT))
    result = subprocess.run([sys.executable, '-m', 'reveal', 'imports://.?violations', '--format', 'json'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode in (0, 1), result.stdout + result.stderr
    rows = json.loads(result.stdout)['violations']
    targets = sorted(r['to_file'] for r in rows)
    assert targets and all(t.startswith('src/infra/') for t in targets)
    assert not any(r['to_file'].startswith('src/domain/') for r in rows)
