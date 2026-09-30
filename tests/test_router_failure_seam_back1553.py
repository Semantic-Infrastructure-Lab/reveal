"""BACK-1553: one failure path in the URI router.

An adapter can fail two ways: return an error result, or raise. A returned error went
through ``_emit_result`` (one stderr line, the JSON envelope, --also-json, exit 1). A raise
was caught at each of six call sites, which printed their own error line (three spellings),
hand-built another envelope (contract_version 1.0, source_type always 'file') and exited
without writing --also-json; text printed the error twice. An element lookup that found
nothing printed on stderr only, so --format json got 0 bytes.

Now every call into an adapter goes through ``_call_adapter``, which turns a raise into a
result that leaves through ``_emit_result``. These tests drive each exit and check that it
reads the same; ``test_every_adapter_call_goes_through_the_seam`` keeps it that way.
"""

import ast
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from reveal.cli.defaults import _default_args
from reveal.cli.routing import uri as router
from reveal.errors import NotApplicableError, RevealError
from reveal.reveal_types import CONTRACT_VERSION

pytestmark = pytest.mark.component


class _Renderer:
    """Stands in for an adapter's renderer: a router-built failure must never reach it."""

    @staticmethod
    def render_structure(result, format='text', **kwargs):
        print('RENDERED')

    @staticmethod
    def render_element(result, format='text', **kwargs):
        print('RENDERED')


def _adapter(fail_at=None, exc=None, **attrs):
    """An adapter class that raises `exc` from the method named `fail_at`."""
    exc = exc or ValueError('boom at ' + str(fail_at))

    def raise_or(value):
        def method(self, *args, **kwargs):
            if fail_at == name_of[method]:
                raise exc
            return value(self, *args, **kwargs) if callable(value) else value
        return method

    name_of = {}
    methods = {
        'get_structure': raise_or({'type': 'fake', 'source': 'x'}),
        'get_element': raise_or(lambda self, name, **kw: None if fail_at == 'none' else {'name': name}),
        'post_process': raise_or(lambda self, result, args: result),
        'check': raise_or({'exit_code': 0}),
        'reconfigure_base_path': raise_or(None),
    }
    for name, method in methods.items():
        name_of[method] = name

    def from_uri(cls, scheme, resource, element):
        if fail_at == 'construct':
            raise exc
        return cls()

    namespace = {'from_uri': classmethod(from_uri), 'list_elements': lambda self: ['alpha', 'beta'],
                 **methods, **attrs}
    return type('FakeAdapter', (), namespace)


def _run(adapter_class, *, resource='x', element=None, fmt='text', tmp_path=None, **flags):
    """(exit code, stdout, stderr, --also-json payload or None)."""
    also = tmp_path / 'also.json' if tmp_path is not None and fmt != 'json' else None
    args = _default_args(format=fmt, also_json=str(also) if also else None, **flags)
    out, err, code = io.StringIO(), io.StringIO(), 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            router.generic_adapter_handler(adapter_class, _Renderer, 'fake', resource, element, args)
        except SystemExit as e:
            code = e.code
    also_payload = json.loads(also.read_text(encoding='utf-8')) if also is not None and also.exists() else None
    return code, out.getvalue(), err.getvalue(), also_payload


# Each way a query can fail in the router: (id, adapter class, run kwargs, meta.errors code).
EXITS = [
    ('construct', _adapter('construct'), {}, 'adapter_error'),
    ('base_path', _adapter('reconfigure_base_path'), {'base_path': '/tmp'}, 'adapter_error'),
    ('check', _adapter('check'), {'check': True}, 'adapter_error'),
    ('get_structure', _adapter('get_structure'), {}, 'adapter_error'),
    ('post_process', _adapter('post_process'), {}, 'adapter_error'),
    ('get_element', _adapter('get_element'), {'element': 'alpha'}, 'adapter_error'),
    ('element_none', _adapter('none'), {'element': 'gamma'}, 'element_not_found'),
    ('missing_path', _adapter(RESOURCE_IS_PATH=True), {'resource': '/no/such/zz_1553'}, 'adapter_error'),
]


@pytest.mark.parametrize('adapter_class,kwargs,code', [e[1:] for e in EXITS], ids=[e[0] for e in EXITS])
def test_text_prints_the_error_once_on_stderr(adapter_class, kwargs, code, tmp_path):
    exit_code, out, err, also = _run(adapter_class, tmp_path=tmp_path, **kwargs)
    assert exit_code == 1
    assert out == '', 'a failure prints nothing on stdout in text'
    assert err.startswith('Error (fake://): ')
    assert err.count('Error') == 1, err
    assert also is not None and also['error'], '--also-json gets the failure envelope'


@pytest.mark.parametrize('adapter_class,kwargs,code', [e[1:] for e in EXITS], ids=[e[0] for e in EXITS])
def test_json_gets_one_current_envelope(adapter_class, kwargs, code):
    exit_code, out, err, _ = _run(adapter_class, fmt='json', **kwargs)
    assert exit_code == 1
    envelope = json.loads(out)
    assert envelope['contract_version'] == CONTRACT_VERSION
    assert envelope['type'] == 'fake'
    assert envelope['error']
    assert envelope['meta']['errors'] == [{'code': code, 'message': envelope['error']}]
    assert err.count(envelope['error'].splitlines()[0]) == 1


def test_element_not_found_lists_the_elements():
    _, out, _, _ = _run(_adapter('none'), fmt='json', element='gamma')
    envelope = json.loads(out)
    assert envelope['error'] == "Element 'gamma' not found"
    assert envelope['available_elements'] == ['alpha', 'beta']
    _, _, err, _ = _run(_adapter('none'), element='gamma')
    assert err == "Error (fake://): Element 'gamma' not found\nAvailable elements: alpha, beta\n"


def test_not_applicable_is_an_answer_with_its_envelope(tmp_path):
    declines = _adapter('get_structure', NotApplicableError('Not a repo', reason='Not a repo'))
    code, out, err, also = _run(declines, tmp_path=tmp_path)
    assert (code, out, err) == (0, '(fake://) not applicable: Not a repo\n', '')
    assert also['applicable'] is False and also['reason'] == 'Not a repo'
    code, out, _, _ = _run(declines, fmt='json')
    envelope = json.loads(out)
    assert code == 0 and envelope['contract_version'] == CONTRACT_VERSION
    assert envelope['meta']['warnings'] == [{'code': 'not_applicable', 'message': 'Not a repo'}]


def test_a_raise_with_no_message_still_fails():
    """An empty `error` would read as success (outcome_of), so the type names it."""
    code, out, _, _ = _run(_adapter('get_structure', KeyError()), fmt='json')
    assert code == 1 and json.loads(out)['error'] == 'KeyError'


def test_the_messages_own_error_prefix_is_not_repeated():
    code, _, err, _ = _run(_adapter('get_structure', RevealError('no index')))
    assert code == 1 and err == 'Error (fake://): no index\n'


def test_source_type_claims_only_what_exists(tmp_path):
    (tmp_path / 'f.py').write_text('', encoding='utf-8')
    assert router._source_type_of(str(tmp_path)) == 'directory'
    assert router._source_type_of(str(tmp_path / 'f.py') + '?q=1') == 'file'
    assert router._source_type_of(str(tmp_path / 'nope')) == 'unknown'
    assert router._source_type_of('.@nosuchref') == 'unknown'
    assert router._source_type_of('') == 'unknown'


# The adapter methods the router calls. A call to one outside _call_adapter is a raise that
# skips the one failure path.
_ADAPTER_CALLS = {'from_uri', '_default_from_uri', 'reconfigure_base_path', 'check',
                  'get_element', 'get_structure', 'post_process'}


def test_every_adapter_call_goes_through_the_seam():
    tree = ast.parse(Path(router.__file__).read_text(encoding='utf-8'))
    guarded = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == '_call_adapter' and isinstance(node.args[0], ast.Lambda)):
            guarded.update(id(n) for n in ast.walk(node.args[0].body))

    def name(call):
        return call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, 'id', None)

    stray = [f'line {n.lineno}: {name(n)}()' for n in ast.walk(tree)
             if isinstance(n, ast.Call) and name(n) in _ADAPTER_CALLS and id(n) not in guarded]
    assert not stray, f'adapter calls outside _call_adapter: {stray}'

    # A broad handler that doesn't re-raise ends the query: only the seam may do that.
    handlers = [f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                for h in ast.walk(f) if isinstance(h, ast.ExceptHandler)
                and isinstance(h.type, ast.Name) and h.type.id == 'Exception'
                and not any(isinstance(n, ast.Raise) for n in ast.walk(h))]
    assert handlers == ['_call_adapter'], f'`except Exception` outside the seam: {handlers}'


def test_no_renderer_reports_errors_itself():
    """The router reports every failure, so a renderer's render_error would never be called.
    Its one caller was the missing-dependency branch; 36 copies printed their own spelling
    of the error, and git's printed its pygit2 hint twice (the hint is in the ImportError)."""
    from conftest import production_schemes
    from reveal import adapters  # noqa: F401  (registers every adapter)
    from reveal.adapters.base import get_renderer_class

    stale = [s for s in production_schemes() if hasattr(get_renderer_class(s), 'render_error')]
    assert not stale, f'renderers defining render_error, which nothing calls: {stale}'
