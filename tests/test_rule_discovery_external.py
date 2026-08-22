"""BACK-856 — user-global and project-local custom rule discovery.

Reveal supports custom rules in two locations outside the reveal package:

    ~/.local/share/reveal/rules/<category>/<CODE>.py   (user-global)
    <project root>/.reveal/rules/<category>/<CODE>.py  (project-local)

Both were dead code. `_discover_dir()` built a synthetic module name
("user.rules.custom.Q001" / "project.rules.custom.Q001") and handed it to
`importlib.import_module()`, but no `user`/`project` package exists on
sys.path — so every custom rule failed with ModuleNotFoundError, which was
swallowed by a broad `except` and logged at ERROR, invisible at default
verbosity. The feature silently did nothing, with no test covering either path.

Two path bugs compounded it: `user_data_dir` returned `get_data_path('').parent`
(~/.local/share, dropping the `reveal` component), and `project_config_dir`
was anchored to `Path.cwd()` rather than the project root, so project rules
vanished whenever reveal ran from a subdirectory.
"""

import pytest

from reveal.rules import RuleRegistry
from reveal.rules.base import Severity, RulePrefix

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


@pytest.fixture
def clean_registry():
    """Snapshot and restore the class-level registry around a test."""
    saved = (
        list(RuleRegistry._rules),
        dict(RuleRegistry._rules_by_code),
        RuleRegistry._discovered,
    )
    RuleRegistry._rules = []
    RuleRegistry._rules_by_code = {}
    # These tests drive the individual _discover_*_rules() entry points
    # directly, so mark discovery as already done: get_rule() otherwise
    # lazily re-runs full discover(), which resets the registry and would
    # throw away the rule under test.
    RuleRegistry._discovered = True
    yield RuleRegistry
    RuleRegistry._rules, RuleRegistry._rules_by_code, RuleRegistry._discovered = saved


def _write_rule(rules_dir, code, *, severity="Severity.HIGH", category=None):
    """Write a minimal valid rule file into <rules_dir>/custom/<code>.py.

    `severity`/`category` are injected as raw source literals so a test can
    author them the loose way a user would (`'"high"'`) or the typed way
    (`"Severity.HIGH"`).
    """
    category_literal = repr(category) if category is not None else "RulePrefix.B"
    custom = rules_dir / "custom"
    custom.mkdir(parents=True, exist_ok=True)
    source = (
        "from reveal.rules.base import BaseRule, Severity, RulePrefix\n"
        "\n"
        f"class {code}(BaseRule):\n"
        f'    code = "{code}"\n'
        f'    message = "custom rule {code}"\n'
        f"    category = {category_literal}\n"
        f"    severity = {severity}\n"
        "    file_patterns = ['*.py']\n"
        '    version = "1.0.0"\n'
        "\n"
        "    def check(self, file_path, structure, content):\n"
        "        return []\n"
    )
    (custom / f"{code}.py").write_text(source)
    return custom / f"{code}.py"


class _FakeConfig:
    """Minimal stand-in for RevealConfig's rule-discovery surface."""

    def __init__(self, user_data_dir, project_config_dir):
        self.user_data_dir = user_data_dir
        self.project_config_dir = project_config_dir

    def get_legacy_paths(self):
        return {"rules_user": self.user_data_dir / "_nonexistent_legacy"}


def test_project_local_rule_is_discovered(clean_registry, tmp_path):
    """A rule under <project>/.reveal/rules/ must actually load and register."""
    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Q001")

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    rule = clean_registry.get_rule("Q001")
    assert rule is not None, "project-local rule was not discovered"
    assert rule.code == "Q001"


def test_user_global_rule_is_discovered(clean_registry, tmp_path):
    """A rule under ~/.local/share/reveal/rules/ must actually load and register."""
    user_data_dir = tmp_path / "share" / "reveal"
    _write_rule(user_data_dir / "rules", "W001")

    clean_registry._discover_user_rules(
        _FakeConfig(user_data_dir, tmp_path / "unused")
    )

    assert clean_registry.get_rule("W001") is not None, (
        "user-global rule was not discovered"
    )


def test_external_rule_does_not_shadow_real_packages(clean_registry, tmp_path):
    """External rule modules are parked under a reveal-owned sys.modules
    namespace, so a rule dir can never squat on a real top-level package."""
    import sys

    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Q002")

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    assert "project" not in sys.modules
    assert any(
        name.startswith(RuleRegistry._EXTERNAL_MODULE_NAMESPACE)
        for name in sys.modules
    )


def test_string_severity_is_normalized(clean_registry, tmp_path):
    """`severity = "high"` is a natural way to author a rule; it must be
    coerced to the enum rather than crashing every consumer of .severity.value."""
    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Q003", severity='"high"')

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    rule = clean_registry.get_rule("Q003")
    assert rule.severity is Severity.HIGH


def test_unknown_severity_degrades_instead_of_crashing(clean_registry, tmp_path):
    """One mistyped user rule must not take down `reveal --rules` for all rules."""
    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Q004", severity='"banana"')

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    rule = clean_registry.get_rule("Q004")
    assert rule.severity is Severity.MEDIUM
    # The whole listing must still render.
    assert clean_registry._rule_to_dict(rule)["severity"] == "medium"


def test_known_string_category_is_normalized(clean_registry, tmp_path):
    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Q005", category="B")

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    assert clean_registry.get_rule("Q005").category is RulePrefix.B


def test_unknown_string_category_is_left_alone(clean_registry, tmp_path):
    """Prefixes outside the known set are emitted as plain strings by the rule
    scaffold on purpose (cli/scaffold/rule.py) — normalization must not choke."""
    project_config_dir = tmp_path / ".reveal"
    _write_rule(project_config_dir / "rules", "Z999", category="Z")

    clean_registry._discover_project_rules(
        _FakeConfig(tmp_path / "unused", project_config_dir)
    )

    rule = clean_registry.get_rule("Z999")
    assert rule.category == "Z"
    assert clean_registry._rule_to_dict(rule)["category"] == "Z"


# --------------------------------------------------------------------------- #
# Config path anchors
# --------------------------------------------------------------------------- #

def test_user_data_dir_includes_reveal_component():
    """user_data_dir must be ~/.local/share/reveal, not ~/.local/share —
    the latter sends discovery to ~/.local/share/rules/, which nothing writes."""
    from reveal.config import get_config

    assert get_config().user_data_dir.name == "reveal"


def test_project_config_dir_is_anchored_to_project_root(tmp_path, monkeypatch):
    """Project rules must resolve the same from any subdirectory of the project."""
    from reveal.config import RevealConfig

    config = RevealConfig.get(start_path=tmp_path)
    monkeypatch.chdir(tmp_path)
    from_root = config.project_config_dir

    subdir = tmp_path / "src" / "deep"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    assert config.project_config_dir == from_root
