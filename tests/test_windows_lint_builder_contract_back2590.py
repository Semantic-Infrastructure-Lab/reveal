"""The same native assertion can be valid before a builder normalizes Paths."""
import pytest

from test_windows_path_rule_back1707 import checkout as checkout
from test_windows_path_rule_back1707 import _lines, _run
from test_windows_lint_back2590 import SOURCE, ERROR, UNITTEST, SINK

pytestmark = pytest.mark.component


@pytest.mark.parametrize('source,owner,line', [
    (SOURCE, 'class ResultBuilder:\n    def create(source):\n        return {"source": VALUE}\n', 4),
    (ERROR, 'class ResultBuilder:\n    def create_error(source):\n        return {"source": VALUE}\n', 4),
    (UNITTEST, 'def add_cli_contract_fields(source):\n    return {"source": VALUE}\n', 6),
], ids=['create', 'create-error', 'cli-fields'])
@pytest.mark.parametrize('normalized', [False, True], ids=['native-producer', 'normalized-producer'])
def test_assertion_is_checked_against_the_target_builder(checkout, tmp_path, source, owner, line, normalized):
    builder = tmp_path / 'reveal' / 'utils' / 'results.py'
    builder.parent.mkdir()
    builder.write_text(owner.replace('VALUE', 'source.as_posix()' if normalized else 'str(source)'), encoding='utf-8')
    checkout('test_envelope.py', source)
    rule, found = _run()
    assert _lines(found) == ([('tests/test_envelope.py', line)] if normalized else [])
    assert rule.outcomes == []


def test_native_builder_does_not_exempt_stderr_path_assertions(checkout, tmp_path):
    builder = tmp_path / 'reveal' / 'utils' / 'results.py'
    builder.parent.mkdir()
    builder.write_text('class ResultBuilder:\n    def create(source):\n        return {"source": str(source)}\n', encoding='utf-8')
    checkout('test_envelope.py', SOURCE)
    checkout('test_sink.py', SINK)
    assert _lines(_run()[1]) == [('tests/test_sink.py', 4)]
