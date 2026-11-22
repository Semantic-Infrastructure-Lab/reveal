"""A where term on a field a closed-field noun does not declare is an invalid request on every transport (BACK-2731).

Git and Metrics declare their where fields (closed sets). ``?where=FIELD...`` and a bare ``?FIELD=`` already exit 2
naming the noun's fields (rule 3, the binder's one unknown-key check); ``--where`` on the subcommand, ``--where`` after
the URI, and the typed API (noun form and a ``where=`` keyword on the URI form) answered instead: 0 rows with exit 0, or
an ``unknown_filter_field`` typo warning. The check is the binder's, on every where term a request binds. An open-field
noun (AST, whose fields come from the data) still answers with its typo warning.
"""
import json

import pytest

from conftest import _run_reveal_in

pygit2 = pytest.importorskip('pygit2')

# (noun, an unknown field's term, a declared field's term, the arguments that select an answer reading where)
NOUNS = [
    ('git', 'authr=Ada', 'author=Ada', ('--view', 'history')),
    ('metrics', 'bogus>1', 'lines>1', ()),
]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.py').write_text('def one():\n    return 1\n', encoding='utf-8')
    r = pygit2.init_repository(str(root))
    r.index.add('a.py')
    r.index.write()
    sig = pygit2.Signature('Ada', 'ada@example.com', 1700000000, 0)
    r.create_commit('HEAD', sig, sig, 'c1', r.index.write_tree(), [])
    return root


def _uri_view(args):
    return '?view=' + args[1] if args else ''


def _cli(repo, *argv):
    run = _run_reveal_in(repo, *argv, '--format', 'json')
    return run.returncode, run.stderr


@pytest.mark.parametrize('noun,unknown,known,args', NOUNS, ids=[n[0] for n in NOUNS])
def test_an_unknown_where_field_exits_2_naming_it_on_every_cli_form(repo, noun, unknown, known, args):
    field = unknown.split('=')[0].split('>')[0]
    forms = [(noun, '.', *args, '--where', unknown),
             (f'{noun}://.{_uri_view(args)}', '--where', unknown),
             (f'{noun}://.{_uri_view(args)}{"&" if args else "?"}where={unknown}',)]  # the control: exits 2 already
    for argv in forms:
        code, stderr = _cli(repo, *argv)
        assert code == 2 and f"unsupported control '{field}'" in stderr, (argv, code, stderr)
    for argv in [(noun, '.', *args, '--where', known), (f'{noun}://.{_uri_view(args)}', '--where', known)]:
        code, stderr = _cli(repo, *argv)
        assert code == 0, (argv, stderr)


@pytest.mark.parametrize('noun,unknown,known,args', NOUNS, ids=[n[0] for n in NOUNS])
def test_an_unknown_where_field_is_refused_by_the_typed_api(repo, monkeypatch, noun, unknown, known, args):
    from reveal.api import query
    from reveal.errors import RequestValidationError
    monkeypatch.chdir(repo)
    controls = {'view': args[1]} if args else {}
    for call in (lambda where: query(noun, '.', where=where, **controls),
                 lambda where: query(f'{noun}://.{_uri_view(args)}', where=where)):
        with pytest.raises(RequestValidationError, match='unsupported control'):
            call(unknown)
        call(known)


def test_an_open_field_noun_still_answers_an_unknown_field_with_its_warning(repo):
    run = _run_reveal_in(repo, 'ast', '.', '--where', 'bogus=1', '--format', 'json')
    assert run.returncode == 0, run.stderr
    warnings = json.loads(run.stdout).get('meta', {}).get('warnings', [])
    assert any(w.get('type') == 'unknown_filter_field' for w in warnings), warnings
