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


def test_rust_first_screen_has_no_python_vocabulary(tmp_path):
    text = _overview(_project(tmp_path, RUST))
    assert 'Rule:' in text and 'Active entrypoint candidates' in text
    assert 'TYPE_CHECKING' not in text
    assert '__init__.py' not in text


def test_shared_clauses_appear_once(tmp_path):
    text = _overview(_project(tmp_path, RUST))
    lines = _rule_lines(text)
    assert [line.split(':')[0].strip() for line in lines] == ['Rule', 'Rule (entry points)', 'Rule (cycles)']
    assert text.count('takes no &lazy') == 1
    assert text.count('Test paths:') == 1
    assert text.count('Import scope is unknown') <= 1


def test_each_section_still_names_what_differs(tmp_path):
    lines = _rule_lines(_overview(_project(tmp_path, RUST)))
    assert 'function-level (lazy) imports included (default)' in lines[0]
    assert 'importers under a test path not counted' in lines[1]
    assert 'function-level (lazy) imports excluded (default)' in lines[2]


def test_json_keeps_the_full_rule_per_section(tmp_path):
    result = json.loads(_overview(_project(tmp_path, RUST), '--format', 'json'))
    rules = result['map']['rules']
    for section in (rules['edge_rule'], *rules['edge_rule_sections'].values()):
        assert 'takes no &lazy' in section['text'] and 'Test paths:' in section['text']
        assert 'TYPE_CHECKING' not in section['text']


@pytest.mark.parametrize('files', [PYTHON, MIXED], ids=['python', 'rust+python'])
def test_python_scan_still_states_python_clauses(tmp_path, files):
    """Control: a scan holding Python files keeps both Python clauses, each once."""
    text = _overview(_project(tmp_path, files))
    assert 'TYPE_CHECKING imports excluded' in text
    assert 'not __init__.py' in text
    assert text.count('TYPE_CHECKING') == 1
    assert text.count('not __init__.py') == 1
    assert text.count('takes no &lazy') == 1
