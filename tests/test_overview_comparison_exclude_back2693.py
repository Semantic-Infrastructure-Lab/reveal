"""The overview comparison applies the request's exclude on every transport (BACK-2693).

``reveal overview P --against REF --exclude X`` leaves X out of both snapshots. The same request as a URI key
(``overview://P?against=REF&exclude=X``), as an ``api.query`` keyword or through the MCP query tool answered as if no
exclude was given: the comparison walked only the scope the CLI publishes for its ``--exclude`` flag, never the
request's own ``exclude`` control, which the plain overview applies.

Config/env ``ignore`` (``REVEAL_IGNORE``, ``.reveal.yaml`` ``ignore:``) is its own always-on scoping setting that hides
trees from every walk (COMMAND_MODEL "Defaults", BACK-1201); here it is a control that already holds on every transport,
and it combines with the request's exclude (BACK-2654 rule 14).

The fixture's working tree differs from HEAD both inside the excluded tree (``vendor/``) and outside it (``pkg/``), so a
dropped exclude changes the answer and a too-wide one empties it.
"""
import json

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct as run  # noqa: E402
from reveal import api  # noqa: E402
from reveal.mcp_server import reveal_query  # noqa: E402
from reveal.utils.request_cache import reset_request_caches  # noqa: E402

_EXCLUDED = 'vendor'


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A one-commit repository whose working tree then changes in pkg/ and in vendor/."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('REVEAL_IGNORE', raising=False)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'vendor').mkdir()
    (root / 'pkg' / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    (root / 'vendor' / 'b.py').write_text('def b():\n    return 2\n', encoding='utf-8')
    repo = pygit2.init_repository(str(root))
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid', 1700000000, 0)
    repo.create_commit('HEAD', signature, signature, 'fixture', repo.index.write_tree(), [])
    (root / 'pkg' / 'a.py').write_text(
        'import os\nfrom pkg import helper\n\n\ndef a():\n    if os.sep:\n        for i in range(3):\n'
        '            if i:\n                return 1\n    return 2\n', encoding='utf-8')
    (root / 'pkg' / 'helper.py').write_text('def helper():\n    return 0\n', encoding='utf-8')
    (root / 'vendor' / 'b.py').write_text(
        'import sys\nfrom vendor import extra\n\n\ndef b(x):\n    if x:\n        while x:\n'
        '            if sys.argv:\n                x -= 1\n    return 2\n', encoding='utf-8')
    (root / 'vendor' / 'extra.py').write_text('def extra():\n    return 0\n', encoding='utf-8')
    reset_request_caches()
    yield 'proj'
    reset_request_caches()


def _cli(*argv, code=0):
    response = run(*argv, '--format', 'json')
    assert response.returncode == code, (argv, response.stdout, response.stderr)
    return json.loads(response.stdout)


def _answer(doc):
    """The comparison as the CLI prints it; MCP's provenance manifest is the one field the CLI JSON lacks."""
    doc = json.loads(json.dumps(doc))
    doc.pop('execution', None)
    return doc


def _mentions(doc, tree):
    return f'{tree}/' in json.dumps(doc['deltas']) or f'"{tree}"' in json.dumps(doc['deltas'])


@pytest.fixture
def reference(project):
    """The CLI subcommand's answer with ``--exclude vendor``: the behaviour every other spelling must match."""
    excluded = _answer(_cli('overview', project, '--against', 'HEAD', '--exclude', _EXCLUDED))
    plain = _answer(_cli('overview', project, '--against', 'HEAD'))
    # The fixture measures something: vendor/ changed, so a dropped exclude would answer `plain`.
    assert _mentions(plain, _EXCLUDED) and not _mentions(excluded, _EXCLUDED)
    assert _mentions(excluded, 'pkg') and excluded != plain
    return excluded


def _request_spellings(project):
    uri = f'overview://{project}?against=HEAD&exclude={_EXCLUDED}'
    return {
        'URI key (CLI)': lambda: _cli(uri),
        'architecture:// URI key (CLI)': lambda: _cli(f'architecture://{project}?against=HEAD&exclude={_EXCLUDED}'),
        'api.query exclude keyword': lambda: api.query(f'overview://{project}', against='HEAD', exclude=[_EXCLUDED]),
        'api.query URI key': lambda: api.query(uri),
        'MCP reveal_query': lambda: json.loads(reveal_query(uri, provenance=True)),
    }


@pytest.mark.parametrize('spelling', ['URI key (CLI)', 'architecture:// URI key (CLI)',
                                      'api.query exclude keyword', 'api.query URI key', 'MCP reveal_query'])
def test_the_comparison_applies_the_requests_exclude(project, reference, spelling):
    answer = _answer(_request_spellings(project)[spelling]())
    answer['type'] = reference['type']  # architecture:// is the retired spelling of the same answer
    assert not _mentions(answer, _EXCLUDED), f'{spelling}: the comparison still measures {_EXCLUDED}/'
    assert answer == reference


def test_the_uri_form_with_a_flag_answers_as_the_subcommand(project, reference):
    """Unaffected control: the CLI publishes its --exclude flag's scope for the URI form too."""
    assert _answer(_cli(f'overview://{project}?against=HEAD', '--exclude', _EXCLUDED)) == reference


@pytest.mark.parametrize('spelling', ['URI key (CLI)', 'api.query'])
def test_the_plain_overview_already_applies_the_requests_exclude(project, spelling):
    """Unaffected sibling: without ``against`` the overview applies the same exclude on every spelling."""
    reference = _cli('overview', project, '--exclude', _EXCLUDED)
    answer = (_cli(f'overview://{project}?exclude={_EXCLUDED}') if spelling == 'URI key (CLI)'
              else json.loads(json.dumps(api.query(f'overview://{project}', exclude=[_EXCLUDED]))))
    assert answer['scope'] == reference['scope'] and answer['map'] == reference['map']
    assert 'vendor/' not in json.dumps(answer['map'])


@pytest.fixture(params=['REVEAL_IGNORE', '.reveal.yaml ignore:'])
def ignored(request, project, monkeypatch, tmp_path):
    """``vendor`` hidden by the always-on ignore setting, from the environment or the project config."""
    if request.param == 'REVEAL_IGNORE':
        monkeypatch.setenv('REVEAL_IGNORE', _EXCLUDED)
    else:
        (tmp_path / project / '.reveal.yaml').write_text(f'ignore:\n  - {_EXCLUDED}\n', encoding='utf-8')
    reset_request_caches()
    return request.param


def test_ignore_hides_the_tree_from_the_comparison_on_every_transport(project, ignored):
    """Control: ignore already reaches both snapshots on every transport (it is applied by the walk itself)."""
    uri = f'overview://{project}?against=HEAD'
    answers = {'subcommand': _cli('overview', project, '--against', 'HEAD'), 'URI': _cli(uri),
               'api.query': api.query(f'overview://{project}', against='HEAD'),
               'MCP': json.loads(reveal_query(uri, provenance=True))}
    for transport, answer in answers.items():
        assert not _mentions(_answer(answer), _EXCLUDED), f'{ignored} did not hide {_EXCLUDED}/ on {transport}'
        assert _mentions(_answer(answer), 'pkg')
    assert len({json.dumps(_answer(answer)['deltas'], sort_keys=True) for answer in answers.values()}) == 1


def test_ignore_and_the_requests_exclude_combine_on_the_comparison(project, ignored):
    """Rule 14: the ignore setting and the request's exclude both apply, on every transport. The second exclusion
    is a scanned source (``pkg/a.py``): an excluded import target stays visible as one, under ignore too."""
    other = 'pkg/a.py'
    reference = _answer(_cli('overview', project, '--against', 'HEAD', '--exclude', other))
    assert other not in json.dumps(reference['deltas']) and not _mentions(reference, _EXCLUDED)
    assert reference != _answer(_cli('overview', project, '--against', 'HEAD'))  # the exclude measures something
    uri = f'overview://{project}?against=HEAD&exclude={other}'
    answers = {'URI': _cli(uri), 'api.query': api.query(f'overview://{project}', against='HEAD', exclude=[other]),
               'MCP': json.loads(reveal_query(uri, provenance=True))}
    for transport, answer in answers.items():
        assert _answer(answer) == reference, f'{transport} with {ignored}: the request exclude was not applied'
