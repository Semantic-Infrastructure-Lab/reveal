"""A config file that exists but cannot be loaded is never read as "no config" (BACK-1857, BACK-2677).

``_load_file`` returned None after a ``logger.error``, so the layers saw an empty config and
``check`` ran under the defaults while its JSON/MCP result said nothing about the user's
``.reveal.yaml`` having been ignored. BACK-1857/2659 disclosed it in a warning over that defaults-built
answer; it now fails every answer that reads configuration (``RevealConfig.require``: ConfigLoadError,
exit 3), and no warning claims the defaults were used.
"""
from pathlib import Path

import pytest

from reveal.checks import capability_disclosures
from reveal.config import RevealConfig
from reveal.errors import ConfigLoadError
from reveal.utils.invocation_log import invocation_warnings, log_scope

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


def _load_failure(root):
    """The failure an answer reading *root*'s config meets (BACK-2677), after checking that the load records
    no ``config_load_failed`` warning claiming the defaults were used. None when the config is usable."""
    with log_scope(to_stderr=False):
        config = RevealConfig.get(root)
        assert not [w for w in invocation_warnings() if w['code'] == 'config_load_failed']
    try:
        config.require()
    except ConfigLoadError as exc:
        return str(exc)
    return None


def test_check_no_longer_adds_its_own_config_note(project):
    (project / '.reveal.yaml').write_text(BROKEN_YAML, encoding='utf-8')
    assert not [n for n in capability_disclosures([str(project / 'a.py')], None, None) if n.startswith('config ')]


def test_broken_yaml_is_recorded_on_the_config(project):
    (project / '.reveal.yaml').write_text(BROKEN_YAML, encoding='utf-8')
    config = RevealConfig.get(project)
    ((path, why),) = config.load_failures
    assert Path(path) == project / '.reveal.yaml' and why.startswith('ParserError')
    assert RevealConfig._load_file(project / '.reveal.yaml') is None  # the old contract is unchanged


def test_a_broken_config_fails_the_answer_naming_it(project):
    (project / '.reveal.yaml').write_text(BROKEN_YAML, encoding='utf-8')
    failure = _load_failure(project)
    assert '.reveal.yaml could not be loaded' in failure and 'ParserError' in failure
    assert 'settings in it are unknown' in failure


def test_invalid_schema_is_a_load_failure(project):
    (project / '.reveal.yaml').write_text('- just\n- a list\n', encoding='utf-8')
    assert _load_failure(project), 'a config that fails validation is not "no config"'


def test_malformed_pyproject_hides_its_tool_reveal_section(project):
    (project / 'pyproject.toml').write_text('[tool.reveal\nx = \n', encoding='utf-8')
    assert 'pyproject.toml could not be loaded' in _load_failure(project)


def test_reveal_config_pointing_at_a_broken_file_is_disclosed(project, tmp_path, monkeypatch):
    broken = tmp_path / 'custom.yaml'
    broken.write_text(BROKEN_YAML, encoding='utf-8')
    monkeypatch.setenv('REVEAL_CONFIG', str(broken))
    assert 'custom.yaml could not be loaded' in _load_failure(project)


@pytest.mark.parametrize('content', [None, '', 'rules:\n  disable: [E501]\n'],
                         ids=['absent', 'empty', 'valid'])
def test_absent_empty_and_valid_configs_are_not_failures(project, content):
    if content is not None:
        (project / '.reveal.yaml').write_text(content, encoding='utf-8')
    assert RevealConfig.get(project).load_failures == []
    assert _load_failure(project) is None
