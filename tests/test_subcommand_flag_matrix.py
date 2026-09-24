"""Routing-seam conformance: global flag x subcommand matrix (BACK-1362, subcommand dimension).

`tests/test_flag_routing_matrix.py` covers the URI (`scheme://...`) path. Subcommands
(`reveal overview`, `reveal check`, ...) are a separate invocation path: each builds its
own `argparse.ArgumentParser` in `reveal/cli/commands/<name>.py` (see `main._SUBCOMMANDS`),
so declaring one of the five global flags there is a per-subcommand choice, not something
inherited automatically the way `--format`/`--copy` are via `_build_global_options_parser()`.

This surfaced a distinct bug shape from the URI dimension: a subcommand parser *inheriting*
--verbose from the shared parent, with nothing in that subcommand's own code ever reading
`args.verbose` -- accepted, parsed, and silently thrown away. Found and fixed for
architecture/deps/hotspots/testability this session (BACK-1362); this test locks the
finding in so a future subcommand can't regress the same way unnoticed.

Cell classification, per (subcommand, flag):
  not-declared     the subcommand's own parser doesn't accept the flag at all -- passing it
                    is a loud `argparse` error ("unrecognized arguments"), which already
                    satisfies BACK-1362's bar (honored or loudly rejected). Auto-classified,
                    no review needed.
  declared-read     the flag is declared AND read (directly, or via a small documented
                    cross-file forward -- see _CROSS_FILE_READERS) somewhere in scope.
                    Still needs a hand `review: honored` plus, ideally, a PROBES entry
                    proving an output difference -- "read" doesn't guarantee "used".
  declared-unused   the flag is declared but no read was found anywhere in scope -- the
                    silent-no-op shape. Must carry `review: not-applicable` with a reason
                    (nothing in this subcommand's output changes based on the flag) or
                    `review: honored` if the automated scan simply missed the wiring
                    (extend _CROSS_FILE_READERS instead of guessing). An unreviewed cell
                    here fails CI.

Regenerate with `python tests/test_subcommand_flag_matrix.py --write` (keeps hand-written
`review`/`reason` fields, exactly like the URI matrix's `--write`).
"""
import ast
import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import yaml

MATRIX_PATH = Path(__file__).parent / 'subcommand_flag_matrix.yaml'
REVEAL_PKG = Path(__file__).resolve().parent.parent / 'reveal'

# Keep in step with test_flag_routing_matrix.py's FLAGS -- same five global flags, other
# invocation path.
FLAGS = ('verbose', 'all', 'since', 'until', 'respect_gitignore')

# name -> (module_path, parser_fn, runner_fn); mirrors reveal/main.py's _SUBCOMMANDS table.
# Not imported directly from main.py to avoid pulling in main's sys.argv-inspection side
# effects at collection time; a test below keeps this list honest against main.py's own copy.
SUBCOMMANDS = {
    'architecture': ('reveal.cli.commands.architecture', 'create_architecture_parser', 'run_architecture'),
    'check':        ('reveal.cli.commands.check',        'create_check_parser',        'run_check'),
    'contracts':    ('reveal.cli.commands.contracts',    'create_contracts_parser',    'run_contracts'),
    'deps':         ('reveal.cli.commands.deps',         'create_deps_parser',         'run_deps'),
    'dev':          ('reveal.cli.commands.dev',          'create_dev_parser',          'run_dev'),
    'health':       ('reveal.cli.commands.health',       'create_health_parser',       'run_health'),
    'hotspots':     ('reveal.cli.commands.hotspots',     'create_hotspots_parser',     'run_hotspots'),
    'offline':      ('reveal.cli.commands.offline',      'create_offline_parser',      'run_offline'),
    'overview':     ('reveal.cli.commands.overview',     'create_overview_parser',     'run_overview'),
    'pack':         ('reveal.cli.commands.pack',         'create_pack_parser',         'run_pack'),
    'review':       ('reveal.cli.commands.review',       'create_review_parser',       'run_review'),
    'scaffold':     ('reveal.cli.commands.scaffold',     'create_scaffold_parser',     'run_scaffold'),
    'surface':      ('reveal.cli.commands.surface',      'create_surface_parser',      'run_surface'),
    'testability':  ('reveal.cli.commands.testability',  'create_testability_parser',  'run_testability'),
    'trace':        ('reveal.cli.commands.trace',        'create_trace_parser',        'run_trace'),
}

# A flag genuinely read by a different module than the subcommand's own, because the
# subcommand forwards `args` wholesale into a shared helper (e.g. check -> file_checker).
# Extend this, don't guess at cross-file wiring by other means.
_CROSS_FILE_READERS = {
    'check': ('reveal/cli/file_checker.py',),
}

# Cells provably honored by an observable output difference (mirrors PROBES in
# test_flag_routing_matrix.py). (subcommand, flag) -> (extra argv, value for the flag).
# `{pkg}`/`{tests}` are conftest's flag_probe_corpus (BACK-1451), `{tree}` probe_tree below.
PROBES = {
    ('architecture', 'verbose'): (['{pkg}'], True),
    ('deps', 'verbose'): (['{pkg}'], True),
    ('hotspots', 'verbose'): (['{pkg}'], True),
    ('testability', 'verbose'): (['{pkg}', '--tests', '{tests}'], True),
    ('check', 'respect_gitignore'): (['{tree}'], False),
    ('pack', 'since'): (['{tree}'], '2099-01-01'),
    ('overview', 'all'): (['{pkg}'], True),
}

_FLAG_TO_CLI = {
    'verbose': '--verbose',
    'all': '--all',
    'since': '--since',
    'until': '--until',
    'respect_gitignore': '--no-gitignore',  # value=False means "pass --no-gitignore"
}


def _module_reads_flag(rel_path: str, flag: str) -> bool:
    path = REVEAL_PKG.parent / rel_path if not rel_path.startswith('reveal/') else REVEAL_PKG / rel_path[len('reveal/'):]
    if not path.exists():
        return False
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        is_getattr = (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'getattr' and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name) and node.args[0].id == 'args'
            and isinstance(node.args[1], ast.Constant) and node.args[1].value == flag)
        is_attr = (
            isinstance(node, ast.Attribute) and node.attr == flag
            and isinstance(node.value, ast.Name) and node.value.id == 'args')
        if is_getattr or is_attr:
            return True
    return False


def _reads_via_shared_seam(name, flag):
    """A subcommand can also route a flag through flag_specs.inject_query_flags -- the
    same generic seam URI adapters use (BACK-1377 shared overview.py with handle_uri).
    That reads args via a variable dest (getattr(args, spec.dest)), not the literal
    `args.<flag>` _module_reads_flag looks for, and is gated on the target adapter's own
    CLI_QUERY_FLAGS declaration, not on anything visible in the subcommand's source."""
    own_rel = 'reveal/' + SUBCOMMANDS[name][0].split('reveal.', 1)[1].replace('.', '/') + '.py'
    src = (REVEAL_PKG.parent / own_rel).read_text(encoding='utf-8')
    if 'inject_query_flags' not in src:
        return False
    from reveal.adapters.base import get_adapter_class
    try:
        adapter_cls = get_adapter_class(name)
    except Exception:
        return False
    return bool(getattr(adapter_cls, 'CLI_QUERY_FLAGS', {}).get(flag))


def derive_matrix():
    matrix = {}
    for name, (modpath, parser_fn, _runner_fn) in SUBCOMMANDS.items():
        mod = importlib.import_module(modpath)
        parser = getattr(mod, parser_fn)()
        dests = {a.dest for a in parser._actions}
        own_rel = 'reveal/' + modpath.split('reveal.', 1)[1].replace('.', '/') + '.py'
        cross_files = _CROSS_FILE_READERS.get(name, ())
        cells = {}
        for flag in FLAGS:
            if flag not in dests:
                cells[flag] = []
                continue
            read = (_module_reads_flag(own_rel, flag)
                    or any(_module_reads_flag(f, flag) for f in cross_files)
                    or _reads_via_shared_seam(name, flag))
            cells[flag] = ['declared-read'] if read else ['declared-unused']
        matrix[name] = cells
    return matrix


def load_recorded():
    return yaml.safe_load(MATRIX_PATH.read_text(encoding='utf-8'))['subcommands']


def _default_reason(name, flag):
    return (f'--{flag} is not declared on `reveal {name}`\'s own parser -- '
            'argparse rejects it loudly (unrecognized arguments), not a silent gap')


def write_matrix():
    old = load_recorded() if MATRIX_PATH.exists() else {}
    out = {}
    for name, cells in derive_matrix().items():
        out[name] = {}
        for flag, via in cells.items():
            prev = (old.get(name) or {}).get(flag) or {}
            cell = {'via': via}
            if not via:
                cell['review'] = 'not-applicable'
                cell['reason'] = prev.get('reason') or _default_reason(name, flag)
            else:
                cell['review'] = prev.get('review', 'unreviewed')
                if prev.get('reason'):
                    cell['reason'] = prev['reason']
            out[name][flag] = cell
    header = (
        '# Generated by tests/test_subcommand_flag_matrix.py --write (BACK-1362).\n'
        '# `via` is derived from code; `review`/`reason` are hand-written for declared cells:\n'
        '# honored (say how you proved it, ideally a PROBES entry) or not-applicable (say why).\n')
    MATRIX_PATH.write_text(
        header + yaml.safe_dump({'flags': list(FLAGS), 'paths': ['subcommand'], 'subcommands': out},
                                 sort_keys=True), encoding='utf-8')


# --------------------------------------------------------------------------- tests

def test_subcommand_table_matches_main():
    from reveal.main import _SUBCOMMANDS as live
    assert set(SUBCOMMANDS) == set(live), (
        f'subcommand set drifted from main.py: {sorted(set(SUBCOMMANDS) ^ set(live))} -- '
        'update SUBCOMMANDS above to match main._SUBCOMMANDS')
    assert SUBCOMMANDS == dict(live), 'module/parser/runner names drifted from main._SUBCOMMANDS'


def test_recorded_matrix_matches_derived_channels():
    derived, recorded = derive_matrix(), load_recorded()
    assert set(recorded) == set(derived), (
        f'subcommands added/removed: {sorted(set(recorded) ^ set(derived))} -- '
        'run `python tests/test_subcommand_flag_matrix.py --write` and classify')
    drift = [(s, f, recorded[s][f]['via'], via)
             for s, cells in derived.items() for f, via in cells.items()
             if recorded[s][f]['via'] != via]
    assert not drift, f'flag declaration/wiring changed (subcommand, flag, recorded, derived): {drift}'


def test_every_cell_is_classified():
    bad = []
    for name, cells in load_recorded().items():
        for flag, cell in cells.items():
            review = cell.get('review')
            if review not in ('honored', 'not-applicable'):
                bad.append((name, flag, review))
            elif review == 'not-applicable' and not cell.get('reason'):
                bad.append((name, flag, 'not-applicable needs a reason'))
    assert not bad, f'unclassified cells: {bad}'


def test_probes_only_target_honored_cells():
    recorded = load_recorded()
    for (name, flag) in PROBES:
        assert recorded[name][flag]['review'] == 'honored', f'{name}/{flag} has a probe but is not marked honored'


def _run_subcommand(name, argv):
    modpath, parser_fn, runner_fn = SUBCOMMANDS[name]
    mod = importlib.import_module(modpath)
    args = getattr(mod, parser_fn)().parse_args(argv)
    from reveal.cli.global_flags import apply_global_flags
    apply_global_flags(args)
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        try:
            getattr(mod, runner_fn)(args)
        except SystemExit:
            pass
    return out.getvalue()


@pytest.fixture(scope='module')
def probe_tree(tmp_path_factory):
    import subprocess

    root = tmp_path_factory.mktemp('subcommand_probe_tree')
    (root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    (root / 'ignored.py').write_text('def b():\n    return 2\n', encoding='utf-8')
    (root / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    git = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'add', 'a.py', '.gitignore'], check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'init', '--date', '2020-01-01T00:00:00'],
                   check=True, env={**__import__('os').environ, 'GIT_COMMITTER_DATE': '2020-01-01T00:00:00'})
    return root


@pytest.mark.parametrize('name,flag', sorted(PROBES))
def test_honored_cell_changes_output(name, flag, probe_tree, flag_probe_corpus, monkeypatch):
    argv, value = PROBES[name, flag]
    # Relative {pkg}/{tests}, as the reveal/ probes were (see test_flag_routing_matrix.py).
    monkeypatch.chdir(flag_probe_corpus)
    argv = [a.replace('{tree}', str(probe_tree)).replace('{pkg}', 'pkg').replace('{tests}', 'tests')
            for a in argv]
    baseline = _run_subcommand(name, argv)
    cli_flag = _FLAG_TO_CLI[flag]
    if flag == 'respect_gitignore':
        changed_argv = [*argv, '--no-gitignore']
    elif isinstance(value, bool):
        changed_argv = [*argv, cli_flag]
    else:
        changed_argv = [*argv, cli_flag, str(value)]
    changed = _run_subcommand(name, changed_argv)
    assert baseline != changed, (
        f'`reveal {name}` claims --{flag} is honored but output is identical with/without it')


if __name__ == '__main__':
    if '--write' in sys.argv:
        write_matrix()
        print(f'wrote {MATRIX_PATH}')
    else:
        print(yaml.safe_dump(derive_matrix(), sort_keys=True))
