"""Unit tests for scripts/check_boundaries.py (the shared-seam ratchet, BACK-1515/1046/1368)."""
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    'check_boundaries', Path(__file__).resolve().parent.parent / 'scripts' / 'check_boundaries.py')
cb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cb)

PLAIN = 'reveal/adapters/foo.py'


def _hits(src, rel=PLAIN):
    return {rule: lines for rule, lines in cb.find_sites(src, rel).items() if lines}


@pytest.mark.parametrize('src', [
    "import os\nos.walk(p)",
    "from os import walk\nwalk(p)",
    "p.rglob('*.py')",
    "p.glob('**/*.py')",
    "p.glob(f'**/*.{ext}')",
    "import glob\nglob.glob(pat, recursive=True)",
    "def scan(d):\n    for c in d.iterdir():\n        scan(c)",
    "class A:\n    def scan(self, d):\n        for c in d.iterdir():\n            self.scan(c)",
])
def test_walker_flagged(src):
    assert set(_hits(src)) == {'walker'}


@pytest.mark.parametrize('src', [
    "p.glob('*.py')",
    "import glob\nglob.glob(pat)",
    "def ls(d):\n    return list(d.iterdir())",
    "import ast\nast.walk(tree)",
])
def test_walker_not_flagged(src):
    assert _hits(src) == {}


def test_walker_home_is_the_shared_walker_function_including_nested_helpers():
    src = "def _walk_code_files(r):\n    def inner():\n        return os.walk(r)\n    return inner()"
    assert _hits(src, 'reveal/utils/path_utils.py') == {}
    # Same file, any other function: still a second walker.
    assert _hits("def other(r):\n    return os.walk(r)", 'reveal/utils/path_utils.py') == {
        'walker': [2]}


@pytest.mark.parametrize('src', [
    "import tree_sitter",
    "from tree_sitter_language_pack import get_parser",
    "def f():\n    from tree_sitter import Parser",
])
def test_tree_sitter_import_flagged(src):
    assert set(_hits(src)) == {'tree-sitter-import'}


@pytest.mark.parametrize('src, rel', [
    ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from tree_sitter import Node", PLAIN),
    ("from .tree_sitter_helpers import x", PLAIN),
    ("from tree_sitter_language_pack import get_parser", 'reveal/core/treesitter_compat.py'),
])
def test_tree_sitter_import_not_flagged(src, rel):
    assert _hits(src, rel) == {}


def test_type_checking_else_branch_is_still_checked():
    src = "if TYPE_CHECKING:\n    import tree_sitter\nelse:\n    import tree_sitter_language_pack"
    assert _hits(src) == {'tree-sitter-import': [4]}


@pytest.mark.parametrize('src', [
    "import sys\nsys.exit(1)",
    "from sys import exit as bail\nbail(2)",
    "import os\nos._exit(1)",
    "exit()",
    "raise SystemExit",
    "raise SystemExit(2)",
])
def test_exit_flagged(src):
    assert set(_hits(src)) == {'exit'}


@pytest.mark.parametrize('src', [
    "print('x')",
    "import sys\nsys.stderr.write('x')",
    "import sys\nsys.stdout.write('x')",
])
def test_print_flagged(src):
    assert set(_hits(src)) == {'print'}


@pytest.mark.parametrize('src', [
    "import sys\nname = sys.argv[1]",
    "import sys\nif '--copy' in sys.argv:\n    pass",
    "import sys\nsys.argv.remove('--perf')",
    "from sys import argv",
])
def test_argv_flagged(src):
    assert set(_hits(src)) == {'argv'}


@pytest.mark.parametrize('src', [
    "print(add_cli_contract_fields(report, result_type='x', source=p))",
    "from reveal.utils import results\nresults.add_cli_contract_fields(r, result_type='x', source=p)",
])
def test_subcommand_output_flagged(src):
    # BACK-1544: a runner that builds its own JSON envelope skips the outcome seam.
    hits = _hits(src, 'reveal/cli/commands/foo.py')
    assert set(hits) == {'subcommand-output'}


def test_subcommand_output_home_is_the_emitter_only():
    src = ("def emit_subcommand_result(result):\n    return add_cli_contract_fields(result)\n"
           "def other(result):\n    return add_cli_contract_fields(result)\n")
    assert _hits(src, 'reveal/cli/routing/subcommand.py') == {'subcommand-output': [4]}


def test_argv_home_is_main_only():
    # main() reads it once into an Invocation; the rest of main.py and the CLI may not.
    src = "import sys\ndef main():\n    run(sys.argv)\ndef other():\n    return sys.argv[1]"
    assert _hits(src, 'reveal/main.py') == {'argv': [5]}
    assert _hits("import sys\nsys.argv[1:]", 'reveal/cli/parser.py') == {'argv': [2]}


@pytest.mark.parametrize('src, rel', [
    ("print('x')\nsys.exit(1)", 'reveal/cli/commands/foo.py'),
    ("print('x')\nsys.exit(1)", 'reveal/main.py'),
    ("print('x')", 'reveal/rendering/adapters/foo.py'),
    ("print('x')", 'reveal/display/foo.py'),
    ("print('x')", 'reveal/adapters/foo/renderer.py'),
    ("print('x')", 'reveal/adapters/claude/render_messages.py'),
    ("class FooRenderer:\n    def render(self):\n        print('x')", PLAIN),
    ("if __name__ == '__main__':\n    print('x')\n    sys.exit(0)", PLAIN),
    ("sys.exit(1)", 'reveal/mcp_server.py'),
])
def test_exit_and_print_homes(src, rel):
    assert _hits(src, rel) == {}


def test_mcp_server_is_not_a_print_home():
    # stdout is the JSON-RPC stream there.
    assert _hits("print('x')", 'reveal/mcp_server.py') == {'print': [1]}


def test_renderer_class_does_not_excuse_exit():
    assert _hits("class FooRenderer:\n    def r(self):\n        sys.exit(1)") == {'exit': [3]}


@pytest.mark.parametrize('src', [
    "p.rglob('*')  # boundary-ok: walker -- reveal's own docs",
    "# boundary-ok: walker -- reveal's own docs\np.rglob('*')",
    "list(\n    p.rglob('*'),  # boundary-ok: walker -- multi-line call\n)",
])
def test_boundary_ok_marker_suppresses(src):
    assert _hits(src) == {}


def test_marker_is_per_rule_and_must_be_adjacent():
    assert _hits("p.rglob('*')  # boundary-ok: print -- wrong rule") == {'walker': [1]}
    assert _hits("# boundary-ok: walker -- too far\n\np.rglob('*')") == {'walker': [3]}


def test_compare_reports_regressions_and_stale_entries():
    base = {'walker': {'a.py': 2, 'b.py': 1}}
    now = {'walker': {'a.py': 3, 'c.py': 1}}
    regressions, stale = cb.compare(base, now)
    assert regressions == [('walker', 'a.py', 2, 3), ('walker', 'c.py', 0, 1)]
    assert stale == [('walker', 'b.py', 1, 0)]


@pytest.fixture
def ratchet(tmp_path, monkeypatch):
    """Point main() at a temp baseline and a fake scan result."""
    baseline = tmp_path / 'baseline.json'
    monkeypatch.setattr(cb, 'BASELINE', baseline)
    state = {'found': {rule: {} for rule in cb.RULES}}
    monkeypatch.setattr(cb, 'scan', lambda: state['found'])

    def run(found, base=None, argv=()):
        state['found'] = {rule: found.get(rule, {}) for rule in cb.RULES}
        if base is not None:
            baseline.write_text(json.dumps(base), encoding='utf-8')
        return cb.main(list(argv))
    run.baseline = baseline
    return run


def test_main_passes_at_baseline(ratchet, capsys):
    assert ratchet({'walker': {'a.py': [1, 2]}}, {'walker': {'a.py': 2}}) == 0
    assert 'boundary ratchet OK' in capsys.readouterr().out


def test_main_fails_on_growth_and_names_the_seam(ratchet, capsys):
    assert ratchet({'walker': {'a.py': [1, 2, 3]}}, {'walker': {'a.py': 2}}) == 1
    out = capsys.readouterr().out
    assert 'a.py: 2 -> 3' in out and '_walk_code_files' in out


def test_main_fails_on_stale_baseline_so_counts_only_fall(ratchet, capsys):
    assert ratchet({'walker': {'a.py': [1]}}, {'walker': {'a.py': 2}}) == 1
    assert '--update-baseline' in capsys.readouterr().out


def test_update_baseline_lowers_counts(ratchet):
    assert ratchet({'walker': {'a.py': [1]}}, {'walker': {'a.py': 2}}, ['--update-baseline']) == 0
    assert json.loads(ratchet.baseline.read_text(encoding='utf-8'))['walker'] == {'a.py': 1}


def test_update_baseline_refuses_to_raise_counts(ratchet):
    base = {'walker': {'a.py': 1}}
    assert ratchet({'walker': {'a.py': [1, 2]}}, base, ['--update-baseline']) == 1
    assert json.loads(ratchet.baseline.read_text(encoding='utf-8')) == base
