"""Routing-seam conformance: global flag x URI adapter matrix (BACK-1362).

A global CLI flag can be honored on one invocation path and silently ignored on
another (>=32 tasks in the 2026-09-21 self-review). This test derives, for every
registered URI scheme, HOW each flag reaches the adapter and compares that with the
checked-in matrix `tests/flag_routing_matrix.yaml`. A new adapter, or a new way a flag
is consumed, changes the derived matrix and fails CI until the yaml is updated on
purpose. Re-generate with `python tests/test_flag_routing_matrix.py --write`; it keeps
hand-written `review`/`reason` fields.

Channels by which a flag reaches a URI adapter (only these exist):
  declared          adapter lists the flag in CLI_QUERY_FLAGS; handle_uri injects it
  structure-param   get_structure() has a parameter named after the flag (auto-discovered)
  adapter-reads-args  adapter/renderer module reads `args.<flag>` itself
  routing-special   renderer declares ACCEPTS_TOP (all/verbose -> its render_structure(top=))
A flag with no channel is accepted and silently does nothing. Each such cell must be
classified `not-applicable` (with a reason) or stays `unreviewed` -- the honest
"nobody has decided yet", which is the backlog this matrix exists to make visible.

Scope: URI path only. Bare-path and subcommand invocation, env vars and .reveal.yaml
keys are the next dimensions of BACK-1362.
"""
import ast
import functools
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import yaml

from conftest import write_gitignore_probe_files

MATRIX_PATH = Path(__file__).parent / 'flag_routing_matrix.yaml'
REVEAL_PKG = Path(__file__).resolve().parent.parent / 'reveal'

# The global flags routed by cli/routing/flag_specs.py (a test below keeps this in step).
FLAGS = ('verbose', 'all', 'since', 'until', 'respect_gitignore')

# Adapters whose --all/--verbose reach a renderer-level `top` kwarg via ACCEPTS_TOP
# (handle_uri._render_structure_top_kwargs, BACK-1226/BACK-1379) are detected below,
# not hard-coded here -- ROUTING_SPECIAL is only for routing that isn't derivable that way.
ROUTING_SPECIAL = {}

# Routing/parser modules read args.<flag> to implement the seam itself, not to honor it.
_SEAM_FILES = {'cli/parser.py', 'cli/routing/uri.py', 'main.py'}

# Honored cells that can be proven by output difference: scheme -> flag -> probe URI.
# Probes must exceed the adapter's default cap or the flag has nothing to change.
# scheme/flag -> (probe URI, value to give the flag). `{tree}` is a throwaway git repo with
# one commit, a .gitignore and one ignored file; `{pkg}`/`{tests}` are conftest's
# flag_probe_corpus, sized past every cap below. Neither depends on what the checkout
# under test happens to contain, and neither costs what probing reveal/ itself did
# (6-59s per probe, BACK-1451).
PROBES = {
    ('hotspots', 'all'): ('hotspots://{pkg}', True),
    ('overview', 'all'): ('overview://{pkg}', True),
    ('overview', 'verbose'): ('overview://{pkg}', True),
    ('git', 'since'): ('git://{tree}', '2099-01-01'),
    ('git', 'until'): ('git://{tree}', '1970-01-02'),
    ('stats', 'respect_gitignore'): ('stats://{tree}', False),
    ('overview', 'respect_gitignore'): ('overview://{tree}', False),
    # BACK-1379: adapters whose --all now lifts a real default cap.
    ('ast', 'all'): ('ast://{pkg}', True),
    ('calls', 'all'): ('calls://{pkg}?rank=callers', True),
    ('patches', 'all'): ('patches://{tests}', True),
    ('testability', 'all'): ('testability://{pkg}', True),
    ('stats', 'all'): ('stats://{pkg}?hotspots=true', True),
    ('architecture', 'all'): ('architecture://{pkg}', True),
    ('deps', 'all'): ('deps://{pkg}', True),
    ('git', 'all'): ('git://{tree}?type=log', True),
    # BACK-1379: --verbose slice.
    ('git', 'verbose'): ('git://{tree}/a.py?type=blame', True),
    ('depends', 'verbose'): ('depends://{pkg}', True),
    ('pack', 'verbose'): ('pack://{pkg}', True),
    # BACK-1379: respect_gitignore slice.
    ('classify', 'respect_gitignore'): ('classify://{tree}', False),
    # BACK-1386: every walker honors it (probe_tree's *ignored* files).
    ('architecture', 'respect_gitignore'): ('architecture://{tree}', False),
    ('ast', 'respect_gitignore'): ('ast://{tree}', False),
    ('calls', 'respect_gitignore'): ('calls://{tree}?uncalled', False),
    ('contracts', 'respect_gitignore'): ('contracts://{tree}', False),
    ('depends', 'respect_gitignore'): ('depends://{tree}/a.py', False),
    ('deps', 'respect_gitignore'): ('deps://{tree}', False),
    ('hotspots', 'respect_gitignore'): ('hotspots://{tree}', False),
    ('imports', 'respect_gitignore'): ('imports://{tree}', False),
    ('markdown', 'respect_gitignore'): ('markdown://{tree}', False),
    ('pack', 'respect_gitignore'): ('pack://{tree}', False),
    ('patches', 'respect_gitignore'): ('patches://{tree}', False),
    ('surface', 'respect_gitignore'): ('surface://{tree}', False),
    ('testability', 'respect_gitignore'): ('testability://{tree}', False),
    ('trace', 'respect_gitignore'): ('trace://{tree}?from=a', False),
    ('diff', 'respect_gitignore'): ('diff://{tree}:{churn_tree}', False),
    # BACK-1379/BACK-1388: since/until slice. Originally pointed at a real repo file
    # (reveal/adapters/stats) on the theory that a future since= excludes every real
    # commit "regardless of clone depth" -- wrong: that file's churn score is only
    # legible with the many real commits a full dev clone has. CI's actual checkout
    # (actions/checkout, depth 1) has exactly one commit for every file, so
    # since=2099-01-01 (0 touches) vs. unfiltered (1 touch) didn't move the rendered
    # score enough to differ -- byte-identical on every one of 15 CI jobs, reproduced
    # locally via `git clone --depth 1`. Fixed the same way as the git-all bug
    # (BACK-1379): build the commit history the probe needs inside the test itself
    # (churn_tree) instead of trusting the ambient checkout's depth.
    # No probe for codex/since+until: its only fixture path is monkeypatching
    # CODEX_HOME/CODEX_DB (see tests/adapters/test_codex_adapter.py), which a
    # (uri, value) PROBES tuple can't express.
    ('stats', 'since'): ('stats://{churn_tree}?hotspots=true', '2099-01-01'),
}


def _flag_readers(flag):
    """Files under reveal/ (relative posix paths) that read args.<flag> directly."""
    return _readers_by_flag()[flag]


@functools.cache
def _readers_by_flag():
    """flag -> files reading args.<flag>; one AST pass over reveal/ for all FLAGS.

    Source files don't change within a run, so every derive_matrix() call shares it
    (it was one full parse per flag per call, ~10s of each matrix test, BACK-1451).
    """
    found = {flag: set() for flag in FLAGS}
    for path in REVEAL_PKG.rglob('*.py'):
        rel = path.relative_to(REVEAL_PKG).as_posix()
        if rel in _SEAM_FILES or rel.startswith('cli/commands/'):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'getattr' and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == 'args'
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in found):
                found[node.args[1].value].add(rel)
            elif (isinstance(node, ast.Attribute) and node.attr in found
                    and isinstance(node.value, ast.Name) and node.value.id == 'args'):
                found[node.attr].add(rel)
    return found


# Scaffold/test adapters register themselves only when something imports them, so which of
# them exist depends on test order. The registry-integrity test discards them the same way.
_NON_PRODUCTION = {'adapters/demo.py', 'adapters/test.py'}


def _adapter_rel_path(cls):
    """Path of the adapter's module relative to reveal/, or None if it lives outside the
    package (a plugin, or an adapter a test registered)."""
    file = Path(sys.modules[cls.__module__].__file__).resolve()
    try:
        return file.relative_to(REVEAL_PKG)
    except ValueError:
        return None


def _is_shipped(cls):
    rel = _adapter_rel_path(cls)
    return rel is not None and rel.as_posix() not in _NON_PRODUCTION


def _adapter_scope(cls):
    """Relative path prefix owned by an adapter: its package dir, or its own file."""
    rel = _adapter_rel_path(cls)
    return rel.parent.as_posix() + '/' if rel.parent.as_posix() != 'adapters' else rel.as_posix()


def derive_matrix():
    import inspect

    from reveal import adapters  # noqa: F401  (registers every scheme)
    from reveal.adapters import base
    from reveal.adapters.base import get_renderer_class

    readers = {flag: _flag_readers(flag) for flag in FLAGS}
    matrix = {}
    for scheme in sorted(base.list_supported_schemes()):
        cls = base.get_adapter_class(scheme)
        if not _is_shipped(cls):
            continue
        scope = _adapter_scope(cls)
        params = (set(inspect.signature(cls.get_structure).parameters)
                  if hasattr(cls, 'get_structure') else set())
        declared = dict(getattr(cls, 'CLI_QUERY_FLAGS', {}))
        renderer_cls = get_renderer_class(scheme)
        accepts_top = getattr(renderer_cls, 'ACCEPTS_TOP', False) is True
        cells = {}
        for flag in FLAGS:
            via = []
            if declared.get(flag):
                via.append('declared')
            if flag in params:
                via.append('structure-param')
            if any(r.startswith(scope) for r in readers[flag]):
                via.append('adapter-reads-args')
            if accepts_top and flag in ('all', 'verbose'):
                via.append('routing-special')
            if flag in ROUTING_SPECIAL.get(scheme, ()):
                via.append('routing-special')
            cells[flag] = via
        matrix[scheme] = cells
    return matrix


def load_recorded():
    return yaml.safe_load(MATRIX_PATH.read_text(encoding='utf-8'))['adapters']


def write_matrix():
    """Regenerate the yaml from the derivation, keeping hand-written review fields."""
    old = load_recorded() if MATRIX_PATH.exists() else {}
    out = {}
    for scheme, cells in derive_matrix().items():
        out[scheme] = {}
        for flag, via in cells.items():
            prev = (old.get(scheme) or {}).get(flag) or {}
            cell = {'via': via}
            if not via:
                cell['review'] = prev.get('review', 'unreviewed')
                if prev.get('reason'):
                    cell['reason'] = prev['reason']
            out[scheme][flag] = cell
    header = (
        '# Generated by tests/test_flag_routing_matrix.py --write (BACK-1362).\n'
        '# `via` is derived from code; `review`/`reason` on cells with empty `via` are\n'
        '# hand-written: not-applicable (say why) or unreviewed (flag is accepted and\n'
        '# silently ignored -- decide: honor it, reject it, or mark not-applicable).\n')
    MATRIX_PATH.write_text(
        header + yaml.safe_dump({'flags': list(FLAGS), 'paths': ['uri'], 'adapters': out},
                                sort_keys=True), encoding='utf-8')


# --------------------------------------------------------------------------- tests

def test_recorded_matrix_matches_derived_channels():
    derived, recorded = derive_matrix(), load_recorded()
    assert set(recorded) == set(derived), (
        f'schemes added/removed: {sorted(set(recorded) ^ set(derived))} '
        f'-- run `python tests/test_flag_routing_matrix.py --write` and classify')
    drift = [(s, f, recorded[s][f]['via'], via)
             for s, cells in derived.items() for f, via in cells.items()
             if recorded[s][f]['via'] != via]
    assert not drift, f'flag routing changed (scheme, flag, recorded, derived): {drift}'


def test_unshipped_adapters_do_not_change_the_matrix():
    """demo:// registers only when imported, so it appears in some test orders and not
    others; a plugin or a test-registered adapter would do the same. None may leak in."""
    before = derive_matrix()
    import reveal.adapters.demo  # noqa: F401
    assert derive_matrix() == before
    assert 'demo' not in before and 'test' not in before


def test_every_silent_cell_is_classified():
    bad = []
    for scheme, cells in load_recorded().items():
        for flag, cell in cells.items():
            if cell['via']:
                continue
            review = cell.get('review')
            if review not in ('unreviewed', 'not-applicable'):
                bad.append((scheme, flag, review))
            elif review == 'not-applicable' and not cell.get('reason'):
                bad.append((scheme, flag, 'not-applicable needs a reason'))
    assert not bad, f'unclassified cells: {bad}'


def test_flags_match_the_flag_spec_table():
    from reveal.cli.routing.flag_specs import FLAG_SPECS

    # Universal specs (sort=, limit=) reach every adapter's query pipeline alike, so there is
    # no per-adapter routing for the matrix to record; declaration-based ones must be columns.
    assert set(FLAGS) >= {spec.dest for spec in FLAG_SPECS if spec.universal is None}, (
        'a FlagSpec exists for a flag this matrix does not cover')


def test_probes_only_target_honored_cells():
    recorded = load_recorded()
    for (scheme, flag) in PROBES:
        assert recorded[scheme][flag]['via'], f'{scheme}/{flag} has a probe but no channel'


def _render(uri, **flags):
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import handle_uri

    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        handle_uri(uri, None, _default_args(**flags))
    return out.getvalue()


@pytest.fixture(scope='module')
def probe_tree(tmp_path_factory):
    import subprocess

    root = tmp_path_factory.mktemp('probe_tree')
    tracked = write_gitignore_probe_files(root)
    git = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'add', *tracked], check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'init', '--date', '2020-01-01T00:00:00'],
                   check=True, env={**__import__('os').environ, 'GIT_COMMITTER_DATE': '2020-01-01T00:00:00'})
    # git://{tree}?type=log's default cap is 20 commits (refs.get_ref_structure); add
    # enough follow-up commits that --all (limit=1000000, BACK-1379) visibly differs
    # from the default instead of both showing the same short history.
    log_path = root / 'log.txt'
    for i in range(1, 26):
        log_path.write_text(f'commit {i}\n', encoding='utf-8')
        subprocess.run([*git, 'add', 'log.txt'], check=True)
        date = f'2020-01-{i + 1:02d}T00:00:00'
        subprocess.run([*git, 'commit', '-q', '-m', f'log {i}', '--date', date],
                       check=True, env={**__import__('os').environ, 'GIT_COMMITTER_DATE': date})
    return root


@pytest.fixture(scope='module')
def churn_tree(tmp_path_factory):
    """A file with real complexity (clears the hotspot threshold) churned across many
    commits entirely within this fixture -- unlike a path into the ambient repo, its
    history doesn't depend on how deep the checkout under test happens to be."""
    import subprocess
    import os as _os

    root = tmp_path_factory.mktemp('churn_tree')
    code = (
        'def complex_func(x):\n'
        '    if x > 0:\n'
        '        if x > 10:\n'
        '            if x > 100:\n'
        '                return "huge"\n'
        '            return "big"\n'
        '        for i in range(x):\n'
        '            if i % 2 == 0:\n'
        '                x += 1\n'
        '            elif i % 3 == 0:\n'
        '                x -= 1\n'
        '        return x\n'
        '    elif x < 0:\n'
        '        while x < 0:\n'
        '            x += 1\n'
        '    return x\n'
    )
    (root / 'a.py').write_text(code, encoding='utf-8')
    git = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'add', 'a.py'], check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'init', '--date', '2020-01-01T00:00:00'],
                   check=True, env={**_os.environ, 'GIT_COMMITTER_DATE': '2020-01-01T00:00:00'})
    for i in range(1, 26):
        (root / 'a.py').write_text(f'{code}\n# churn {i}\n', encoding='utf-8')
        subprocess.run([*git, 'add', 'a.py'], check=True)
        date = f'2020-01-{i + 1:02d}T00:00:00'
        subprocess.run([*git, 'commit', '-q', '-m', f'churn {i}', '--date', date],
                       check=True, env={**_os.environ, 'GIT_COMMITTER_DATE': date})
    return root


@pytest.mark.parametrize('scheme,flag', sorted(PROBES))
def test_honored_cell_changes_output(scheme, flag, probe_tree, churn_tree, flag_probe_corpus,
                                     monkeypatch):
    uri, value = PROBES[scheme, flag]
    # Relative {pkg}/{tests}, as the reveal/ probes were: no drive-letter paths in URIs.
    monkeypatch.chdir(flag_probe_corpus)
    uri = (uri.replace('{tree}', str(probe_tree)).replace('{churn_tree}', str(churn_tree))
           .replace('{pkg}', 'pkg').replace('{tests}', 'tests'))
    assert _render(uri) != _render(uri, **{flag: value}), (
        f'{scheme}:// claims a channel for --{flag} but the output is identical on {uri}')


if __name__ == '__main__':
    if '--write' in sys.argv:
        write_matrix()
        print(f'wrote {MATRIX_PATH}')
    else:
        print(yaml.safe_dump(derive_matrix(), sort_keys=True))
