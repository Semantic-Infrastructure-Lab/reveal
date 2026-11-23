"""BACK-2599 (rules R2 ruling 1): imports keeps a declared ``test_layout`` basis visible beside its Rules pointer, as
patches and surface do: declared additional paths, above all the whole scope by ``.``, change what counted. The
default basis of a selected project stays behind the pointer (``edge_rule.text``)."""

import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.analyzers.imports.service import edge_rule_disclosures
from reveal.config import RevealConfig

DEFAULT = {'anchor': '.', 'source': 'project', 'include_anchor_name': False, 'rule': 'is_test_path',
           'basis': 'paths relative to the selected project'}
DECLARED = dict(DEFAULT, additional_paths=['suite'],
                basis='paths relative to the selected project; conventional names plus declared additional paths')


def test_declared_basis_is_a_disclosure():
    assert edge_rule_disclosures({'test_scope': DECLARED}) == [
        'Test paths: paths relative to the selected project; conventional names plus declared additional paths; '
        'anchor ..']


def test_default_basis_is_no_disclosure():
    """Control: a selected project's default basis is behind the pointer."""
    assert edge_rule_disclosures({'test_scope': DEFAULT}) == []


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.setattr(RevealConfig, '_get_user_config_path', staticmethod(lambda: tmp_path / 'absent-user.yaml'))
    root = tmp_path / 'checkout'
    for rel, text in {'pyproject.toml': '[project]\nname="declared"\n', 'app.py': 'X = 1\n',
                      'suite/helper.py': 'import app\n'}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding='utf-8')
    return root


@pytest.mark.parametrize('paths, basis', [
    (['suite'], 'conventional names plus declared additional paths'),
    (['.'], 'WHOLE SCOPE selected by explicit .'),
])
def test_imports_text_shows_a_declared_basis(project, paths, basis):
    (project / '.reveal.yaml').write_text('test_layout:\n  additional_paths: ' + json.dumps(paths) + '\n',
                                          encoding='utf-8')
    data = json.loads(run('imports', str(project), '--format', 'json').stdout)
    assert basis in data['edge_rule']['test_scope']['basis']
    text = run('imports', str(project))
    assert text.returncode == 0, text.stderr
    assert basis in text.stdout
    assert 'Rules: --format json (edge_rule.text)' in [line.strip() for line in text.stdout.splitlines()]
