"""Opt-in parser attribution observes requests without changing cache identity."""
import ast
import dataclasses
from importlib.metadata import version

import pytest

from reveal.core import treesitter_parse as tp
from reveal.utils import pyparse

pytestmark = pytest.mark.component
SOURCE = 'value = 1\n'


def _api():
    from reveal.utils.parse_audit import ParseAttributionError, capture_parses
    return capture_parses, ParseAttributionError


def _events(capture, kind):
    return [event for event in capture.events if event.event == kind]


def test_identical_content_paths_are_distinct_requests_sharing_one_artifact(tmp_path):
    capture_parses, _ = _api()
    with capture_parses(tmp_path) as capture:
        first = tp.get_tree('python', SOURCE, filename=tmp_path / 'a.py')
        second = tp.get_tree('python', SOURCE, filename=tmp_path / 'b.py')
    assert first is second
    assert [event.filename for event in _events(capture, 'request')] == [
        (tmp_path / 'a.py').resolve().as_posix(), (tmp_path / 'b.py').resolve().as_posix()]
    assert [event.scope for event in _events(capture, 'request')] == ['target', 'target']
    assert [event.outcome for event in _events(capture, 'outcome')] == ['built', 'cached']
    artifact, = _events(capture, 'artifact')
    assert artifact.request_id == _events(capture, 'request')[0].request_id
    assert artifact.parser == 'treesitter:python'
    assert artifact.domain == 'fullsource'
    assert artifact.parsed_hash == artifact.source_hash
    assert capture.metadata['parser_versions']['tree-sitter-language-pack'] == version('tree-sitter-language-pack')
    assert capture.metadata['parser_versions']['python.ast']
    assert SOURCE not in str(dataclasses.asdict(artifact))


def test_language_and_edited_content_stay_separate(tmp_path):
    capture_parses, _ = _api()
    with capture_parses(tmp_path) as capture:
        a = tp.get_tree('python', SOURCE, filename=tmp_path / 'a.py')
        b = tp.get_tree('javascript', SOURCE, filename=tmp_path / 'a.js')
        c = tp.get_tree('python', 'value = 2\n', filename=tmp_path / 'a.py')
    assert a is not b and a is not c
    assert len(_events(capture, 'artifact')) == 3
    assert len({event.source_hash for event in _events(capture, 'request')}) == 2


def test_python_direct_builds_keep_each_target_identity(tmp_path):
    capture_parses, _ = _api()
    with capture_parses(tmp_path) as capture:
        a = pyparse.parse_python(SOURCE, tmp_path / 'a.py')
        b = pyparse.parse_python(SOURCE, tmp_path / 'b.py')
    assert isinstance(a, ast.Module) and a is not b
    assert [event.filename for event in _events(capture, 'artifact')] == [
        (tmp_path / 'a.py').resolve().as_posix(), (tmp_path / 'b.py').resolve().as_posix()]
    assert len(_events(capture, 'request')) == len(_events(capture, 'attempt')) == 2
    assert [event.outcome for event in _events(capture, 'outcome')] == ['built', 'built']


def test_bom_hash_keeps_original_source_identity(tmp_path):
    capture_parses, _ = _api()
    with capture_parses(tmp_path) as capture:
        pyparse.parse_python('\ufeff' + SOURCE, tmp_path / 'bom.py')
    request, = _events(capture, 'request')
    artifact, = _events(capture, 'artifact')
    assert request.source_hash == artifact.source_hash
    assert artifact.parsed_hash != request.source_hash


def test_compat_attempts_are_not_successful_artifacts(tmp_path, monkeypatch):
    capture_parses, _ = _api()
    real = pyparse.ast.parse
    source = 'compat_marker\n'

    def parse(content, *args, **kwargs):
        if content == source:
            raise SyntaxError('exercise existing compatibility retry')
        return real(content, *args, **kwargs)

    monkeypatch.setattr(pyparse.ast, 'parse', parse)
    monkeypatch.setattr(pyparse, 'downlevel_source', lambda content: SOURCE)
    with capture_parses(tmp_path) as capture:
        tree = pyparse.parse_python(source, tmp_path / 'compat.py')
    assert isinstance(tree, ast.Module)
    assert [event.phase for event in _events(capture, 'attempt')] == ['original', 'compat']
    assert [event.error for event in _events(capture, 'failure')] == ['SyntaxError']
    artifact, = _events(capture, 'artifact')
    assert artifact.phase == 'compat' and artifact.source_hash != artifact.parsed_hash
    assert _events(capture, 'outcome')[0].outcome == 'built'


def test_original_failure_survives_and_capture_context_is_reset(tmp_path):
    capture_parses, _ = _api()
    with pytest.raises(SyntaxError):
        with capture_parses(tmp_path) as failed:
            pyparse.parse_python('def broken(:\n', tmp_path / 'broken.py')
    assert [event.outcome for event in _events(failed, 'outcome')] == ['failed']
    assert len(_events(failed, 'failure')) == 1
    failed.validate()
    count = len(failed.events)
    pyparse.parse_python(SOURCE)  # Missing filename is still supported outside capture.
    assert len(failed.events) == count


def test_grammar_failure_has_request_outcome_without_artifact(tmp_path, monkeypatch):
    capture_parses, _ = _api()

    def unavailable(language):
        raise tp.GrammarUnavailable(language, RuntimeError('unavailable fixture grammar'))

    monkeypatch.setattr(tp, 'get_parser', unavailable)
    with pytest.raises(tp.GrammarUnavailable):
        with capture_parses(tmp_path) as capture:
            tp.get_tree('missing', SOURCE, filename=tmp_path / 'a.py')
    assert len(_events(capture, 'request')) == 1
    assert not _events(capture, 'attempt') and not _events(capture, 'artifact')
    assert _events(capture, 'outcome')[0].outcome == 'failed'
    capture.validate()


def test_unknown_fullsource_is_rejected_instead_of_excluded(tmp_path):
    capture_parses, error = _api()
    with pytest.raises(error, match='fullsource.*filename'):
        with capture_parses(tmp_path) as capture:
            pyparse.parse_python(SOURCE)
    assert _events(capture, 'request')[0].scope == 'unattributed'


def test_explicit_domains_and_external_paths_remain_visible(tmp_path):
    capture_parses, _ = _api()
    with capture_parses(tmp_path / 'target') as capture:
        pyparse.parse_python(SOURCE, domain='snippet')
        pyparse.parse_python(SOURCE, domain='validation')
        pyparse.parse_python(SOURCE, tmp_path / 'external.py')
    assert [(event.domain, event.scope) for event in _events(capture, 'request')] == [
        ('snippet', 'unattributed'), ('validation', 'unattributed'), ('fullsource', 'external')]


def test_existing_warm_cache_remains_warm_and_domain_is_not_a_cache_key(tmp_path):
    capture_parses, _ = _api()
    existing = tp.get_tree('python', SOURCE)
    with capture_parses(tmp_path) as capture:
        assert tp.get_tree('python', SOURCE, filename=tmp_path / 'a.py') is existing
        assert tp.get_tree('python', SOURCE, domain='snippet') is existing
    assert not _events(capture, 'artifact')
    assert [event.outcome for event in _events(capture, 'outcome')] == ['cached', 'cached']


def test_duplicate_build_injection_is_visible_to_an_exact_ceiling(tmp_path, monkeypatch):
    capture_parses, _ = _api()
    physical = tp._parse_recent.__wrapped__

    def duplicate(language, source):
        physical(language, source)
        return physical(language, source)

    with monkeypatch.context() as scoped:
        scoped.setattr(tp, '_parse_recent', duplicate)
        with capture_parses(tmp_path) as capture:
            tp.get_tree('python', SOURCE, filename=tmp_path / 'a.py')
    assert len(_events(capture, 'request')) == 1
    assert len(_events(capture, 'artifact')) == 2
    with pytest.raises(AssertionError):
        assert len(_events(capture, 'artifact')) <= 1


def test_incomplete_outcomes_are_rejected(tmp_path):
    capture_parses, error = _api()
    with capture_parses(tmp_path) as capture:
        pyparse.parse_python(SOURCE, tmp_path / 'a.py')
    capture.events[:] = [event for event in capture.events if event.event != 'outcome']
    with pytest.raises(error, match='outcome'):
        capture.validate()
