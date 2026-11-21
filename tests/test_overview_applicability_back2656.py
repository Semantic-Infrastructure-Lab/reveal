"""Overview and its retired spelling Architecture declare which answers read each control (COMMAND_MODEL
"Applicability", BACK-2656).

``against=REF`` selects the comparison answer (``overview_diff``); without it the answer is the project map
(``overview``). The map's own controls, ``imports`` (legacy word ``no_imports``) and ``all`` (legacy word ``verbose``), are not read by the
comparison: given there, even false, the request is refused before analysis with the shared message on every form,
as the comparison's own hand check refused them before. ``--all`` is a satisfied no-op on the comparison, which has no
cap it lifts (Scott 2026-11-18): it answers quietly as without it. ``top`` is read by both answers.
"""
import json
from urllib.parse import quote

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct as run  # noqa: E402
from reveal import api  # noqa: E402
from reveal.errors import RequestValidationError  # noqa: E402

NOUNS = ('overview', 'architecture')
REFUSAL = ("control '{control}' is not read by this answer (overview_diff, against, against=HEAD); "
           "{control} is read by: overview; controls this answer reads: ")


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    repo = pygit2.init_repository(str(root))
    (root / 'app.py').write_text('from helper import VALUE\n\ndef choose(v):\n    return VALUE\n', encoding='utf-8')
    (root / 'helper.py').write_text('VALUE = 1\n', encoding='utf-8')
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    repo.create_commit('HEAD', signature, signature, 'fixture', repo.index.write_tree(), [])
    (root / 'helper.py').write_text('import app\nVALUE = 1\n', encoding='utf-8')  # a change to compare
    monkeypatch.chdir(tmp_path)
    return root


def _uri(noun, query):
    return f'{noun}://proj?{query}'


def _json(response):
    return json.loads(response.stdout) if response.stdout.strip().startswith('{') else {}


def _without_volatile(doc):
    doc = json.loads(json.dumps(doc))
    for key in ('execution', 'timing', 'elapsed', 'generated_at'):
        doc.pop(key, None)
    (doc.get('meta') or {}).pop('timing', None)
    return doc


@pytest.mark.parametrize('noun', NOUNS)
# A legacy word is refused under the control it stands for, as verbose is under all (no_imports -> imports, BACK-2622).
@pytest.mark.parametrize('query,control', [('no_imports=true', 'imports'), ('no_imports=false', 'imports'),
                                           ('imports=off', 'imports'), ('all=true', 'all'), ('all=false', 'all'), ('verbose=true', 'all')])
def test_the_comparison_refuses_a_map_control_on_the_uri(project, noun, query, control):
    response = run(_uri(noun, f'against=HEAD&{query}'), '--format', 'json')
    assert response.returncode == 2, (response.returncode, response.stderr)
    assert REFUSAL.format(control=control) in response.stderr, response.stderr
    answer = _json(response)  # the invalid-request document keeps the comparison's identity
    assert answer['type'] == 'overview_diff' and answer['error'], answer


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('argv,control,global_flag', [(('--no-imports',), 'imports', False),
                                                      (('--imports', 'off'), 'imports', False),
                                                      (('--verbose',), 'all', True)])
def test_the_comparison_refuses_a_map_control_on_the_subcommand_and_the_uri_with_a_flag(project, noun, argv, control,
                                                                                         global_flag):
    forms = [(noun, 'proj', '--against', 'HEAD', *argv)]
    if global_flag:  # the URI form takes global flags; a noun's own flag is a query key there
        forms.append((_uri(noun, 'against=HEAD'), *argv))
    for form in forms:
        response = run(*form, '--format', 'json')
        assert response.returncode == 2, (form, response.returncode, response.stderr)
        assert REFUSAL.format(control=control) in response.stderr, (form, response.stderr)


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('keywords,query,control', [({'no_imports': True}, '', 'imports'),
                                                    ({'no_imports': False}, '', 'imports'),
                                                    ({'imports': 'off'}, '', 'imports'),
                                                    ({'all': True}, '', 'all'),
                                                    ({}, '&verbose=true', 'all')])
def test_the_comparison_refuses_a_map_control_on_the_api_before_analysis(project, monkeypatch, noun, keywords, query,
                                                                         control):
    from reveal.adapters import overview
    from reveal.diff import architecture_diff

    def forbidden(*args, **kwargs):
        raise AssertionError('a refused comparison reached analysis')
    for owner, name in ((overview, '_run_scope'), (overview, '_run_imports_analysis'),
                        (architecture_diff, 'run_architecture_diff')):
        monkeypatch.setattr(owner, name, forbidden)
    with pytest.raises(RequestValidationError, match=f"'{control}' is not read by this answer"):
        api.query(_uri(noun, 'against=HEAD' + query), **keywords)


def test_the_comparison_refuses_a_map_control_on_mcp(project):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    for noun in NOUNS:
        text = reveal_query(_uri(noun, 'against=HEAD&no_imports=true'))
        assert REFUSAL.format(control='imports') in text, text


@pytest.mark.parametrize('noun', NOUNS)
def test_all_is_satisfied_quietly_on_the_comparison(project, noun):
    """The comparison has no cap --all lifts: --all answers as without it, exit 0, no note (Scott 2026-11-18)."""
    for form in ((_uri(noun, 'against=HEAD'),), (noun, 'proj', '--against', 'HEAD')):
        plain, lifted = run(*form, '--format', 'json'), run(*form, '--all', '--format', 'json')
        assert plain.returncode == lifted.returncode == 0, (form, plain.stderr, lifted.stderr)
        assert _without_volatile(_json(lifted)) == _without_volatile(_json(plain)), form
        assert '--all' not in lifted.stderr, lifted.stderr


# --- negative controls: the answers that read these controls answer as before -------------------------------------

@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('query', ['no_imports=true', 'no_imports=false', 'all=true', 'verbose=true', 'top=2'])
def test_the_map_reads_its_controls(project, noun, query):
    response = run(_uri(noun, query), '--format', 'json')
    assert response.returncode == 0, response.stderr
    assert _json(response)['type'] == 'overview'
    assert 'not read by this answer' not in response.stderr


@pytest.mark.parametrize('noun', NOUNS)
def test_the_comparison_reads_top(project, noun):
    for form in ((_uri(noun, 'against=HEAD&top=2'),), (noun, 'proj', '--against', 'HEAD', '--top', '2')):
        response = run(*form, '--format', 'json')
        assert response.returncode == 0, (form, response.stderr)
        answer = _json(response)
        assert answer['type'] == 'overview_diff'
        assert answer['deltas']['complexity_centroid']['top_n'] == 8  # max(top, 1) * 4
    assert api.query(_uri(noun, 'against=HEAD'), top=0)['deltas']['complexity_centroid']['top_n'] == 4


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('query', ['against=HEAD&no_git=true', 'no_git=true'])
def test_an_obsolete_control_keeps_its_own_message_on_both_answers(project, noun, query):
    response = run(_uri(noun, query), '--format', 'json')
    assert response.returncode == 2
    assert 'overview no longer collects Git history' in response.stderr, response.stderr


def test_a_quoted_path_with_a_refused_control_keeps_its_identity(tmp_path, monkeypatch, project):
    spaced = tmp_path / 'project space'
    project.rename(spaced)
    response = run(f"overview://{quote(spaced.as_posix(), safe='/.:')}?against=HEAD&all=true", '--format', 'json')
    assert response.returncode == 2 and REFUSAL.format(control='all') in response.stderr, response.stderr
    assert _json(response)['type'] == 'overview_diff'
