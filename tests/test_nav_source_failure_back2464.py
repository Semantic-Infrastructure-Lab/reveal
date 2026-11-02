"""Mandatory source-authored nav failure contract; shell codes remain independent."""
import pytest

from reveal.errors import NavSourceFailure
from reveal.utils.results import AnalysisCompleteness, ExecutionFacts, FailureCause, failure_execution_facts

pytestmark = pytest.mark.component


@pytest.mark.parametrize('code', [0, 1, 3])
@pytest.mark.parametrize('cause', [FailureCause.INVALID_REQUEST, FailureCause.ANALYSIS])
def test_carrier_preserves_explicit_code_and_mandatory_facts(code, cause):
    facts = failure_execution_facts(cause)
    failure = NavSourceFailure(code, execution_facts=facts, public_diagnostic='Source unavailable\n  Inspect the request.')
    assert isinstance(failure, SystemExit) and not isinstance(failure, Exception)
    assert failure.code == code and failure.args == (code,)
    assert failure.execution_facts is facts
    assert failure.public_diagnostic == 'Source unavailable\n  Inspect the request.'
    with pytest.raises(SystemExit) as caught:
        raise failure
    assert caught.value is failure


def test_fields_are_required_and_plain_system_exit_has_no_authored_origin():
    with pytest.raises(TypeError):
        NavSourceFailure(1)
    ordinary = SystemExit(1)
    assert ordinary.code == 1 and not hasattr(ordinary, 'execution_facts')


@pytest.mark.parametrize('facts', [None, {}, 'failed'])
def test_untyped_facts_cannot_claim_authored_origin(facts):
    with pytest.raises(TypeError, match='ExecutionFacts'):
        NavSourceFailure(1, execution_facts=facts, public_diagnostic='unavailable')


@pytest.mark.parametrize('facts', [
    ExecutionFacts(AnalysisCompleteness.COMPLETE),
    ExecutionFacts(AnalysisCompleteness.INCOMPLETE, failures=frozenset({FailureCause.ANALYSIS})),
    ExecutionFacts(AnalysisCompleteness.NOT_STARTED),
    failure_execution_facts(FailureCause.OUTPUT),
])
def test_healthy_partial_or_non_source_facts_are_not_source_failure(facts):
    with pytest.raises(ValueError, match='failed source/selection'):
        NavSourceFailure(1, execution_facts=facts, public_diagnostic='unavailable')


@pytest.mark.parametrize('diagnostic', ['', '  ', None])
def test_diagnostic_is_required_public_text(diagnostic):
    with pytest.raises((TypeError, ValueError)):
        NavSourceFailure(1, execution_facts=failure_execution_facts(FailureCause.INVALID_REQUEST),
                         public_diagnostic=diagnostic)


def test_exit_code_is_explicit_integer_not_a_derived_fact():
    with pytest.raises(TypeError, match='integer'):
        NavSourceFailure(True, execution_facts=failure_execution_facts(FailureCause.ANALYSIS),
                         public_diagnostic='unavailable')


@pytest.mark.parametrize('error,cause', [(FileNotFoundError, FailureCause.INVALID_REQUEST),
                                       (PermissionError, FailureCause.ANALYSIS)])
def test_actual_constructor_failure_authors_facts_without_precheck(tmp_path, monkeypatch, error, cause):
    import errno
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    path = tmp_path / 'requested.py'
    reads = []

    def construct(request):
        reads.append(request)
        number = errno.ENOENT if error is FileNotFoundError else errno.EACCES
        raise error(number, 'controlled source read', str(path))

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    with pytest.raises(NavSourceFailure) as caught:
        _get_analyzer_or_exit(str(path), True, nav_source=True)
    assert reads == [str(path)]
    assert caught.value.code == 1
    assert caught.value.execution_facts == failure_execution_facts(cause)


@pytest.mark.parametrize('code', [0, 1, 3])
def test_default_off_helper_retains_plain_exit_override(tmp_path, monkeypatch, code):
    import errno
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    def construct(path):
        raise PermissionError(errno.EACCES, 'controlled source read', path)

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    with pytest.raises(SystemExit) as caught:
        _get_analyzer_or_exit(str(tmp_path / 'requested.py'), True, unreadable_exit_code=code)
    assert type(caught.value) is SystemExit and caught.value.code == code


def test_no_analyzer_is_explicitly_outside_this_adoption(tmp_path, monkeypatch):
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: None)
    with pytest.raises(SystemExit) as caught:
        _get_analyzer_or_exit(str(tmp_path / 'requested.unknown'), True, nav_source=True)
    assert type(caught.value) is SystemExit and caught.value.code == 1


@pytest.mark.parametrize('flags', [{'effects': True}, {'sideeffects': True}, {'boundary': True},
                                  {'inputs': True}, {'flow': ()}, {'varflow': 'value'},
                                  {'calls': 'FULL'}, {'scope': True}, {'around': 1}])
def test_handle_file_adopts_existing_nav_predicate_without_mutating_args(tmp_path, monkeypatch, flags):
    import errno
    from reveal.cli.defaults import _default_args
    from reveal.file_handler import handle_file
    import reveal.registry as registry

    args = _default_args(**flags)
    original = dict(vars(args))
    reads = []

    def construct(path):
        reads.append(path)
        raise FileNotFoundError(errno.ENOENT, 'controlled source read', path)

    monkeypatch.setattr(registry, 'get_analyzer', lambda *a, **kw: construct)
    path = str(tmp_path / 'requested.py')
    with pytest.raises(NavSourceFailure):
        handle_file(path, ':2', False, 'text', args)
    assert reads == [path] and vars(args) == original


@pytest.mark.parametrize('filename_kind', ['dependency', 'unknown'])
def test_missing_dependency_or_unknown_filename_is_analysis_not_request(tmp_path, monkeypatch, filename_kind):
    import errno
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    requested = tmp_path / 'requested.py'
    dependency = tmp_path / 'parser-data.bin'

    def construct(path):
        filename = str(dependency) if filename_kind == 'dependency' else None
        raise FileNotFoundError(errno.ENOENT, 'required constructor data missing', filename)

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    with pytest.raises(NavSourceFailure) as caught:
        _get_analyzer_or_exit(str(requested), True, nav_source=True)
    assert caught.value.execution_facts == failure_execution_facts(FailureCause.ANALYSIS)
    assert str(dependency) not in caught.value.public_diagnostic


def test_public_read_diagnostic_spells_only_requested_path(monkeypatch):
    import errno
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    def construct(path):
        raise PermissionError(errno.EACCES, 'controlled read', 'PRIVATE_DEPENDENCY_FILENAME')

    monkeypatch.setattr(registry, 'get_analyzer', lambda *a, **kw: construct)
    with pytest.raises(NavSourceFailure) as caught:
        _get_analyzer_or_exit('pkg\\requested.py', True, nav_source=True)
    assert caught.value.public_diagnostic == 'Error: cannot read pkg/requested.py: controlled read'
    assert 'PRIVATE_DEPENDENCY_FILENAME' not in caught.value.public_diagnostic


def test_default_off_read_diagnostic_keeps_legacy_fallback(tmp_path, monkeypatch, capsys):
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    def construct(path):
        raise PermissionError('controlled legacy read')

    monkeypatch.setattr(registry, 'get_analyzer', lambda *a, **kw: construct)
    path = str(tmp_path / 'requested.py')
    with pytest.raises(SystemExit) as caught:
        _get_analyzer_or_exit(path, True)
    assert type(caught.value) is SystemExit
    assert capsys.readouterr().err == f'Error: cannot read {path}: controlled legacy read\n'


def test_definitive_selection_absence_authors_invalid_request_facts(tmp_path):
    from reveal.file_handler import _resolve_func_node
    from reveal.registry import get_analyzer

    path = tmp_path / 'source.py'
    path.write_text('def empty():\n    return 1\n', encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    with pytest.raises(NavSourceFailure) as caught:
        _resolve_func_node(analyzer, 'absent')
    assert caught.value.code == 1
    assert caught.value.execution_facts == failure_execution_facts(FailureCause.INVALID_REQUEST)
    assert caught.value.public_diagnostic.count('list available elements') == 1
    node, first, last = _resolve_func_node(analyzer, ':1-2')
    assert node is not None and (first, last) == (1, 2)
