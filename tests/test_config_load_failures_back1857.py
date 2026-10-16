"""A config file that exists but cannot be loaded is disclosed, not read as "no config" (BACK-1857).

``_load_file`` returned None after a ``logger.error``, so the layers saw an empty config and
``check`` ran under the defaults while its JSON/MCP result said nothing about the user's
``.reveal.yaml`` having been ignored.
"""
from pathlib import Path

import pytest

from reveal.checks import capability_disclosures
from reveal.config import RevealConfig

pytestmark = pytest.mark.component

BROKEN_YAML = 'rules:\n  disable: [E501\n   bad: : yaml\n'


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    RevealConfig._cache.clear()
    yield
    RevealConfig._cache.clear()


@pytest.fixture
def project(tmp_path, monkeypatch):
    # Keep the user's and system configs out of it: only the project's own are in play.
    monkeypatch.setattr(RevealConfig, '_get_user_config_path', classmethod(lambda cls: tmp_path / 'no-user.yaml'))
    root = tmp_path / 'proj'
    root.mkdir()
    (root / '.git').mkdir()
    (root / 'a.py').write_text('x = 1\n', encoding='utf-8')
    return root


def _config_notes(root):
    return [n for n in capability_disclosures([str(root / 'a.py')], None, None)
            if n.startswith('config ')]


def test_broken_yaml_is_recorded_on_the_config(project):
    (project / '.reveal.yaml').write_text(BROKEN_YAML, encoding='utf-8')
    config = RevealConfig.get(project)
    ((path, why),) = config.load_failures
    assert Path(path) == project / '.reveal.yaml' and why.startswith('ParserError')
    assert RevealConfig._load_file(project / '.reveal.yaml') is None  # the old contract is unchanged


def test_check_discloses_the_config_it_ignored(project):
    (project / '.reveal.yaml').write_text(BROKEN_YAML, encoding='utf-8')
    (note,) = _config_notes(project)
    assert '.reveal.yaml could not be loaded' in note and 'ParserError' in note
    assert 'settings were not applied' in note


def test_invalid_schema_is_a_load_failure(project):
    (project / '.reveal.yaml').write_text('- just\n- a list\n', encoding='utf-8')
    assert _config_notes(project), 'a config that fails validation is not "no config"'


def test_malformed_pyproject_hides_its_tool_reveal_section(project):
    (project / 'pyproject.toml').write_text('[tool.reveal\nx = \n', encoding='utf-8')
    (note,) = _config_notes(project)
    assert 'pyproject.toml could not be loaded' in note


def test_reveal_config_pointing_at_a_broken_file_is_disclosed(project, tmp_path, monkeypatch):
    broken = tmp_path / 'custom.yaml'
    broken.write_text(BROKEN_YAML, encoding='utf-8')
    monkeypatch.setenv('REVEAL_CONFIG', str(broken))
    (note,) = _config_notes(project)
    assert 'custom.yaml could not be loaded' in note


@pytest.mark.parametrize('content', [None, '', 'rules:\n  disable: [E501]\n'],
                         ids=['absent', 'empty', 'valid'])
def test_absent_empty_and_valid_configs_are_not_failures(project, content):
    if content is not None:
        (project / '.reveal.yaml').write_text(content, encoding='utf-8')
    assert RevealConfig.get(project).load_failures == []
    assert not _config_notes(project)
