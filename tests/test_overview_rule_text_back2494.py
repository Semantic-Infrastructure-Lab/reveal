"""The overview first screen states each rule once, in the vocabulary of the scanned languages (BACK-2494)."""
import json

import pytest

from conftest import _run_reveal_direct as run

RUST = {
    'Cargo.toml': '[package]\nname = "probe"\nversion = "0.1.0"\n',
    'src/main.rs': 'mod util;\nmod core;\nuse crate::util::helper;\nfn main() { helper(); }\n',
    'src/util.rs': 'use crate::core::X;\npub fn helper() {}\n',
    'src/core.rs': 'pub const X: i32 = 1;\n',
    'tests/it.rs': 'use probe::util::helper;\n',
}
PYTHON = {
    'pyproject.toml': '[project]\nname = "probe"\n',
    'app.py': 'import core\nimport util\n',
    'core.py': 'X = 1\n',
    'util.py': 'import core\n',
    'pkg/__init__.py': 'import core\n',
    'tests/test_app.py': 'import app\n',
}
MIXED = {**RUST, **{name: text for name, text in PYTHON.items() if name != 'pyproject.toml'}}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _project(tmp_path, files):
    root = (tmp_path / 'p')
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _overview(root, *flags):
    out = run('overview', root, *flags)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _rule_lines(text):
    return [line for line in text.splitlines() if line.strip().startswith('Rule')]


def _rules(root):
    rules = json.loads(_overview(root, '--format', 'json'))['map']['rules']
    return [rules['edge_rule']['text'], *(section['text'] for section in rules['edge_rule_sections'].values())]


# The first screen points at the rules' JSON fields (BACK-2685); the vocabulary checks read those fields.

def test_rust_first_screen_has_no_python_vocabulary(tmp_path):
    root = _project(tmp_path, RUST)
    text = _overview(root)
    assert 'Rules: --format json (' in text and 'Active entrypoint candidates' in text
    assert 'TYPE_CHECKING' not in text and not any('TYPE_CHECKING' in rule for rule in _rules(root))
    assert '__init__.py' not in text


def test_shared_clauses_appear_once(tmp_path):
    root = _project(tmp_path, RUST)
    text = _overview(root)
    lines = _rule_lines(text)
    assert len(lines) == 1 and lines[0].startswith('Rules: --format json (')
    assert lines[0].endswith('map.rules.edge_rule.text, map.rules.edge_rule_sections.entry_points.text, '
                             'map.rules.edge_rule_sections.cycles.text)')
    assert text.count('takes no &lazy') == 0 and text.count('Test paths:') == 0  # stated once, in each JSON rule
    assert text.count('Import scope is unknown') <= 1


def test_each_section_still_names_what_differs(tmp_path):
    rules = _rules(_project(tmp_path, RUST))
    assert 'function-level (lazy) imports included (default)' in rules[0]
    assert 'importers under a test path not counted' in rules[1]
    assert 'function-level (lazy) imports excluded (default)' in rules[2]


def test_json_keeps_the_full_rule_per_section(tmp_path):
    result = json.loads(_overview(_project(tmp_path, RUST), '--format', 'json'))
    rules = result['map']['rules']
    for section in (rules['edge_rule'], *rules['edge_rule_sections'].values()):
        assert 'takes no &lazy' in section['text'] and 'Test paths:' in section['text']
        assert 'TYPE_CHECKING' not in section['text']


@pytest.mark.parametrize('files', [PYTHON, MIXED], ids=['python', 'rust+python'])
def test_python_scan_still_states_python_clauses(tmp_path, files):
    """Control: a scan holding Python files keeps both Python clauses: the entrypoint predicate once in text, the
    TYPE_CHECKING clause in the JSON rule the text points at (BACK-2685)."""
    root = _project(tmp_path, files)
    text = _overview(root)
    assert 'TYPE_CHECKING imports excluded' in _rules(root)[0]
    assert 'not __init__.py' in text
    assert text.count('TYPE_CHECKING') == 0
    assert text.count('not __init__.py') == 1
    assert text.count('takes no &lazy') == 0
