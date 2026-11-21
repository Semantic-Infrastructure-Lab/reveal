"""BACK-2724: an invalid git ``bucket`` is an invalid request (exit 2, no request note), not a failed analysis.

``git://f?view=history&bucket=day`` exited 3 with an answer carrying the request note, because the adapter checked the
value at analysis time; its declaration now names its choices, so binding refuses it on every transport.
"""
import json

import pytest
from conftest import _run_reveal_direct
from test_declared_parity_back2053 import project  # noqa: F401  (the fixture)

MESSAGE = "bucket must be one of ('week', 'month'), got 'day'"


@pytest.mark.parametrize('argv', [
    ('git://proj/app.py?view=history&bucket=day',),
    ('git', 'proj/app.py', '--view', 'history', '--bucket', 'day'),
], ids=['uri', 'subcommand'])
def test_an_invalid_bucket_is_an_invalid_request(project, argv):  # noqa: F811
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 2, run.stderr
    assert MESSAGE in run.stderr
    assert 'request:' not in run.stdout  # a refused request recommends no command


def test_a_valid_bucket_still_answers(project):  # noqa: F811
    """The positive control: the declaration's choices are the values the timeline answers."""
    for bucket in ('week', 'month'):
        run = _run_reveal_direct('git', 'proj/app.py', '--view', 'history', '--bucket', bucket, '--format', 'json')
        assert run.returncode == 0, run.stderr
        assert json.loads(run.stdout)['bucket'] == bucket


def test_mcp_and_python_refuse_it_alike(project):  # noqa: F811
    from reveal import api
    from reveal.errors import RequestValidationError
    from reveal.mcp_server import reveal_run
    with pytest.raises(RequestValidationError, match=MESSAGE.replace('(', r'\(').replace(')', r'\)')):
        api.query('git://proj/app.py?view=history&bucket=day')
    with pytest.raises(RequestValidationError):
        api.query('git', 'proj/app.py', view='history', bucket='day')
    answer = reveal_run(['git', 'proj/app.py', '--view', 'history', '--bucket', 'day', '--format', 'json'])
    assert str(answer).startswith('[reveal error:') and MESSAGE in str(answer)
