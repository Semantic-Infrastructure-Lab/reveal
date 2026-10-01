"""Adapter contract harness (BACK-1513): every registered adapter, one fixture tree,
invariants checked on the result dict.

The adapter set comes from the registry, never from a hand-written list. A new adapter
fails ``test_every_registered_adapter_is_covered`` until it gets a ``FIXTURE_URIS`` row (how
to run it here) or a ``NOT_RUNNABLE`` reason. This file used to hold one hand-written class
per adapter (15 of 35). An adapter nobody listed was never checked, which is the opt-in
failure mode BACK-1363 describes.

Each run goes through ``handle_uri`` with ``--format json`` from a temp cwd, using a
relative URI. That is the same result dict the CLI and MCP produce. Runs are hermetic: HOME
points at a fixture home, and so does every adapter class attribute holding a ``Path``
under the real home (``CodexAdapter.CODEX_DB``, ``ClaudeAdapter.CONVERSATION_BASE``, ...),
since those are resolved once at import. The fixture home holds an empty Claude projects
directory and an empty Codex session DB, so claude:// and codex:// return a real (empty)
answer. Without them their result is an error, and a contract check on an error envelope
proves nothing about the adapter's normal output. Invariants:

1. ``contract``: Output Contract fields are present, and ``type`` is one the schema declares.
2. ``missing``: a nonexistent resource exits nonzero. It is never a clean empty answer
   (BACK-1321).
3. ``error_exit``: a result carrying a top-level ``error`` exits nonzero. An error must not
   read as success. The router enforces this for every adapter since BACK-1059
   (``cli/routing/uri._emit_result``); the fixture runs below are normally clean, so
   the error paths themselves are pinned in ``tests/test_result_outcome.py``.
4. ``abs_path``: no string in the result contains the fixture root's absolute path. The
   input was relative, so an absolute path is a leak (BACK-1366). The subcommand forms are held to the same rule (``subcommand_abs_path``):
   their runners resolved the target before the adapter saw it, so ``reveal trace proj``
   leaked every frame's file where ``trace://proj`` leaked none.
   ``test_the_abs_path_invariant_bites`` checks that an absolute input is still caught.
5. ``truncation``: every list that ``--head 1`` makes shorter is disclosed as a
   ``truncated`` meta warning naming it (``note_truncation``), and the text render prints
   it (BACK-1059). A cut list must not read as the whole answer.
6. ``subcommand``: every ``reveal <name>`` that answers a query (the ``COMMANDS``
   registry, run through ``main``) prints its result through
   ``cli/routing/subcommand.emit_subcommand_result``, and every cut that result records is
   printed in its text output. Runners that built their own output never checked the
   outcome, so slice 2 of BACK-1059 silently dropped ``reveal overview``'s cut line
   (BACK-1544). ``SUBCOMMAND_CUT_ARGV`` makes the fixture cut real lists, and
   ``test_the_subcommand_cut_invariant_bites`` checks that it does.
7. ``own_cap``: every list an adapter's own cap knob makes shorter is disclosed. The knob is
   the key its ``CLI_QUERY_FLAGS['all']`` lifts, or a ``top``/``limit`` its schema declares;
   the adapter runs on the wider ``wide/`` tree with the knob at 1 and uncapped. A cap the
   adapter applies itself is a ``[:N]`` the router never sees, so ``--head`` (invariant 5)
   can't expose it: ``stats://?hotspots=true&top=2`` showed 2 of 43 hotspot files as the
   whole list (BACK-1543). ``test_the_own_cap_invariant_bites`` checks that it cuts.
   The cut must also be honest: the capped list is the first N of the uncapped one (git's
   ``?sort=date&limit=1`` listed the newest commit, sorted after the walk stopped), and a
   disclosed ``total`` is the uncapped length, or at most it when ``exact`` is false
   (xlsx said ``total_matches: 3`` where 684 matched) (BACK-1547).
8. ``failure``: a query that fails on a missing resource reads the same whether the adapter
   returned the error or raised it: the error once, on stderr, in text; a JSON envelope
   with the Output Contract fields and the current ``contract_version``; ``--also-json``
   written. A raise used to print twice, carry ``contract_version`` 1.0 and skip
   ``--also-json`` (BACK-1553). ``test_the_failure_invariant_bites`` checks that both kinds
   are compared.
9. ``batch``: ``--stdin --batch`` answers each URI as ``reveal URI`` does: the entry's ``data``
   is the same result, and its status is ``error`` exactly when the URI form exits nonzero
   (``not_applicable`` when it declines). Batch built each adapter itself from the whole URI
   and called only get_structure(), so ast:// found nothing on any path, env://HOME listed
   the whole environment, and a failed query counted as successful with exit 0 (BACK-1554).
   ``test_the_batch_invariant_bites`` checks that every status is compared.
10. ``posix_path``: no string in a result spells a fixture path with Windows separators
   (``proj\\app.py``, ``pkg\\util.py``); paths are written with ``/`` on every OS (BACK-1586).
   Only Windows CI can produce a violation, so this invariant has no strict-xfail list: on
   Linux an entry would XPASS. ``test_the_posix_path_invariant_bites`` checks the needles.

Violations that exist today are listed in ``KNOWN_VIOLATIONS`` as strict xfails, each
naming its task. A fix makes its case XPASS, which fails the run until the entry is
deleted. The list can only shrink.

Not covered yet (BACK-1513 follow-ups): caps with no knob (a hard-coded ``[:20]``, which
invariant 7 can't vary) and consumed flags (BACK-1514).
"""

import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from reveal import adapters  # noqa: F401  (registers every adapter)
from conftest import production_schemes
from reveal.adapters import base as adapters_base
from reveal.cli.defaults import _default_args
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing import subcommand as subcommand_seam
from reveal.cli.routing.uri import handle_uri
from reveal.main import main
from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.results import outcome_of, truncations_of

pytestmark = pytest.mark.contract

# How to run each adapter against the fixture (paths relative to its root). A URI that
# names 'proj' reads the fixture tree and is subject to the abs_path invariant; the rest
# read host state (made hermetic by an empty HOME).
FIXTURE_URIS = {
    'architecture': 'architecture://proj',
    'ast': 'ast://proj',
    'calls': 'calls://proj?target=helper',
    'classify': 'classify://proj',
    'contracts': 'contracts://proj',
    'depends': 'depends://proj',
    'deps': 'deps://proj',
    'diff': 'diff://proj/app_old.py:proj/app.py',
    'git': 'git://proj/app.py',
    'hotspots': 'hotspots://proj',
    'imports': 'imports://proj',
    'json': 'json://proj/data.json',
    'markdown': 'markdown://proj',
    'overview': 'overview://proj',
    'pack': 'pack://proj',
    'patches': 'patches://proj/tests',
    'sqlite': 'sqlite://proj/app.db',
    'stats': 'stats://proj',
    'surface': 'surface://proj',
    'testability': 'testability://proj',
    'trace': 'trace://proj?from=main',
    'xlsx': 'xlsx://proj/data.xlsx',
    'claude': 'claude://sessions',
    'codex': 'codex://',
    'env': 'env://',
    'help': 'help://',
    'nginx': 'nginx://',
    'python': 'python://',
    'reveal': 'reveal://',
}

NOT_RUNNABLE = {
    'autossl': 'reads certbot renewal logs on a server',
    'cpanel': 'needs a live cPanel server',
    'domain': 'needs live DNS',
    'letsencrypt': 'reads /etc/letsencrypt on a server',
    'mysql': 'needs a live MySQL server',
    'ssl': 'needs a live TLS endpoint',
}

# Where 'scheme://nonexistent' is not a well-formed request of that adapter. git reads the
# repository from the cwd; outside one it declines as not-applicable, which exits 0 by
# design (tests/test_routing.py::test_not_applicable_exits_zero_not_one).
MISSING_URIS = {
    'diff': 'diff://nonexistent_zz_1513.py:nonexistent_zz_1513b.py',
    'trace': 'trace://nonexistent_zz_1513?from=main',
}

KNOWN_VIOLATIONS = {
    ('subcommand', 'check'): 'BACK-1545',
}

# How to run each `reveal <name>` against the fixture (invariant 6). Every COMMANDS entry
# needs a row here or a NOT_A_QUERY reason.
SUBCOMMAND_ARGV = {
    'architecture': ['proj'],
    'check': ['proj'],
    'contracts': ['proj'],
    'deps': ['proj'],
    'health': ['proj'],
    'hotspots': ['proj'],
    'overview': ['proj'],
    'pack': ['proj'],
    'review': ['proj'],
    'surface': ['proj'],
    'testability': ['proj'],
    'trace': ['proj', '--from', 'main'],
}

NOT_A_QUERY = {
    'dev': 'developer tooling (scaffold, config inspection), not an answer about a target',
    'offline': 'prepares grammars for offline use, not an answer about a target',
    'scaffold': 'writes template files, not an answer about a target',
}

# Flags that make the small fixture cut a list, so the text-disclosure half of invariant 6
# is not vacuously green.
SUBCOMMAND_CUT_ARGV = {
    'hotspots': ['--top', '1', '--min-complexity', '1'],
}

# Invariant 7 runs each adapter that has a cap knob on the wider tree: its FIXTURE_URIS row
# with 'proj' read as 'wide', plus any other views listed here (a view is where a list, and
# the knob that caps it, lives: calls:// ranks only under ?uncalled or ?rank=).
OWN_CAP_URIS = {
    'calls': ['calls://wide?uncalled', 'calls://wide?rank=callers'],
    'depends': ['depends://wide/pkg/y.py'],
    # history newest-first, the same file oldest-first (a sort must see every commit, not
    # the ones walked before the limit), and the repository view's recent commits, branches
    # and tags
    'git': ['git://wide/app.py?type=history', 'git://wide/app.py?type=history&sort=date',
            'git://.'],
    'imports': ['imports://wide?rank=fan-in'],
    'stats': ['stats://wide?hotspots=true'],
    'xlsx': ['xlsx://wide/data.xlsx?sheet=Sheet', 'xlsx://wide/data.xlsx?search=n'],
}

# Invariant 9 compares each adapter's fixture and missing URIs through --batch, plus these: a
# not-applicable answer (the fixture home has no tests), so a declined query is compared too.
BATCH_URIS = {
    'testability': ['testability://home'],
}

_REQUIRED_FIELDS = ['contract_version', 'type', 'source', 'source_type']
_UNSET = object()
_VALID_SOURCE_TYPES = {'file', 'directory', 'database', 'runtime', 'network'}


def _registered():
    return production_schemes()


def _cases(invariant, schemes):
    """Parametrize `schemes`, marking known violators as strict xfails."""
    params = []
    for scheme in schemes:
        task = KNOWN_VIOLATIONS.get((invariant, scheme))
        marks = [pytest.mark.xfail(strict=True, reason=f'{task}: known violation')] if task else []
        params.append(pytest.param(scheme, marks=marks, id=scheme))
    return params


def _build_tree(root: Path) -> None:
    proj = root / 'proj'
    (proj / 'tests').mkdir(parents=True)
    (root / 'home').mkdir()
    (root / 'home' / '.claude' / 'projects').mkdir(parents=True)
    (root / 'home' / '.codex').mkdir()
    conn = sqlite3.connect(str(root / 'home' / '.codex' / 'state_5.sqlite'))
    conn.execute(
        'CREATE TABLE threads (id TEXT, title TEXT, first_user_message TEXT, model TEXT, '
        'model_provider TEXT, reasoning_effort TEXT, tokens_used INTEGER, cwd TEXT, '
        'created_at INTEGER, updated_at INTEGER, cli_version TEXT, git_branch TEXT, '
        'approval_mode TEXT, thread_source TEXT, archived INTEGER)')
    conn.commit()
    conn.close()
    (proj / 'app.py').write_text(
        'import os\n\n\ndef main():\n    return helper()\n\n\n'
        'def helper():\n    return os.getcwd()\n', encoding='utf-8')
    (proj / 'app_old.py').write_text('def main():\n    pass\n', encoding='utf-8')
    (proj / 'tests' / 'test_app.py').write_text(
        'from unittest import mock\n\n\ndef test_main():\n'
        '    with mock.patch("app.helper"):\n        pass\n', encoding='utf-8')
    (proj / 'README.md').write_text('# Proj\n\nSee [app](app.py).\n', encoding='utf-8')
    # A doc under tests/, so the flag ledger's '--exclude tests' probe has something to drop
    # on markdown://, which walks through the shared walker since BACK-1516.
    (proj / 'tests' / 'NOTES.md').write_text('# Test notes\n', encoding='utf-8')
    (proj / 'data.json').write_text('{"key": "value", "items": [1, 2]}', encoding='utf-8')
    conn = sqlite3.connect(str(proj / 'app.db'))
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
    conn.commit()
    conn.close()
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        wb.active.append(['name', 'value'])
        wb.save(str(proj / 'data.xlsx'))
    except ImportError:
        pass
    _build_wide_tree(root / 'wide')
    if shutil.which('git'):  # the root is the repo: git:// resolves it from the cwd
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com')

        def git(*cmd, day=1):
            # A day apart, so a date sort has one right answer (invariant 7's prefix rule).
            date = f'2026-01-{day:02d}T12:00:00'
            subprocess.run(['git', '-C', str(root), *cmd], check=True, capture_output=True,
                           env=dict(env, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date))

        git('init', '-q')
        git('add', 'proj', 'wide')
        git('commit', '-q', '-m', 'init')
        for day, name in ((2, 'later'), (3, 'latest')):
            with open(root / 'wide' / 'app.py', 'a', encoding='utf-8') as f:
                f.write(f'\n\ndef {name}():\n    pass\n')
            git('commit', '-q', '-am', name, day=day)
        # Two of each ref, a day apart, so the repository view's ?limit cuts its newest
        # branches and tags too (BACK-1551).
        git('branch', 'first', 'HEAD~2')
        git('tag', 'v1', 'HEAD~1')
        git('tag', 'v2')


def _build_wide_tree(wide: Path) -> None:
    """Two or more of everything a cap knob cuts (invariant 7): hotspot files, complex
    functions, callers, imports, modules, patches, JSON items, sheet rows, commits. Kept
    apart from proj/ so the other invariants' fixture answers don't move."""
    (wide / 'pkg').mkdir(parents=True)
    (wide / 'tests').mkdir()
    nested = ''.join('    ' * (i + 1) + f'if x > {i}:\n' for i in range(6)) + '    ' * 7 + 'return x\n'
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
    for n in ('a', 'b', 'c'):
        (wide / f'deep_{n}.py').write_text(
            f'def deep_{n}(x):\n{nested}    return 0\n\n\n'
            f'def cx_{n}(x):\n{branches}    return -1\n', encoding='utf-8')
    (wide / 'app.py').write_text(
        'import os\nimport json\nimport sys\nfrom pkg import x, y\n\n\n'
        'def main():\n    return helper() + a() + b()\n\n\n'
        'def a():\n    return helper()\n\n\ndef b():\n    return helper()\n\n\n'
        'def helper():\n    return os.getcwd()\n\n\n'
        'def unused_one():\n    pass\n\n\ndef unused_two():\n    pass\n', encoding='utf-8')
    (wide / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (wide / 'pkg' / 'x.py').write_text(
        'import requests\nimport yaml\nfrom pkg import y\n\n\ndef fx():\n    return y.fy()\n',
        encoding='utf-8')
    (wide / 'pkg' / 'y.py').write_text(
        'import numpy\nfrom pkg import x\n\n\ndef fy():\n    return 1\n', encoding='utf-8')
    (wide / 'tests' / 'test_app.py').write_text(
        'from unittest import mock\n\n\ndef test_main():\n'
        '    with mock.patch("app.helper"):\n        pass\n'
        '    with mock.patch("app.a"):\n        pass\n\n\n'
        'def test_b():\n    with mock.patch("app.b"):\n        pass\n', encoding='utf-8')
    (wide / 'data.json').write_text(json.dumps([{'n': i} for i in range(4)]), encoding='utf-8')
    for i in range(3):
        (wide / f'doc{i}.md').write_text(f'# Doc {i}\n\n## One\n\n## Two\n', encoding='utf-8')
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        for i in range(4):
            wb.active.append([f'n{i}', i])
        wb.create_sheet('second').append(['k'])
        wb.save(str(wide / 'data.xlsx'))
    except ImportError:
        pass


class _Harness:
    def __init__(self, root: Path):
        self.root = root
        self.home = root / 'home'
        self._cache = {}
        self.needles = {str(p) for r in (root, root.resolve()) for p in (r, r.as_posix())}

    def _home_paths(self):
        """(class, attr, fake path) for adapter class attributes under the real home."""
        real = Path.home()
        for scheme in _registered():
            cls = adapters_base.get_adapter_class(scheme)
            for klass in cls.__mro__:
                for name, value in vars(klass).items():
                    if isinstance(value, Path):
                        try:
                            yield cls, name, self.home / value.relative_to(real)
                        except ValueError:
                            pass

    @contextmanager
    def _hermetic(self):
        # The language pack fixes its grammar cache directory at first use, under HOME. Use it
        # once before HOME moves, or each xdist worker downloads grammars into the empty home
        # (8s+ per worker, and a network dependency).
        from tree_sitter_language_pack import get_parser
        get_parser('python')
        cwd = os.getcwd()
        saved_env = {k: os.environ.get(k) for k in ('HOME', 'USERPROFILE')}
        redirected = [(cls, name, cls.__dict__.get(name, _UNSET), fake)
                      for cls, name, fake in self._home_paths()]
        os.environ['HOME'] = os.environ['USERPROFILE'] = str(self.home)
        for cls, name, _, fake in redirected:
            setattr(cls, name, fake)
        os.chdir(self.root)
        try:
            yield
        finally:
            os.chdir(cwd)
            for cls, name, original, _ in redirected:
                if original is _UNSET:
                    delattr(cls, name)
                else:
                    setattr(cls, name, original)
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def run_raw(self, uri, **flags):
        """(exit code, stdout, stderr) for `uri` with CLI `flags`, run once and cached."""
        key = (uri, tuple(sorted(flags.items())))
        if key not in self._cache:
            self._cache[key] = self._invoke(uri, **flags)
        return self._cache[key]

    def _invoke(self, uri, **flags):
        out, err, code = StringIO(), StringIO(), 0
        with self._hermetic(), redirect_stdout(out), redirect_stderr(err):
            try:
                handle_uri(uri, None, _default_args(**flags))
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def run(self, uri, **flags):
        """(exit code, parsed JSON or None, stderr) for `uri` with --format json."""
        code, out, err = self.run_raw(uri, format='json', **flags)
        try:
            payload = json.loads(out)
        except ValueError:
            payload = None
        return code, payload, err

    def run_subcommand(self, name, *argv):
        """(exit code, stdout, stderr, results) for `reveal <name> <argv>` through ``main``.

        ``results`` are the result dicts that reached ``emit_subcommand_result``, seen at
        its ``outcome_of`` call; empty when the runner printed its output some other way.
        """
        key = (name, argv)
        if key not in self._cache:
            out, err, code, results = StringIO(), StringIO(), 0, []

            def recording_outcome_of(result, _real=subcommand_seam.outcome_of):
                results.append(result)
                return _real(result)

            with self._hermetic(), redirect_stdout(out), redirect_stderr(err), \
                    pytest.MonkeyPatch.context() as mp:
                mp.setattr(subcommand_seam, 'outcome_of', recording_outcome_of)
                try:
                    main(['reveal', name, *argv])
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            self._cache[key] = (code, out.getvalue(), err.getvalue(), results)
        return self._cache[key]

    def run_batch(self, uri):
        """(URI-form exit code, URI-form JSON, batch exit code, the one batch entry) for `uri`
        run as `reveal URI --format json` and piped to `reveal --stdin --batch --format json`.
        The two run back to back, not from the cache: env:// reads os.environ, which other
        tests in the worker change between an earlier cached run and this one."""
        key = ('--batch', uri)
        if key not in self._cache:
            direct_code, direct_out, _ = self._invoke(uri, format='json')
            try:
                direct = json.loads(direct_out)
            except ValueError:
                direct = None
            out, err, code = StringIO(), StringIO(), 0
            with self._hermetic(), redirect_stdout(out), redirect_stderr(err), \
                    pytest.MonkeyPatch.context() as mp:
                mp.setattr('sys.stdin', StringIO(uri + '\n'))
                try:
                    main(['reveal', '--stdin', '--batch', '--format', 'json'])
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            entries = json.loads(out.getvalue())['results']
            assert len(entries) == 1, entries
            self._cache[key] = (direct_code, direct, code, entries[0])
        return self._cache[key]

    def fixture_uri(self, scheme):
        if scheme == 'xlsx' and not (self.root / 'proj' / 'data.xlsx').exists():
            pytest.skip('openpyxl not installed')
        if scheme == 'git' and not shutil.which('git'):
            pytest.skip('git not installed')
        return FIXTURE_URIS[scheme]

    def run_fixture(self, scheme, **flags):
        return self.run(self.fixture_uri(scheme), **flags)


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    root = tmp_path_factory.mktemp('contract_harness')
    _build_tree(root)
    return _Harness(root)


def _strings(obj, path=''):
    """(json-path, string) for every string value and key in `obj`."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield f'{path}.<key>', str(key)
            yield from _strings(value, f'{path}.{key}')
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _strings(value, f'{path}[{i}]')


# -- coverage --------------------------------------------------------------------------

def test_every_registered_adapter_is_covered():
    registered = set(_registered())
    covered = set(FIXTURE_URIS) | set(NOT_RUNNABLE)
    assert not set(FIXTURE_URIS) & set(NOT_RUNNABLE)
    assert registered - covered == set(), (
        'New adapter(s) with no contract-harness entry: add a FIXTURE_URIS row '
        '(or a NOT_RUNNABLE reason) in tests/test_output_contract_compliance.py')
    assert covered - registered == set(), 'Harness lists adapters that are no longer registered'


def test_known_violations_name_real_cases():
    for invariant, scheme in KNOWN_VIOLATIONS:
        assert invariant in ('contract', 'missing', 'error_exit', 'abs_path', 'truncation',
                             'subcommand', 'subcommand_abs_path', 'own_cap', 'failure')
        assert scheme in (SUBCOMMAND_ARGV if invariant.startswith('subcommand') else FIXTURE_URIS)


# -- invariants ------------------------------------------------------------------------

@pytest.mark.parametrize('scheme', _cases('contract', sorted(FIXTURE_URIS)))
def test_contract(harness, scheme):
    code, payload, err = harness.run_fixture(scheme)
    assert code == 0, f'{scheme}: exit {code}: {err[:300]}'
    assert isinstance(payload, dict), f'{scheme}: --format json did not print a JSON object'
    for field in _REQUIRED_FIELDS:
        assert payload.get(field), f'{scheme}: missing or empty contract field {field!r}'
    assert payload['source_type'] in _VALID_SOURCE_TYPES, payload['source_type']
    schema = adapters_base.get_adapter_class(scheme).get_schema() or {}
    declared = {ot['type'] for ot in schema.get('output_types', [])}
    if declared:
        assert payload['type'] in declared, (
            f"{scheme}: type {payload['type']!r} is not in the schema's output_types")


@pytest.mark.parametrize('scheme', _cases('missing', sorted(FIXTURE_URIS)))
def test_missing_resource_is_an_error(harness, scheme):
    code, _, err = harness.run(MISSING_URIS.get(scheme, f'{scheme}://nonexistent_zz_1513'))
    assert code != 0, f'{scheme}: a nonexistent resource exited 0 (stderr: {err[:200]!r})'


@pytest.mark.parametrize('scheme', _cases('error_exit', sorted(FIXTURE_URIS)))
def test_error_in_result_exits_nonzero(harness, scheme):
    code, payload, _ = harness.run_fixture(scheme)
    if isinstance(payload, dict) and payload.get('error'):
        assert code != 0, f"{scheme}: result carries error {payload['error']!r} but exited 0"


def _missing_uri(scheme):
    return MISSING_URIS.get(scheme, f'{scheme}://nonexistent_zz_1513')


@pytest.mark.parametrize('scheme', _cases('failure', sorted(FIXTURE_URIS)))
def test_a_failure_reads_the_same_however_it_happened(harness, scheme, tmp_path):
    """Invariant 8: a failed query reports its error once, as one envelope, whether the
    adapter returned the error or raised it (BACK-1553)."""
    code, payload, _ = harness.run(_missing_uri(scheme))
    if code == 0:
        return  # not a failure: invariant 2 ('missing') owns an exit 0 here
    assert isinstance(payload, dict), f'{scheme}: a failure printed no JSON envelope'
    for field in _REQUIRED_FIELDS:
        assert payload.get(field), f'{scheme}: failure envelope lacks {field!r}'
    assert payload['contract_version'] == CONTRACT_VERSION, (
        f"{scheme}: failure envelope says contract_version {payload['contract_version']!r}")
    assert payload['source_type'] in _VALID_SOURCE_TYPES | {'unknown'}, payload['source_type']
    error = payload.get('error')
    assert error, f'{scheme}: exited {code} with no top-level error in its envelope'

    also = tmp_path / 'also.json'
    _, out, err = harness.run_raw(_missing_uri(scheme), format='text', also_json=str(also))
    first = error.splitlines()[0]
    assert (out + err).count(first) == 1, (
        f'{scheme}: text printed the error {(out + err).count(first)} times, not once '
        f'(stdout {out[:120]!r}, stderr {err[:120]!r})')
    assert first not in out, f'{scheme}: the error went to stdout, not stderr'
    assert also.exists() and json.loads(also.read_text(encoding='utf-8')).get('error') == error, (
        f'{scheme}: --also-json did not get the failure envelope')


def test_the_failure_invariant_bites(harness):
    """Positive control: the missing resources fail both ways, so invariant 8 compares an
    error an adapter returned with one the router built from a raise."""
    built, returned = [], []
    for scheme in sorted(FIXTURE_URIS):
        code, payload, _ = harness.run(_missing_uri(scheme))
        if code and isinstance(payload, dict):
            codes = {e.get('code') for e in (payload.get('meta') or {}).get('errors') or []}
            (built if codes & {'adapter_error', 'element_not_found'} else returned).append(scheme)
    assert {'ast', 'env', 'git', 'json'} <= set(built), built
    assert returned, 'no adapter returned its own failure on a missing resource'


@pytest.mark.parametrize('scheme', _cases(
    'abs_path', sorted(s for s, uri in FIXTURE_URIS.items() if '://proj' in uri)))
def test_no_absolute_fixture_path_in_result(harness, scheme):
    _, payload, _ = harness.run_fixture(scheme)
    leaks = _path_leaks(harness, payload)
    assert not leaks, f'{scheme}: absolute path in a result for a relative input: {leaks[:3]}'


def _path_leaks(harness, payload):
    """Strings naming the fixture by its absolute path (BACK-1366)."""
    return [(where, value) for where, value in _strings(payload)
            if any(needle in value for needle in harness.needles)]


def _windows_spellings(root):
    """Every multi-part relative path in the fixture, spelled with '\\' -- 'proj\\app.py',
    and the same file below each of its directories ('pkg\\util.py')."""
    spellings = set()
    for path in root.rglob('*'):
        parts = path.relative_to(root).parts
        spellings.update('\\'.join(parts[i:]) for i in range(len(parts) - 1))
    return spellings


def _native_separators(harness, payload):
    """Strings spelling a fixture path with Windows separators (BACK-1586)."""
    if not hasattr(harness, 'windows_spellings'):
        harness.windows_spellings = _windows_spellings(harness.root)
    return [(where, value) for where, value in _strings(payload)
            if '\\' in value and any(needle in value for needle in harness.windows_spellings)]


@pytest.mark.parametrize('name', _cases('subcommand_abs_path', sorted(SUBCOMMAND_ARGV)))
def test_no_absolute_fixture_path_in_subcommand_result(harness, name):
    _, out, _, _ = harness.run_subcommand(name, *SUBCOMMAND_ARGV[name], '--format', 'json')
    leaks = _path_leaks(harness, json.loads(out))
    assert not leaks, f'reveal {name}: absolute path in a result for a relative input: {leaks[:3]}'


@pytest.mark.parametrize('scheme', sorted(s for s, uri in FIXTURE_URIS.items() if '://proj' in uri))
def test_paths_use_posix_separators(harness, scheme):
    _, payload, _ = harness.run_fixture(scheme)
    native = _native_separators(harness, payload)
    assert not native, f'{scheme}: a path written with Windows separators: {native[:3]}'


@pytest.mark.parametrize('name', sorted(SUBCOMMAND_ARGV))
def test_subcommand_paths_use_posix_separators(harness, name):
    _, out, _, _ = harness.run_subcommand(name, *SUBCOMMAND_ARGV[name], '--format', 'json')
    native = _native_separators(harness, json.loads(out))
    assert not native, f'reveal {name}: a path written with Windows separators: {native[:3]}'


def test_the_posix_path_invariant_bites(harness):
    """Positive control: the needles are the fixture's own files spelled the Windows way, so
    a clean run on Linux is not a needle set that never matches. A regex escape is not one."""
    payload = {'results': [{'file': 'proj\\app.py'}], 'pattern': r'\d+\.py'}
    assert [w for w, _ in _native_separators(harness, payload)] == ['.results[0].file']


def test_the_abs_path_invariant_bites(harness):
    """Positive control: named by its absolute path, the target comes back that way, and
    the check above sees it -- so a clean relative run is not a needle that never matches."""
    absolute = str(harness.root / 'proj')
    _, out, _, _ = harness.run_subcommand('overview', absolute, '--format', 'json')
    assert _path_leaks(harness, json.loads(out))


def _cut_lists(full, cut):
    """Top-level lists that are shorter in `cut` than in `full`."""
    if not (isinstance(full, dict) and isinstance(cut, dict)):
        return []
    return sorted(key for key, value in full.items()
                  if isinstance(value, list) and isinstance(cut.get(key), list)
                  and len(cut[key]) < len(value))


@pytest.mark.parametrize('scheme', _cases('truncation', sorted(FIXTURE_URIS)))
def test_a_cut_list_is_disclosed(harness, scheme):
    _, full, _ = harness.run_fixture(scheme)
    _, cut, _ = harness.run_fixture(scheme, head=1)
    shortened = _cut_lists(full, cut)
    if not shortened:
        return
    disclosed = {entry.get('field') for entry in truncations_of(cut)}
    assert set(shortened) <= disclosed, (
        f'{scheme}: --head 1 cut {shortened} but the result discloses only {sorted(disclosed)}')
    _, text, _ = harness.run_raw(harness.fixture_uri(scheme), format='text', head=1)
    for field in shortened:
        assert f'⚠ Truncated {field}: ' in text, f'{scheme}: text render hides the cut of {field}'


def test_the_truncation_invariant_bites(harness):
    """Positive control: on this fixture --head 1 really cuts some adapters' lists, so
    test_a_cut_list_is_disclosed is not vacuously green."""
    expected = ['ast', 'classify', 'pack', 'reveal', 'stats']
    bitten = [scheme for scheme in expected
              if _cut_lists(harness.run_fixture(scheme)[1], harness.run_fixture(scheme, head=1)[1])]
    assert bitten == expected


# --- Invariant 6: subcommand forms (BACK-1544) ---------------------------------------------

def test_every_subcommand_is_covered():
    covered = set(SUBCOMMAND_ARGV) | set(NOT_A_QUERY)
    assert not set(SUBCOMMAND_ARGV) & set(NOT_A_QUERY)
    assert set(COMMANDS) - covered == set(), (
        'New subcommand(s) with no contract-harness entry: add a SUBCOMMAND_ARGV row '
        '(or a NOT_A_QUERY reason) in tests/test_output_contract_compliance.py')
    assert covered - set(COMMANDS) == set(), 'Harness lists subcommands that no longer exist'


@pytest.mark.parametrize('name', _cases('subcommand', sorted(SUBCOMMAND_ARGV)))
def test_subcommand_result_leaves_through_the_seam(harness, name):
    argv = SUBCOMMAND_ARGV[name] + SUBCOMMAND_CUT_ARGV.get(name, [])
    for fmt in ('json', 'text'):
        _, _, err, results = harness.run_subcommand(name, *argv, '--format', fmt)
        assert results, (
            f'reveal {name} --format {fmt} printed its result without emit_subcommand_result '
            f'(cli/routing/subcommand.py), so a failed or cut answer goes unreported. '
            f'stderr: {err[-300:]}')
    # The envelope (BACK-906) under the subcommand's own name, conforming to the same
    # contract version as its URI twin (BACK-1178: pack's said 1.0 to pack://'s 1.1).
    _, out, _, _ = harness.run_subcommand(name, *argv, '--format', 'json')
    payload = json.loads(out)
    assert [f for f in _REQUIRED_FIELDS if f not in payload] == []
    assert payload['type'] == name
    if name in FIXTURE_URIS:
        _, twin, _ = harness.run_fixture(name)
        assert payload['contract_version'] == twin['contract_version'], (
            f'reveal {name} and {name}:// disagree about the contract their payload conforms to')
    _, text, _, results = harness.run_subcommand(name, *argv, '--format', 'text')
    for entry in truncations_of(results[-1]):
        assert f"⚠ Truncated {entry['message']}" in text, (
            f"reveal {name}: the result records a cut of {entry['field']} that the text hides")


def test_the_subcommand_cut_invariant_bites(harness):
    """Positive control: with SUBCOMMAND_CUT_ARGV the fixture really cuts these
    subcommands' lists, so the text-disclosure check above is not vacuously green."""
    for name, extra in SUBCOMMAND_CUT_ARGV.items():
        _, text, _, results = harness.run_subcommand(
            name, *SUBCOMMAND_ARGV[name], *extra, '--format', 'text')
        assert results and truncations_of(results[-1]), f'reveal {name} {extra}: nothing was cut'
        assert '⚠ Truncated ' in text


# --- Invariant 7: an adapter's own cap (BACK-1543) ----------------------------------------

def _cap_knobs(scheme):
    """The query keys that cap this adapter's lists: the one --all lifts, plus a declared
    top/limit. Derived from the adapter's own declarations, never a hand-written table."""
    cls = adapters_base.get_adapter_class(scheme)
    knobs = set()
    lifted = (getattr(cls, 'CLI_QUERY_FLAGS', None) or {}).get('all')
    if lifted:
        knobs.add(lifted.partition('=')[0])
    params = (cls.get_schema() or {}).get('query_params') or {}
    return sorted(knobs | {key for key in params if key in ('top', 'limit')})


def _own_cap_uris(scheme):
    return [FIXTURE_URIS[scheme].replace('://proj', '://wide')] + OWN_CAP_URIS.get(scheme, [])


def _lists(obj, path=()):
    """(path, list) for every list in a result, two dict levels deep, meta excluded."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'meta':
                continue
            if isinstance(value, list):
                yield path + (key,), value
            elif isinstance(value, dict) and len(path) < 2:
                yield from _lists(value, path + (key,))


def _knob_cuts(harness, scheme):
    """{'<view>?<knob>=1': ([shortened list paths], cut result, uncapped result)}, each view
    with each knob at 1 vs uncapped."""
    harness.fixture_uri(scheme)  # the same skips as the proj/ runs
    cuts = {}
    for uri in _own_cap_uris(scheme):
        sep = '&' if '?' in uri else '?'
        for knob in _cap_knobs(scheme):
            _, full, _ = harness.run(f'{uri}{sep}{knob}=1000000')
            _, cut, _ = harness.run(f'{uri}{sep}{knob}=1')
            whole, part = dict(_lists(full)), dict(_lists(cut))
            cuts[f'{uri}{sep}{knob}=1'] = (
                sorted(p for p, v in whole.items() if p in part and len(part[p]) < len(v)),
                cut, full)
    return cuts


def _names(path):
    """The field names a cut of the list at ``path`` may be recorded under: its key, or
    its dotted path when it is nested (git:// root's ``commits.recent``)."""
    return {path[-1], '.'.join(path)}


@pytest.mark.parametrize('scheme', _cases('own_cap', sorted(
    s for s in FIXTURE_URIS if _cap_knobs(s))))
def test_an_adapters_own_cap_is_disclosed(harness, scheme):
    hidden = {}
    for run, (shortened, cut, _) in _knob_cuts(harness, scheme).items():
        disclosed = {entry.get('field') for entry in truncations_of(cut)}
        missed = ['.'.join(path) for path in shortened if not _names(path) & disclosed]
        if missed:
            hidden[run] = missed
    assert not hidden, (
        f'cut without saying so: {hidden}. Record it with note_truncation '
        f'(reveal/utils/results.py), or compose(..., cut_as=...)')


@pytest.mark.parametrize('scheme', _cases('own_cap_prefix', sorted(
    s for s in FIXTURE_URIS if _cap_knobs(s))))
def test_an_adapters_own_cap_keeps_the_first_n(harness, scheme):
    """A cap cuts the answer: the capped list is the uncapped list's first N. A cap that
    bounds what is read instead (git walked 1 commit, then sorted it) answers a different
    question."""
    wrong = {}
    for run, (shortened, cut, full) in _knob_cuts(harness, scheme).items():
        whole, part = dict(_lists(full)), dict(_lists(cut))
        for path in shortened:
            if part[path] != whole[path][:len(part[path])]:
                wrong[f"{run} {'.'.join(path)}"] = (part[path], whole[path][:len(part[path])])
    assert not wrong, f'capped list is not the first N of the uncapped one: {wrong}'


@pytest.mark.parametrize('scheme', _cases('own_cap_total', sorted(
    s for s in FIXTURE_URIS if _cap_knobs(s))))
def test_a_disclosed_total_is_the_real_total(harness, scheme):
    """A cut says how many there are: the uncapped length, or at most it for a lower bound
    (``exact: false``, a walk that stopped one past the page)."""
    wrong = {}
    for run, (shortened, cut, full) in _knob_cuts(harness, scheme).items():
        whole = dict(_lists(full))
        for path in shortened:
            for entry in truncations_of(cut):
                if entry.get('field') not in _names(path):
                    continue
                real = len(whole[path])
                honest = (entry['total'] == real if entry.get('exact', True)
                          else entry['shown'] < entry['total'] <= real)
                if not honest:
                    wrong[f"{run} {'.'.join(path)}"] = (
                        entry['total'], entry.get('exact', True), real)
    assert not wrong, f'disclosed (total, exact) vs the real length: {wrong}'


def test_the_own_cap_invariant_bites(harness):
    """Positive control: on wide/ a knob at 1 really cuts these adapters' lists, so
    test_an_adapters_own_cap_is_disclosed is not vacuously green."""
    expected = ['ast', 'calls', 'depends', 'git', 'hotspots', 'imports', 'json', 'overview',
                'patches', 'stats', 'xlsx']
    bitten = [scheme for scheme in sorted(s for s in FIXTURE_URIS if _cap_knobs(s))
              if any(shortened for shortened, _, _ in _knob_cuts(harness, scheme).values())]
    assert bitten == expected


def _batch_uris(harness, scheme):
    return (harness.fixture_uri(scheme), _missing_uri(scheme), *BATCH_URIS.get(scheme, ()))


def _expected_batch_status(code, payload):
    if code:
        return 'error'
    return 'not_applicable' if outcome_of(payload) == 'not_applicable' else 'success'


@pytest.mark.parametrize('scheme', _cases('batch', sorted(FIXTURE_URIS)))
def test_batch_answers_like_the_uri(harness, scheme):
    """Invariant 9: a URI piped to --batch gets the answer `reveal URI` gives, and a failure
    there is a failure here (BACK-1554)."""
    for uri in _batch_uris(harness, scheme):
        code, payload, batch_code, entry = harness.run_batch(uri)
        expected = _expected_batch_status(code, payload)
        assert entry['status'] == expected, (
            f"{uri}: --batch says {entry['status']!r}, the URI form exits {code} ({expected!r})")
        assert entry.get('data') == payload, f'{uri}: --batch answered differently from the URI form'
        assert batch_code == (2 if expected == 'error' else 0), (
            f'{uri}: --batch exited {batch_code} for a {expected!r} entry')


def test_the_batch_invariant_bites(harness):
    """Positive control: invariant 9 compares successes, failures and a not-applicable
    answer, and the fixture answers are not empty, so equal answers are not vacuous."""
    statuses = {}
    for scheme in sorted(FIXTURE_URIS):
        for uri in _batch_uris(harness, scheme):
            code, payload, _, _ = harness.run_batch(uri)
            statuses.setdefault(_expected_batch_status(code, payload), []).append(uri)
    assert {'success', 'error', 'not_applicable'} <= set(statuses), statuses
    *_, ast_entry = harness.run_batch(harness.fixture_uri('ast'))
    assert ast_entry['data']['results'], 'ast://proj found nothing: the fixture answer is empty'
