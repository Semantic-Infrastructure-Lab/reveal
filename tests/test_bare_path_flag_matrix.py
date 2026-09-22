"""Routing-seam conformance: global flag x bare-path invocation-shape matrix (BACK-1362,
bare-path dimension).

`tests/test_flag_routing_matrix.py` covers the URI (`scheme://...`) path;
`tests/test_subcommand_flag_matrix.py` covers subcommands (`reveal overview`, ...). The third
invocation path is a bare `reveal <path> [flags]` — one shared parser
(`reveal/cli/parser.py::create_argument_parser`), so every one of the five global flags is
always *declared* here; the question is whether each of the several distinct code branches
`reveal/cli/routing/file.py::handle_file_or_directory` dispatches to actually reads it.

Unlike the URI/subcommand dimensions (one parser per scheme/subcommand -> a clean per-module
AST scan), a bare path fans out to several branches living in the same module
(`_handle_directory_path`), so this matrix is keyed by invocation *shape* (which branch fires)
rather than by module. Classification was derived by hand-reading each branch (not an AST scan
-- the branches share a module, so a naive `args.<flag>` scan would over- and under-attribute
across branches) and is pinned here by two live-behavior probe tests instead of a derived-vs-
recorded AST diff: `test_honored_cell_changes_output` (an "honored" cell must produce different
output with/without the flag) and `test_not_applicable_cell_output_is_identical` (a
"not-applicable" cell must produce IDENTICAL output -- if it starts mattering, this test breaks
and the cell needs reclassifying, not a silent drift).

Found and fixed this session: `--meta`'s directory summary (`_collect_dir_stats`) walked raw
`os.walk()` with no filtering at all -- `.gitignore`, `--exclude`, and even `.git/` internals
were silently included, unlike every sibling bare-path directory view (tree, `--files`,
`--grep`), which all share `display.filtering.PathFilter`. Now wired the same way.

Cell classification, per (shape, flag):
  honored           the branch reads the flag (directly or by forwarding into a shared seam,
                     e.g. handle_uri's inject_query_flags) and it observably changes output.
                     Proven by a PROBES entry.
  not-applicable    the flag is always declared (shared parser) but this branch's output has
                     no dimension the flag could affect -- reason required. Proven by
                     test_not_applicable_cell_output_is_identical (output must not change).
  forwarded         the branch is a pure passthrough into another invocation path already
                     covered by a different matrix (ast:// via handle_uri for --name/--type/
                     --sort; the `check` subcommand for --check) -- no new classification here,
                     see the referenced matrix.

Regenerate is manual (hand-edit + rerun the probe tests) -- there is no `--write` here since
the classification isn't AST-derivable the way the other two dimensions are.
"""
import io
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import yaml

MATRIX_PATH = Path(__file__).parent / 'bare_path_flag_matrix.yaml'

FLAGS = ('verbose', 'all', 'since', 'until', 'respect_gitignore')

_FLAG_TO_CLI = {
    'verbose': '--verbose',
    'all': '--all',
    'since': '--since',
    'until': '--until',
    'respect_gitignore': '--no-gitignore',  # value=False means "pass --no-gitignore"
}

# (shape, flag) -> (extra argv after {tree}, value). Proves the cell is genuinely honored.
PROBES = {
    ('dir_tree', 'respect_gitignore'): ([], False),
    ('dir_files', 'respect_gitignore'): (['--files'], False),
    ('dir_meta', 'respect_gitignore'): (['--meta'], False),
    ('dir_grep', 'respect_gitignore'): (['--grep', 'return 2'], False),
}


def load_recorded():
    return yaml.safe_load(MATRIX_PATH.read_text(encoding='utf-8'))['shapes']


def test_every_cell_is_classified():
    bad = []
    for shape, cells in load_recorded().items():
        for flag, cell in cells.items():
            review = cell.get('review')
            if review not in ('honored', 'not-applicable', 'forwarded'):
                bad.append((shape, flag, review))
            elif review == 'not-applicable' and not cell.get('reason'):
                bad.append((shape, flag, 'not-applicable needs a reason'))
            elif review == 'forwarded' and not cell.get('see'):
                bad.append((shape, flag, 'forwarded needs a `see` pointer to the other matrix'))
    assert not bad, f'unclassified cells: {bad}'


def test_probes_only_target_honored_cells():
    recorded = load_recorded()
    for (shape, flag) in PROBES:
        assert recorded[shape][flag]['review'] == 'honored', (
            f'{shape}/{flag} has a probe but is not marked honored')


def _run_bare(argv):
    from reveal.cli.parser import create_argument_parser
    from reveal.cli.routing.file import handle_file_or_directory
    args = create_argument_parser('test').parse_args(argv)
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        try:
            handle_file_or_directory(args.path, args)
        except SystemExit:
            pass
    return out.getvalue()


@pytest.fixture(scope='module')
def probe_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('bare_path_probe_tree')
    (root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    (root / 'ignored.py').write_text('def b():\n    return 2\n', encoding='utf-8')
    (root / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    git = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'add', 'a.py', '.gitignore'], check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'init'], check=True)
    return root


@pytest.mark.parametrize('shape,flag', sorted(PROBES))
def test_honored_cell_changes_output(shape, flag, probe_tree):
    extra, value = PROBES[shape, flag]
    baseline = _run_bare([str(probe_tree), *extra])
    cli_flag = _FLAG_TO_CLI[flag]
    changed_argv = [str(probe_tree), *extra, cli_flag] if isinstance(value, bool) else \
        [str(probe_tree), *extra, cli_flag, str(value)]
    changed = _run_bare(changed_argv)
    assert baseline != changed, (
        f'bare-path {shape} claims --{flag} is honored but output is identical with/without it')


# Every declared-but-not-applicable cell: run with and without the flag, assert IDENTICAL
# output. This is the regression guard for the opposite failure mode from PROBES -- a cell
# marked not-applicable that quietly starts mattering (or stops) without anyone reclassifying it.
_NOT_APPLICABLE_ARGV = {
    'dir_tree': [],
    'dir_files': ['--files'],
    'dir_meta': ['--meta'],
    'dir_grep': ['--grep', 'return'],
    'file_default': ['{file}'],
    'file_grep': ['{file}', '--grep', 'return'],
}


def _not_applicable_cases():
    recorded = load_recorded()
    cases = []
    for shape, cells in recorded.items():
        if shape not in _NOT_APPLICABLE_ARGV:
            continue
        for flag, cell in cells.items():
            if cell.get('review') == 'not-applicable':
                cases.append((shape, flag))
    return cases


@pytest.mark.parametrize('shape,flag', sorted(_not_applicable_cases()))
def test_not_applicable_cell_output_is_identical(shape, flag, probe_tree):
    template = _NOT_APPLICABLE_ARGV[shape]
    file_path = probe_tree / 'a.py'
    if shape.startswith('dir_'):
        base_argv = [str(probe_tree), *template]
    else:
        base_argv = [a.replace('{file}', str(file_path)) for a in template]

    baseline = _run_bare(base_argv)
    cli_flag = _FLAG_TO_CLI[flag]
    changed_argv = [*base_argv, cli_flag] if flag != 'since' and flag != 'until' else \
        [*base_argv, cli_flag, '2099-01-01']
    changed = _run_bare(changed_argv)
    assert baseline == changed, (
        f'bare-path {shape} marks --{flag} not-applicable but output changed -- '
        f'reclassify as honored (with a PROBES entry) or investigate the regression')


if __name__ == '__main__':
    print(yaml.safe_dump(load_recorded(), sort_keys=True))
