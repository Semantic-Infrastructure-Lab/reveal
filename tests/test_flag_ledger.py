"""Flag ledger (BACK-1514): a flag or query key the user sets is used, or a note names it.

Three layers:

1. Unit tests of ``reveal/cli/routing/ledger.py``: what counts as set, used, carried into the
   query, and what the note says.
2. Regressions for flags that used to vanish silently (``sqlite:// --limit``, ``?bogus=``,
   ``--check`` and ``--exclude`` where they cannot apply).
3. The ratchet: every adapter in the contract harness's ``FIXTURE_URIS`` runs with each
   flag in ``PROBES``. The run must either change the output (the flag was honored) or name
   the flag on stderr (a note). A pair that does neither drops the flag silently, which is
   the bug class the ledger exists for. Today's pairs are ``KNOWN_SILENT`` strict xfails,
   each naming its task. A fix makes its pair XPASS, which fails the run until the row is
   deleted, so the list can only shrink. A new adapter or a new silent path fails at once.

The fixture is the contract harness's tree plus ``_enrich``, so lists have more than one
item and the git file has two commits. "Output changed" still cannot see a flag honored
without visible effect: ``--all`` under a default cap the fixture never reaches, or
``--head 1`` on a one-item list. Those pairs are listed too, against BACK-1538 (grow the
fixture until they show, or confirm the flag is dropped).
"""

import os
import sqlite3
import subprocess
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import MagicMock

import pytest

from conftest import production_schemes
from reveal.cli.defaults import _default_args
from reveal.cli.routing.ledger import FlagLedger, TrackedArgs, delegate, mark, peek
from reveal.cli.routing.uri import handle_uri
from reveal.utils.query_parser import collect_parsed_query_keys, parse_query_params, query_key
import test_output_contract_compliance as harness_module

# ---------------------------------------------------------------------------
# 1. Ledger units
# ---------------------------------------------------------------------------


def _ledger(**flags):
    return FlagLedger(_default_args(**flags))


def test_set_flags_are_the_ones_that_differ_from_the_parser_default():
    ledger = _ledger(limit=2, head=None, depth=0)
    assert set(ledger.set_flags) == {'limit', 'depth'}  # --depth 0 is set, not falsy


def test_process_global_flags_are_never_reported():
    ledger = _ledger(respect_gitignore=False, provenance=True, copy=True)
    assert ledger.set_flags == {}


def test_a_read_through_tracked_args_counts_as_used_and_peek_does_not():
    ledger = _ledger(limit=2, head=3)
    args = ledger.track(_default_args(limit=2, head=3))
    assert isinstance(args, TrackedArgs)
    assert peek(args, 'head') == 3
    assert args.limit == 2
    assert ledger.unused_flags() == ['head']
    mark(args, 'head')
    assert ledger.unused_flags() == []


def test_a_flag_carried_into_the_query_is_judged_by_its_key():
    ledger = _ledger(limit=2)
    args = ledger.track(_default_args(limit=2))
    delegate(args, 'limit', 'top')
    with ledger.dispatching('x?top=2'):
        pass
    assert ledger.unused_flags() == ['limit']  # nobody parsed top=
    with ledger.dispatching('x?top=2'):
        parse_query_params('top=2')
    assert ledger.unused_flags() == []


def test_a_flag_whose_value_is_already_in_the_query_is_carried():
    """reveal f.py --type function routes as ast://f.py?type=function."""
    ledger = _ledger(type='function')
    with ledger.dispatching('f.py?type=function'):
        parse_query_params('type=function')
    assert ledger.unused_flags() == []


def test_a_query_key_no_parser_saw_is_reported_once():
    ledger = _ledger()
    with ledger.dispatching('t.db?bogus=1&name>2&bogus=3'):
        parse_query_params('name>2')
    assert ledger.unused_query_keys() == ['bogus']


def test_query_key_normalizes_filters_and_negation():
    assert [query_key(p) for p in ('limit=2', 'lines>50', '!draft', 'name~=x', 'show')] == \
        ['limit', 'lines', 'draft', 'name', 'show']


def test_parsed_keys_are_collected_only_inside_a_dispatch():
    parse_query_params('outside=1')
    with collect_parsed_query_keys() as keys:
        parse_query_params('a=1&b')
    assert keys == {'a', 'b'}


def test_note_names_every_unused_flag_and_the_bare_path_hint():
    """Flags appear in parser order, so the note is stable."""
    ledger = _ledger(limit=2, depth=1)
    err = StringIO()
    ledger.report('sqlite', stream=err)
    assert err.getvalue() == (
        "Note: --depth, --limit has no effect on sqlite:// queries -- not supported by this "
        "adapter. Use a bare path scan (reveal <path> --depth) instead.\n")


def test_mock_args_are_not_tracked():
    """Unit tests drive handle_uri with MagicMock args; every attribute of a mock 'differs'
    from the default, so tracking them would report every flag."""
    args = MagicMock()
    assert peek(args, 'head') is args.head
    mark(args, 'head')  # no ledger: a no-op, not an error
    delegate(args, 'limit', 'top')


# ---------------------------------------------------------------------------
# 2. Regressions: flags that used to vanish
# ---------------------------------------------------------------------------


def _cli(*argv, cwd):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8')


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / 't.db'))
    for i in range(3):
        conn.execute(f'CREATE TABLE t{i} (a)')
    conn.commit()
    conn.close()
    return tmp_path


def test_sqlite_limit_is_named_not_dropped(db):
    """The BACK-1514 repro: all tables listed, and no word about --limit."""
    proc = _cli('sqlite://t.db', '--limit', '2', cwd=db)
    assert proc.returncode == 0, proc.stderr
    assert 'Note: --limit has no effect on sqlite://' in proc.stderr


def test_unread_query_key_is_named(db):
    proc = _cli('sqlite://t.db?bogus=1', cwd=db)
    assert "query param 'bogus' has no effect on sqlite://" in proc.stderr


def test_exclude_on_an_adapter_that_never_walks_is_named(db):
    proc = _cli('sqlite://t.db', '--exclude', 'tests', cwd=db)
    assert 'Note: --exclude has no effect on sqlite://' in proc.stderr


def test_check_on_an_adapter_without_check_is_named(db):
    proc = _cli('env://', '--check', cwd=db)
    assert 'Note: --check has no effect on env://' in proc.stderr


def test_a_used_flag_gets_no_note(db):
    (db / 'm.py').write_text('def a():\n    pass\n\n\ndef b():\n    pass\n', encoding='utf-8')
    for argv in (('ast://m.py', '--limit', '1'), ('m.py', '--type', 'function'),
                 ('ast://.', '--exclude', 'x'), ('ast://m.py', '--format', 'json')):
        proc = _cli(*argv, cwd=db)
        assert proc.returncode == 0, (argv, proc.stderr)
        assert 'has no effect' not in proc.stderr, (argv, proc.stderr)


# ---------------------------------------------------------------------------
# 3. The ratchet: adapter x flag, honored or named
# ---------------------------------------------------------------------------

# dest -> (spelling on stderr, value). One flag per mechanism: query injection (limit, sort,
# since), router post-processing (head, max_items), walk scope (exclude), adapter/renderer
# reads (all), check mode (check), and the bare-path-only family (depth stands for
# depth/ext/type/fast, which share one path).
PROBES = {
    'limit': ('--limit', 1),
    'sort': ('--sort', 'name'),
    'since': ('--since', '2099-01-01'),
    'head': ('--head', 1),
    'max_items': ('--max-items', 1),
    'exclude': ('--exclude', ['tests']),
    'all': ('--all', True),
    'check': ('--check', True),
    'depth': ('--depth', 1),
}

_PARSED_BUT_IGNORED = 'BACK-1537'  # the adapter parses the key, then this view ignores it
_NOT_VISIBLE = 'BACK-1538'  # read, but the fixture cannot show an effect

KNOWN_SILENT = {
    ('git', 'limit'): _PARSED_BUT_IGNORED,
    ('git', 'sort'): _PARSED_BUT_IGNORED,
    ('git', 'since'): _PARSED_BUT_IGNORED,
    ('git', 'all'): _PARSED_BUT_IGNORED,
    ('xlsx', 'limit'): _PARSED_BUT_IGNORED,
    ('codex', 'since'): _NOT_VISIBLE,
    ('stats', 'since'): _NOT_VISIBLE,
    ('stats', 'sort'): _NOT_VISIBLE,
    ('depends', 'limit'): _NOT_VISIBLE,
    ('hotspots', 'limit'): _NOT_VISIBLE,
    ('testability', 'limit'): _NOT_VISIBLE,
    ('calls', 'head'): _NOT_VISIBLE,
    ('calls', 'max_items'): _NOT_VISIBLE,
    ('depends', 'head'): _NOT_VISIBLE,
    ('depends', 'max_items'): _NOT_VISIBLE,
    ('patches', 'head'): _NOT_VISIBLE,
    ('patches', 'max_items'): _NOT_VISIBLE,
    ('calls', 'exclude'): _NOT_VISIBLE,
    ('hotspots', 'exclude'): _NOT_VISIBLE,
    ('testability', 'exclude'): _NOT_VISIBLE,
    ('trace', 'exclude'): _NOT_VISIBLE,
    ('architecture', 'all'): _NOT_VISIBLE,
    ('ast', 'all'): _NOT_VISIBLE,
    ('calls', 'all'): _NOT_VISIBLE,
    ('claude', 'all'): _NOT_VISIBLE,
    ('deps', 'all'): _NOT_VISIBLE,
    ('hotspots', 'all'): _NOT_VISIBLE,
    ('overview', 'all'): _NOT_VISIBLE,
    ('stats', 'all'): _NOT_VISIBLE,
    ('testability', 'all'): _NOT_VISIBLE,
}


def _enrich(root):
    """More than one item in every list the probes cut, and a second git commit."""
    proj = root / 'proj'
    with open(proj / 'app.py', 'a', encoding='utf-8') as f:
        f.write('\n\ndef alpha(x):\n    if x:\n        return 1\n    return 2\n\n\n'
                'def beta():\n    return alpha(1)\n\n\nclass Gamma:\n    def run(self):\n'
                '        return beta()\n')
    (proj / 'lib.py').write_text('def zeta():\n    return 3\n\n\ndef eta():\n    return zeta()\n',
                                 encoding='utf-8')
    (proj / 'tests' / 'test_lib.py').write_text('def test_zeta():\n    assert True\n',
                                                encoding='utf-8')
    (proj / 'README.md').write_text('# Proj\n\nSee [app](app.py).\n\n## Usage\n\ntext\n\n'
                                    '## More\n\n[lib](lib.py)\n', encoding='utf-8')
    (proj / 'GUIDE.md').write_text('---\ntitle: Guide\n---\n# Guide\n\n## One\n', encoding='utf-8')
    (proj / 'data.json').write_text(
        '[{"name": "b", "n": 2}, {"name": "a", "n": 1}, {"name": "c", "n": 3}]', encoding='utf-8')
    conn = sqlite3.connect(str(proj / 'app.db'))
    conn.execute('CREATE TABLE orders (id INTEGER)')
    conn.execute('CREATE TABLE audit (id INTEGER)')
    conn.commit()
    conn.close()
    if (proj / 'data.xlsx').exists():
        import openpyxl
        wb = openpyxl.load_workbook(str(proj / 'data.xlsx'))
        for i in range(3):
            wb.active.append([f'r{i}', i])
        wb.create_sheet('Second').append(['x'])
        wb.save(str(proj / 'data.xlsx'))
    if (root / '.git').exists():
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com',
                   GIT_AUTHOR_DATE='2020-01-01T00:00:00', GIT_COMMITTER_DATE='2020-01-01T00:00:00')
        for cmd in (['add', 'proj'], ['commit', '-q', '-m', 'more']):
            subprocess.run(['git', '-C', str(root)] + cmd, check=True, env=env, capture_output=True)


class _FlagHarness(harness_module._Harness):
    def run_flags(self, scheme, **flags):
        key = (scheme, tuple(sorted((k, str(v)) for k, v in flags.items())))
        if key not in self._cache:
            out, err, code = StringIO(), StringIO(), 0
            with self._hermetic(), redirect_stdout(out), redirect_stderr(err):
                try:
                    handle_uri(harness_module.FIXTURE_URIS[scheme], None,
                               _default_args(format='json', **flags))
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            self._cache[key] = (code, out.getvalue(), err.getvalue())
        return self._cache[key]


@pytest.fixture(scope='module')
def flag_harness(tmp_path_factory):
    root = tmp_path_factory.mktemp('flag_ledger')
    harness_module._build_tree(root)
    _enrich(root)
    return _FlagHarness(root)


def _cases():
    params = []
    for scheme in sorted(harness_module.FIXTURE_URIS):
        for dest in PROBES:
            task = KNOWN_SILENT.get((scheme, dest))
            marks = [pytest.mark.xfail(strict=True, reason=f'{task}: dropped silently')] if task else []
            params.append(pytest.param(scheme, dest, marks=marks, id=f'{scheme}-{dest}'))
    return params


def test_known_silent_rows_name_real_cases():
    assert {s for s, _ in KNOWN_SILENT} <= set(harness_module.FIXTURE_URIS)
    assert {d for _, d in KNOWN_SILENT} <= set(PROBES)


def test_every_runnable_adapter_is_probed():
    runnable = set(production_schemes()) - set(harness_module.NOT_RUNNABLE)
    assert runnable <= set(harness_module.FIXTURE_URIS)


@pytest.mark.parametrize('scheme, dest', _cases())
def test_flag_is_honored_or_named(flag_harness, scheme, dest):
    if scheme == 'xlsx' and not (flag_harness.root / 'proj' / 'data.xlsx').exists():
        pytest.skip('openpyxl not installed')
    if scheme == 'git' and not (flag_harness.root / '.git').exists():
        pytest.skip('git not installed')
    option, value = PROBES[dest]
    base = flag_harness.run_flags(scheme)
    code, out, err = flag_harness.run_flags(scheme, **{dest: value})
    named = option in err or f"'{dest}'" in err  # an adapter's own 'Unknown query param' warning
    honored = (code, out) != base[:2]
    assert named or honored, (
        f'{option} on {scheme}:// changed nothing and no note named it. Honor it, or make '
        f'sure the ledger sees that it went unused (reveal/cli/routing/ledger.py).')


def test_tracked_args_behave_like_the_namespace_they_copy():
    args = FlagLedger(_default_args()).track(_default_args(limit=3))
    assert isinstance(args, Namespace)
    assert args.limit == 3 and getattr(args, 'no_such_flag', 'd') == 'd'
    args.limit = 4
    assert args.limit == 4
