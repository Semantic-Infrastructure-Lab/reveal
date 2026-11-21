"""BACK-2721: the gitignore walk policy counts as used when the answer read it, in both of its spellings.

``?respect_gitignore=off`` on a walking noun changed the answer (the ignored file appeared) yet the answer said
'Input respect_gitignore has no effect for this operation': the outer ledger saw the key and nothing marked it used
when a walk read the policy (``--exclude`` has ``exclusions_consulted``; gitignore had no counterpart). Its flag
spelling ``--respect-gitignore off`` was never judged at all (process-global), so on a target whose answer reads no
walk policy the URI warned and the flag was silent: two spellings of one request, two answers (conformance rule 24).
"""
import json

import pytest
from conftest import _run_reveal_direct
from test_declared_parity_back2053 import project  # noqa: F401  (the fixture)

FIELD = 'respect_gitignore'


def _ignoring(project):  # noqa: F811
    (project / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    (project / 'ignored.py').write_text('def ignored():\n    return 1\n', encoding='utf-8')


def _answer(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _unused(answer):
    """The unused-input facts naming the walk policy (either spelling)."""
    return [w for w in answer.get('meta', {}).get('warnings', [])
            if w.get('type') in ('unused_flag', 'unused_query_param')
            and any(FIELD in field or 'gitignore' in field for field in w.get('fields', []))]


def _files(answer):
    return {row.get('file') for row in answer.get('results', [])}


@pytest.mark.parametrize('noun', ['ast', 'markdown', 'imports', 'metrics'])
def test_a_walk_that_read_the_policy_says_nothing_about_it(project, noun):  # noqa: F811
    _ignoring(project)
    uri = _answer(f'{noun}://proj?{FIELD}=off')
    typed = _answer(noun, 'proj', '--respect-gitignore', 'off')
    assert _unused(uri) == [] and _unused(typed) == []


def test_the_positive_control_the_policy_changed_the_answer(project):  # noqa: F811
    """Without this the no-warning assertion above could pass on an answer the policy never reached."""
    _ignoring(project)
    assert 'proj/ignored.py' in _files(_answer(f'ast://proj?{FIELD}=off'))
    assert 'proj/ignored.py' in _files(_answer('ast', 'proj', '--respect-gitignore', 'off'))
    assert 'proj/ignored.py' not in _files(_answer('ast', 'proj'))


def test_an_answer_that_reads_no_walk_policy_says_so_in_both_spellings(project):  # noqa: F811
    """A file read never reads the walk policy. The URI said so and the flag, exempt as process-global, did not: now
    both name the control, each as the caller spelled it (rule 24 compares them by the control they name)."""
    _ignoring(project)
    uri = _unused(_answer(f'metrics://proj/app.py?{FIELD}=off'))
    typed = _unused(_answer('metrics', 'proj/app.py', '--respect-gitignore', 'off'))
    assert [w['fields'] for w in uri] == [[FIELD]]
    assert [w['fields'] for w in typed] == [['--respect-gitignore']]


def test_the_policy_left_at_its_default_is_not_named(project):  # noqa: F811
    """Only a policy the caller changed is judged: an explicit 'on' equals the default and says nothing."""
    assert _unused(_answer('metrics', 'proj/app.py', '--respect-gitignore', 'on')) == []
