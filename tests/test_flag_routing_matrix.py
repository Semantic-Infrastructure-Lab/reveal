"""Routing-seam conformance: global flag x URI adapter matrix (BACK-1362).

A global CLI flag can be honored on one invocation path and silently ignored on
another (>=32 tasks in the 2026-09-21 self-review). This test derives, for every
registered URI scheme, HOW each flag reaches the adapter and compares that with the
checked-in matrix `tests/flag_routing_matrix.yaml`. A new adapter, or a new way a flag
is consumed, changes the derived matrix and fails CI until the yaml is updated on
purpose. Re-generate with `python tests/test_flag_routing_matrix.py --write`; it keeps
hand-written `review`/`reason` fields.

Channels by which a flag reaches a URI adapter (only these exist):
  declared          adapter sets ResourceAdapter.<FLAG>_QUERY; handle_uri injects it
  structure-param   get_structure() has a parameter named after the flag (auto-discovered)
  adapter-reads-args  adapter/renderer module reads `args.<flag>` itself
  routing-special   hard-coded in cli/routing/uri.py (overview:// only)
A flag with no channel is accepted and silently does nothing. Each such cell must be
classified `not-applicable` (with a reason) or stays `unreviewed` -- the honest
"nobody has decided yet", which is the backlog this matrix exists to make visible.

Scope: URI path only. Bare-path and subcommand invocation, env vars and .reveal.yaml
keys are the next dimensions of BACK-1362.
"""
import ast
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import yaml

MATRIX_PATH = Path(__file__).parent / 'flag_routing_matrix.yaml'
REVEAL_PKG = Path(__file__).resolve().parent.parent / 'reveal'

# flag -> ResourceAdapter attribute that declares its query fragment
FLAGS = {'verbose': 'VERBOSE_QUERY', 'all': 'ALL_RESULTS_QUERY'}

# cli/routing/uri.py::_render_structure_top_kwargs forwards both flags to this renderer.
# The dynamic test below is what catches this going stale.
ROUTING_SPECIAL = {'overview': set(FLAGS)}

# Routing/parser modules read args.<flag> to implement the seam itself, not to honor it.
_SEAM_FILES = {'cli/parser.py', 'cli/routing/uri.py', 'main.py'}

# Honored cells that can be proven by output difference: scheme -> flag -> probe URI.
# Probes must exceed the adapter's default cap or the flag has nothing to change.
PROBES = {
    ('hotspots', 'all'): 'hotspots://reveal/adapters',
    ('overview', 'all'): 'overview://reveal/adapters',
    ('overview', 'verbose'): 'overview://reveal/adapters',
}


def _flag_readers(flag):
    """Files under reveal/ (relative posix paths) that read args.<flag> directly."""
    found = set()
    for path in REVEAL_PKG.rglob('*.py'):
        rel = path.relative_to(REVEAL_PKG).as_posix()
        if rel in _SEAM_FILES or rel.startswith('cli/commands/'):
            continue
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
                found.add(rel)
                break
    return found


def _adapter_scope(cls):
    """Relative path prefix owned by an adapter: its package dir, or its own file."""
    file = Path(sys.modules[cls.__module__].__file__).resolve()
    rel = file.relative_to(REVEAL_PKG)
    return rel.parent.as_posix() + '/' if rel.parent.as_posix() != 'adapters' else rel.as_posix()


def derive_matrix():
    import inspect

    from reveal import adapters  # noqa: F401  (registers every scheme)
    from reveal.adapters import base

    readers = {flag: _flag_readers(flag) for flag in FLAGS}
    matrix = {}
    for scheme in sorted(base.list_supported_schemes()):
        cls = base.get_adapter_class(scheme)
        scope = _adapter_scope(cls)
        params = (set(inspect.signature(cls.get_structure).parameters)
                  if hasattr(cls, 'get_structure') else set())
        cells = {}
        for flag, attr in FLAGS.items():
            via = []
            if isinstance(getattr(cls, attr, None), str) and getattr(cls, attr):
                via.append('declared')
            if flag in params:
                via.append('structure-param')
            if any(r.startswith(scope) for r in readers[flag]):
                via.append('adapter-reads-args')
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


@pytest.mark.parametrize('scheme,flag', sorted(PROBES))
def test_honored_cell_changes_output(scheme, flag):
    uri = PROBES[scheme, flag]
    assert _render(uri) != _render(uri, **{flag: True}), (
        f'{scheme}:// claims a channel for --{flag} but the output is identical on {uri}')


if __name__ == '__main__':
    if '--write' in sys.argv:
        write_matrix()
        print(f'wrote {MATRIX_PATH}')
    else:
        print(yaml.safe_dump(derive_matrix(), sort_keys=True))
