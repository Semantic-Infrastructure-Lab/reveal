"""``api.query`` noun form: an unread or conflicting control raises ``UnreadControlError``, as the URI form does (BACK-2720).

The noun form runs the CLI's declared dispatch (BACK-2717). Its invalid-request answer for a control the selected
answer does not read (or one another control's value leaves unread, the requires ruling) carried only the message, so
the library caller got the base ``RequestValidationError`` where ``api.query('metrics://P?top=1')`` raises the
subclass with the same text. The answer now carries the request's own validation error beside ``exception`` (which MCP
reads as an internal failure), and MCP ``reveal_run`` still returns the message as a public tool error.
"""
import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError, UnreadControlError

CASES = [
    ('metrics', {'top': 1}, 'metrics://pkg?top=1'),
    ('imports', {'limit': 2}, 'imports://pkg?limit=2'),
    ('calls', {'callers': 'x', 'limit': 2}, 'calls://pkg?callers=x&limit=2'),
    ('metrics', {'view': 'hotspots', 'churn': 'off', 'since': '2020-01-01'},
     'metrics://pkg?view=hotspots&churn=off&since=2020-01-01'),
    ('imports', {'scope': 'path', 'root': '.'}, 'imports://pkg?scope=path&root=.'),
]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'app.py').write_text('import core\n\n\ndef x():\n    return core\n', encoding='utf-8')
    (tmp_path / 'pkg' / 'core.py').write_text('VALUE = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _raised(call):
    with pytest.raises(RequestValidationError) as raised:
        call()
    return raised.value


@pytest.mark.parametrize('noun,controls,uri', CASES)
def test_the_noun_form_raises_the_uri_forms_class_and_message(proj, noun, controls, uri):
    by_uri = _raised(lambda: api.query(uri))
    by_noun = _raised(lambda: api.query(noun, 'pkg', **controls))
    assert type(by_uri) is UnreadControlError
    assert type(by_noun) is UnreadControlError, (type(by_noun), str(by_noun))
    assert str(by_noun) == str(by_uri)


def test_another_invalid_request_keeps_its_own_class(proj):
    # Control: a value outside a control's choices is a RequestValidationError, not an unread control, on both forms.
    by_noun = _raised(lambda: api.query('imports', 'pkg', scope='both'))
    by_uri = _raised(lambda: api.query('imports://pkg?scope=both'))
    assert type(by_noun) is type(by_uri) is RequestValidationError


def test_the_cli_and_mcp_answers_are_unchanged(proj):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_run
    message = str(_raised(lambda: api.query('metrics', 'pkg', top=1)))
    cli = _run_reveal_direct('metrics', 'pkg', '--top', '1')
    assert cli.returncode == 2 and message in cli.stderr, cli.stderr
    result = reveal_run(['metrics', 'pkg', '--top', '1'])
    assert isinstance(result, _ToolFailure) and result.public, str(result)
    assert message in str(result) and 'Internal error' not in str(result)
