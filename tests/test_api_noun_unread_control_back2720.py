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


# --- the shared owner (unit): an invalid-request answer keeps the request's validation error apart from exception ---

def test_an_invalid_answer_keeps_a_validation_error_beside_exception():
    from argparse import Namespace
    from reveal.cli.routing.declared import _invalid_answer, declared_adapter_class
    adapter = declared_adapter_class('metrics')
    unread = UnreadControlError("control 'top' is not read by this answer")
    kept = _invalid_answer(adapter, 'metrics', '.', str(unread), Namespace(format='json'), error=unread)
    assert type(kept.request_error) is UnreadControlError and str(kept.request_error) == str(unread)
    assert kept.exception is None   # MCP's internal-failure slot stays empty
    assert kept.public_diagnostic == str(unread)
    other = _invalid_answer(adapter, 'metrics', '.', 'Path not found: x', Namespace(format='json'),
                            error=FileNotFoundError('x'))
    assert other.request_error is None and other.exception is None
    assert _invalid_answer(adapter, 'metrics', '.', 'm', Namespace(format='json')).request_error is None


def test_the_kept_error_holds_no_frames_so_the_answer_is_freed():
    """The kept error is detached: no traceback, context or cause, whose frames could hold the Answer in a reference
    cycle past its request (BACK-2674; tests/test_answer_lifetime_back2674.py). Its class, message and attributes stay."""
    from argparse import Namespace
    from reveal.cli.routing.declared import _invalid_answer, declared_adapter_class
    try:
        try:
            raise KeyError('inner')
        except KeyError:
            raise UnreadControlError("control 'top' is not read by this answer")
    except UnreadControlError as exc:
        caught = exc
        answer = _invalid_answer(declared_adapter_class('metrics'), 'metrics', '.', str(exc), Namespace(format='json'),
                                 error=exc)
    kept = answer.request_error
    assert type(kept) is UnreadControlError and str(kept) == str(caught)
    assert kept.__traceback__ is None and kept.__context__ is None and kept.__cause__ is None
