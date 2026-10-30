"""URI resource binding reaches exclusions and preserves raw/typed boundaries."""
import json
from argparse import Namespace
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.base import get_adapter_class
from reveal.adapters.factory import _canonical_init
from reveal.errors import RequestValidationError
from reveal.cli.routing.uri import _preparation_answer, resolve_uri
from reveal.utils.results import AnalysisCompleteness, FailureCause


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project space'
    root.mkdir()
    for name in ('keep', 'omit'):
        (root / (name + '.py')).write_text(f'def {name}():\n    return 1\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('policy', ['flag', 'config'])
def test_encoded_resource_uses_actual_exclusion_scope(project, policy):
    flags = ['--exclude', 'omit.py'] if policy == 'flag' else []
    if policy == 'config':
        (project / '.reveal.yaml').write_text('ignore:\n  - omit.py\n', encoding='utf-8')
    answers = []
    for path in (project.as_posix(), quote(project.as_posix(), safe='/:' )):
        response = run('ast://' + path + '?type=function', *flags, '--format', 'json')
        assert response.returncode == 0, (response.stdout, response.stderr)
        answer = json.loads(response.stdout)
        assert {row['name'] for row in answer['results']} == {'keep'}
        answers.append(answer)
    assert answers[0] == answers[1]


@pytest.mark.parametrize('scheme', ['ast', 'surface', 'contracts', 'trace', 'overview',
    'architecture', 'calls', 'imports', 'metrics', 'stats', 'hotspots', 'deps',
    'patches', 'testability', 'pack'])
def test_declared_resource_codec_applies_to_factory_uri_paths(project, scheme):
    owner = get_adapter_class(scheme)
    query = 'from=keep' if scheme == 'trace' else ''
    original = _canonical_init(owner, project.as_posix() + ('?' + query if query else ''))
    bound = _canonical_init(owner, quote(project.as_posix(), safe='/:') + ('?' + query if query else ''))
    if scheme == 'imports':
        assert bound._target_path == original._target_path == project.resolve()
    else:
        assert Path(bound.path).resolve() == Path(original.path).resolve() == project.resolve()
    if scheme == 'ast':
        assert bound.query == original.query
    else:
        assert dict(bound.query_params) == dict(original.query_params)


def test_undeclared_raw_and_bound_typed_resources_remain_literal(project):
    class Raw:
        def __init__(self, resource, query=None, *, params=None):
            self.path, self.query, self.params = resource, query, params
    encoded = quote(project.as_posix(), safe='/:')
    assert _canonical_init(Raw, encoded).path == encoded
    literal = project.as_posix() + '/question?name.py'
    typed = _canonical_init(Raw, literal, params={'top': 0})
    assert typed.path == literal and typed.params == {'top': 0}


@pytest.mark.parametrize('encoding', ['%FF', '%00'])
def test_resolve_uri_returns_qualified_invalid_answer_before_analysis(tmp_path, encoding):
    answer = resolve_uri('ast://' + tmp_path.as_posix() + '/' + encoding,
                         Namespace(format='json'))
    assert answer.result['type'] == 'ast_query'
    assert ('UTF-8' if encoding == '%FF' else 'NUL') in answer.result['error']
    assert answer.execution_facts.completeness is AnalysisCompleteness.NOT_STARTED
    assert answer.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST})


@pytest.mark.parametrize('error,expected', [
    (RequestValidationError('bad resource'), FailureCause.INVALID_REQUEST),
    (ValueError('operational conversion failed'), FailureCause.ANALYSIS),
    (PermissionError('unreadable resource'), FailureCause.ANALYSIS),
])
def test_preparation_classifies_only_explicit_validation(error, expected):
    answer = _preparation_answer('ast://missing?show=dict-schemas', None,
                                  Namespace(format='json'), error)
    assert answer.result['type'] == 'ast_dict_schemas'
    assert answer.execution_facts.failures == frozenset({expected})
