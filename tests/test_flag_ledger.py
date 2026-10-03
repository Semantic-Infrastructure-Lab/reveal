"""Flag ledger (BACK-1514): a flag or query key the user sets is used, or a note names it.

Four layers:

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

4. Subcommands (BACK-1539): ``reveal <name>`` runs through ``cli/routing/subcommand.py``,
   which gives it the same ledger (judged against the subcommand's own parser) and the same
   ``--exclude``/REVEAL_IGNORE walk scope handle_uri publishes. Every subcommand that walks a
   tree must declare ``--exclude`` and honor both it and REVEAL_IGNORE, or name the flag; every
   subcommand's ``--verbose`` is honored or named.
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
from reveal.utils.query_control import parse_result_control
from reveal.utils.query_parser import (
    collect_query_keys, parse_query_filters, parse_query_params, query_key,
    warn_unknown_query_params)
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
    assert ledger.unused_flags() == ['limit']  # parsed, never read (BACK-1537)
    with ledger.dispatching('x?top=2'):
        parse_query_params('top=2').get('top')
    assert ledger.unused_flags() == []


def test_a_flag_whose_value_is_already_in_the_query_is_carried():
    """reveal f.py --type function routes as ast://f.py?type=function."""
    ledger = _ledger(type='function')
    with ledger.dispatching('f.py?type=function'):
        assert parse_query_params('type=function')['type'] == 'function'
    assert ledger.unused_flags() == []


@pytest.mark.parametrize('query', ['name~=load', 'name=load', '!name=load', 'name~=lo%20ad'])
def test_a_flag_carried_as_a_filter_is_matched_by_its_parsed_key(query):
    """reveal f.py --name load routes as ast://f.py?name~=load; parse_qs read the key as
    'name~', so the flag never matched and drew a false "no effect" note (BACK-1604)."""
    value = 'lo ad' if '%20' in query else 'load'
    ledger = _ledger(name=value)
    with ledger.dispatching(f'f.py?{query}'):
        assert parse_query_filters(query)
    assert ledger.unused_flags() == []


def test_a_flag_whose_value_differs_from_the_filter_is_still_unused():
    ledger = _ledger(name='load')
    with ledger.dispatching('f.py?name~=save'):
        pass
    assert ledger.unused_flags() == ['name']


def test_a_query_key_no_parser_saw_is_reported_once():
    ledger = _ledger()
    with ledger.dispatching('t.db?bogus=1&name>2&bogus=3'):
        parse_query_filters('name>2')  # a filter parser uses every key it parses
    assert ledger.unused_query_keys() == ['bogus']


def test_query_key_normalizes_filters_and_negation():
    assert [query_key(p) for p in ('limit=2', 'lines>50', '!draft', 'name~=x', 'show')] == \
        ['limit', 'lines', 'draft', 'name', 'show']


def test_query_keys_are_collected_only_inside_a_dispatch():
    parse_query_params('outside=1').get('outside')
    with collect_query_keys() as log:
        parse_query_filters('x>1')
        params = parse_query_params('a=1&b')
    assert log.seen == {'x', 'a', 'b'} and log.used == {'x'}
    params.get('a')  # bound at parse time: a read after the block still lands in its log
    assert log.used == {'x', 'a'}


# BACK-1537: a dict parser's key is used when the adapter reads it, not when it is parsed.

def test_query_params_record_reads_and_peeks_do_not():
    with collect_query_keys() as log:
        params = parse_query_params('limit=2&content~=x&sort=name&flag')
        assert list(params.peek_items()) == [('limit', '2'), ('content~', 'x'), ('sort', 'name'),
                                             ('flag', True)]
        assert log.used == set()
        params.get('content~')
        assert 'sort' in params
        params['flag']
        params.get('absent')
    assert log.used == {'content', 'sort', 'flag', 'absent'}  # normalized like the ledger's keys


@pytest.mark.parametrize('walk', [list, lambda p: p.items(), lambda p: dict(p), lambda p: {**p},
                                  lambda p: p.copy(), lambda p: (lambda **kw: kw)(**p)])
def test_walking_a_whole_query_counts_every_key(walk):
    """A consumer this class cannot see into (a helper handed the dict) never gets a false note."""
    with collect_query_keys() as log:
        walk(parse_query_params('a=1&b=2'))
    assert log.used == {'a', 'b'}


def test_result_control_counts_a_key_when_a_field_is_read():
    with collect_query_keys() as log:
        rest, control = parse_result_control('limit=2&sort=-name&type=x')
    assert rest == 'type=x' and log.seen == {'limit', 'sort'} and log.used == set()
    assert control.limit == 2
    assert log.used == {'limit'}
    assert control.sort_descending
    assert log.used == {'limit', 'sort'}


def test_an_unknown_key_warning_counts_as_the_note():
    """The adapter's own 'Unknown query param' warning named it; the ledger must not repeat it."""
    with collect_query_keys() as log:
        params = parse_query_params('bogus=1&limit=2')
        warn_unknown_query_params(params, {'limit'}, stream=StringIO())
    assert log.used == {'bogus'}


def test_a_parsed_but_unread_key_gets_the_not_for_this_view_note():
    ledger = _ledger(limit=2)
    args = ledger.track(_default_args(limit=2))
    delegate(args, 'limit', 'limit')
    with ledger.dispatching('f.py?limit=2&raw=1&bogus=1'):
        parse_query_params('limit=2&raw=1')
    err = StringIO()
    ledger.report('git', stream=err)
    assert err.getvalue() == (
        "Note: --limit has no effect on this git:// query -- the adapter accepts it, but not "
        "for this view.\n"
        "Note: query param 'bogus' has no effect on git:// -- this adapter does not read it.\n"
        "Note: query param 'raw' has no effect on this git:// query -- the adapter accepts it, "
        "but not for this view.\n")


def test_note_names_every_unused_flag_and_the_bare_path_hint():
    """Flags appear in parser order, so the note is stable."""
    ledger = _ledger(limit=2, depth=1)
    err = StringIO()
    ledger.report('sqlite', stream=err)
    assert err.getvalue() == (
        "Note: --limit, --depth has no effect on sqlite:// queries -- not supported by this "
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


@pytest.fixture
def jsons(tmp_path):
    (tmp_path / 'obj.json').write_text('{"a": 1, "b": [1, 2, 3]}', encoding='utf-8')
    (tmp_path / 'arr.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('uri', ['json://obj.json?keys', 'json://obj.json?schema',
                                 'json://obj.json?flatten&data-only', 'json://arr.json?n=1',
                                 'json://arr.json?limit=1'])
def test_json_modes_and_applied_filters_get_no_note(jsons, uri):
    """BACK-1542: the legacy modes are read from the raw query, so ?keys (which works) was
    told 'this adapter does not read it'."""
    proc = _cli(uri, '--format', 'json', cwd=jsons)
    assert proc.returncode == 0, proc.stderr
    assert 'has no effect' not in proc.stderr, proc.stderr


@pytest.mark.parametrize('uri, key', [('json://obj.json?bogus=1', 'bogus'),
                                      ('json://obj.json?limit=1', 'limit')])
def test_json_filters_on_an_object_are_named(jsons, uri, key):
    """BACK-1542: filters and ?limit apply to arrays; on an object they were silently
    dropped (a filter counted as used when parsed, ?limit when validated)."""
    proc = _cli(uri, '--format', 'json', cwd=jsons)
    assert f"query param '{key}' has no effect on this json:// query" in proc.stderr


def test_check_on_an_adapter_without_check_is_named(db):
    proc = _cli('env://', '--check', cwd=db)
    assert 'Note: --check has no effect on env://' in proc.stderr


def test_a_used_flag_gets_no_note(db):
    (db / 'm.py').write_text('def a():\n    pass\n\n\ndef b():\n    pass\n', encoding='utf-8')
    for argv in (('ast://m.py', '--limit', '1'), ('m.py', '--type', 'function'),
                 ('ast://.', '--exclude', 'x'), ('ast://m.py', '--format', 'json'),
                 ('m.py', '--name', 'a'), ('.', '--name', 'a'), ('m.py', '--search', 'a')):  # BACK-1604
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

_NOT_VISIBLE = 'BACK-1538'  # read, but the fixture cannot show an effect

KNOWN_SILENT = {
    ('codex', 'since'): _NOT_VISIBLE,
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
    ('trace', 'exclude'): _NOT_VISIBLE,
    # The target is proj/tests, so --exclude tests (relative to it) matches nothing there.
    ('patches', 'exclude'): _NOT_VISIBLE,
    ('architecture', 'all'): _NOT_VISIBLE,
    ('ast', 'all'): _NOT_VISIBLE,
    ('calls', 'all'): _NOT_VISIBLE,
    ('claude', 'all'): _NOT_VISIBLE,
    ('deps', 'all'): _NOT_VISIBLE,
    ('hotspots', 'all'): _NOT_VISIBLE,
    ('overview', 'all'): _NOT_VISIBLE,
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


# ---------------------------------------------------------------------------
# 4. Subcommands (BACK-1539): the same ledger and walk scope through one seam
# ---------------------------------------------------------------------------

from reveal.cli.commands.surface import create_surface_parser  # noqa: E402
from reveal.cli.routing.ledger import complete  # noqa: E402
from reveal.cli.routing.subcommand import dispatch_subcommand  # noqa: E402


def test_a_subcommand_ledger_judges_flags_against_its_own_parser():
    """--top is surface's own flag and --verbose comes from the shared parent; neither is on
    the main parser's defaults, which is what the URI ledger compares against."""
    parser = create_surface_parser()
    ledger = FlagLedger(parser.parse_args(['.', '--top', '3', '--verbose']), parser=parser,
                        subcommand='surface')
    assert set(ledger.set_flags) == {'top', 'verbose'}
    err = StringIO()
    ledger.report(stream=err)
    note = err.getvalue()
    assert "has no effect on 'reveal surface' -- this subcommand does not use it" in note
    assert '--top' in note and '--verbose' in note


def _dispatch(runner, *argv):
    parser = create_surface_parser()
    err = StringIO()
    with redirect_stderr(err):
        try:
            dispatch_subcommand('surface', parser, runner, parser.parse_args(list(argv)))
        except SystemExit:
            pass
    return err.getvalue()


def test_a_findings_exit_still_reports_and_an_error_exit_does_not():
    """deps/hotspots/check/health/review exit nonzero after printing their result: the flags
    were applied (or not), so the note belongs. An early error exit applied nothing."""
    def findings(args):
        complete(args)
        sys.exit(1)

    def error(args):
        sys.exit(1)

    assert '--verbose' in _dispatch(findings, '.', '--verbose')
    assert _dispatch(error, '.', '--verbose') == ''
    assert _dispatch(lambda args: args.verbose, '.', '--verbose') == ''  # read = used


def _walk_tree(root):
    """A project whose skipme/ shows up in every walking subcommand's output.

    The config root sits above the walked path, as in a real repo (``reveal surface src``):
    that is where REVEAL_IGNORE went unhonored, since a walker matching patterns against the
    config root sees ``proj/skipme/...``, not ``skipme/...``."""
    (root / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    proj = root / 'proj'
    (proj / 'skipme').mkdir(parents=True)
    (proj / 'tests').mkdir()
    (proj / 'app.py').write_text(
        'from abc import ABC, abstractmethod\n\nfrom skipme.extra import extra_fn\n\n\n'
        'class Base(ABC):\n    @abstractmethod\n    def run(self):\n        ...\n\n\n'
        'def main(x):\n    if x:\n        return extra_fn(x)\n    return 0\n', encoding='utf-8')
    (proj / 'skipme' / '__init__.py').write_text('', encoding='utf-8')
    (proj / 'skipme' / 'extra.py').write_text(
        'import os\nimport sys\n\nfrom app import Base\n\n\nclass Impl(Base):\n'
        '    def run(self):\n        return 1\n\n\ndef extra_fn(x):\n'
        + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(25))
        + '    return os.sep\n', encoding='utf-8')
    (proj / 'tests' / 'test_app.py').write_text(
        'from unittest.mock import patch\n\n\n@patch("skipme.extra.extra_fn")\n'
        '@patch("skipme.extra.os")\ndef test_main(a, b):\n    pass\n', encoding='utf-8')
    (proj / 'README.md').write_text('# Proj\n\nSee [app](app.py).\n', encoding='utf-8')
    # More of everything than any default --top shows, so --verbose (lift the cap) is visible.
    (proj / 'many').mkdir()
    for i in range(30):
        (proj / 'many' / f'mod{i}.py').write_text(
            f'import json\n\nfrom app import main\n\n\ndef work{i}(x):\n'
            + ''.join(f'    if x == {j}:\n        return main({j})\n' for j in range(12 + i % 5))
            + '    return 0\n', encoding='utf-8')
    # 30 targets patched 3 times each: past testability's --min-patches 3 and its --top 20.
    (proj / 'tests' / 'test_many.py').write_text('from unittest.mock import patch\n\n\n' + ''.join(
        f'@patch("many.mod{i}.work{i}")\ndef test_{i}_{k}(m):\n    pass\n\n\n'
        for i in range(30) for k in range(3)), encoding='utf-8')
    return proj


# name -> argv after the subcommand, for every subcommand that walks a tree.
WALKERS = {
    'architecture': ['proj'],
    'check': ['proj'],
    'contracts': ['proj'],
    'deps': ['proj'],
    'hotspots': ['proj'],
    'overview': ['proj'],
    'pack': ['proj'],
    'surface': ['proj'],
    'testability': ['proj', '--tests', 'proj/tests'],
    'trace': ['proj', '--from', 'main'],
}
# Subcommands that take --verbose, and what else each needs to run on the tree.
VERBOSE_TAKERS = {**{n: a for n, a in WALKERS.items() if n != 'trace'},
                  'health': ['proj'], 'review': ['proj']}

# (subcommand, probe): the walk consulted the scope, but the fixture cannot show an effect.
# The URI ratchet lists the same testability pair (BACK-1538).
KNOWN_NOT_VISIBLE = {
    ('testability', 'exclude'): 'BACK-1538',
    ('testability', 'reveal_ignore'): 'BACK-1538',
}


class _SubcommandHarness:
    def __init__(self, root):
        self.root = root
        self._cache = {}

    def run(self, name, *extra, reveal_ignore=None, fmt='json'):
        key = (name, extra, reveal_ignore, fmt)
        if key not in self._cache:
            from conftest import _run_reveal_direct
            from reveal.config import RevealConfig
            argv = [name, *WALKERS.get(name, VERBOSE_TAKERS.get(name, [])), *extra,
                    '--format', fmt]
            saved_cwd, saved_env = os.getcwd(), os.environ.get('REVEAL_IGNORE')
            os.chdir(self.root)
            if reveal_ignore:
                os.environ['REVEAL_IGNORE'] = reveal_ignore
            RevealConfig._cache.clear()
            try:
                proc = _run_reveal_direct(*argv)
            finally:
                os.chdir(saved_cwd)
                if saved_env is None:
                    os.environ.pop('REVEAL_IGNORE', None)
                else:
                    os.environ['REVEAL_IGNORE'] = saved_env
                RevealConfig._cache.clear()
            self._cache[key] = (proc.returncode, proc.stdout, proc.stderr)
        return self._cache[key]


@pytest.fixture(scope='module')
def subcommand_harness(tmp_path_factory):
    root = tmp_path_factory.mktemp('subcommand_ledger')
    _walk_tree(root)
    return _SubcommandHarness(root)


def _walk_cases():
    for name in sorted(WALKERS):
        for probe in ('exclude', 'reveal_ignore'):
            task = KNOWN_NOT_VISIBLE.get((name, probe))
            marks = [pytest.mark.xfail(strict=True, reason=f'{task}: not visible')] if task else []
            yield pytest.param(name, probe, marks=marks, id=f'{name}-{probe}')


def test_walkers_match_the_subcommand_table():
    from reveal.cli.invocation import COMMANDS
    assert set(VERBOSE_TAKERS) <= set(COMMANDS)
    for name, spec in COMMANDS.items():
        parser, _runner = spec.load()
        declares = any('--exclude' in a.option_strings for a in parser._actions)
        assert declares == (name in WALKERS), (
            f"reveal {name}: --exclude is declared exactly by the subcommands that walk a tree "
            f"(add_exclude_argument), and each of those is probed in WALKERS")


@pytest.mark.parametrize('name, probe', _walk_cases())
def test_walk_scope_reaches_every_walking_subcommand(subcommand_harness, name, probe):
    """BACK-1517: REVEAL_IGNORE pruned surface:// but not `reveal surface`, and `reveal pack`
    rejected the --exclude pack:// accepted. Both now come from one seam."""
    base = subcommand_harness.run(name)
    if probe == 'exclude':
        code, out, err = subcommand_harness.run(name, '--exclude', 'skipme/')
    else:
        code, out, err = subcommand_harness.run(name, reveal_ignore='skipme/**')
    assert 'unrecognized arguments' not in err, err
    honored = (code, out) != base[:2]
    assert honored or 'Note: --exclude' in err, (
        f'{probe} on reveal {name} changed nothing and no note named it. The walk scope is '
        f'published by reveal/cli/routing/subcommand.py; a walker that bypasses '
        f'the shared walker (utils.path_utils.walk_filter) does not see it.')


@pytest.mark.parametrize('name', sorted(VERBOSE_TAKERS))
def test_verbose_is_honored_or_named_on_every_subcommand(subcommand_harness, name):
    """--verbose comes from the shared parent parser, so every subcommand accepts it. Where it
    has nothing to expand (surface, contracts, health, ...) it used to vanish in silence.
    Text output: where --verbose lifts --top, the cap is a display cap (JSON is uncapped)."""
    base = subcommand_harness.run(name, fmt='text')
    code, out, err = subcommand_harness.run(name, '--verbose', fmt='text')
    assert (code, out) != base[:2] or f"--verbose has no effect on 'reveal {name}'" in err, err
