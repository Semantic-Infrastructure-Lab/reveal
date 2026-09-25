"""BACK-1425: --format and --also-json are honored or rejected, never silently
replaced by text.

`--format grep`/`typed` printed the text rendering and exited 0 for a
directory, calls://, imports://, git://, surface and most subcommands (only
overview said so), and `--also-json PATH` wrote nothing for the file view,
directory listings and subcommands other than check. Measured: grep output
byte-identical to text everywhere but the file view, ast://, env:// and
markdown://.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.cli.routing.formats import (
    DEFAULT_OUTPUT_FORMATS, declared_output_formats, reject_unhonored_also_json, require_supported_format,
)

# BACK-1149: exercises reveal.main's CLI entry point via conftest._run_reveal_direct
pytestmark = pytest.mark.cli

PKG = Path(__file__).resolve().parent.parent / 'reveal'
DISPLAY = PKG / 'display'
ELEMENT_PY = DISPLAY / 'element.py'


def test_declared_output_formats():
    class Declares:
        @staticmethod
        def get_help():
            return {'output_formats': ['text', 'json', 'grep']}

    class Silent:
        @staticmethod
        def get_help():
            return {}

    class Opaque:
        @staticmethod
        def get_help():
            return object()

    assert declared_output_formats(Declares) == ('text', 'json', 'grep')
    assert declared_output_formats(Silent) == DEFAULT_OUTPUT_FORMATS
    assert declared_output_formats(Opaque) is None  # nothing to enforce


def test_explicit_unsupported_format_exits_2(capsys, monkeypatch):
    monkeypatch.setattr('sys.argv', ['reveal', 'x', '--format', 'grep'])
    with pytest.raises(SystemExit) as exc:
        require_supported_format(SimpleNamespace(format='grep'), ('text', 'json'), 'surface://')
    assert exc.value.code == 2
    assert 'not supported by surface:// (supported: text, json)' in capsys.readouterr().err


def test_reveal_format_env_default_falls_back_with_a_note(capsys, monkeypatch):
    monkeypatch.setenv('REVEAL_FORMAT', 'grep')
    monkeypatch.setattr('sys.argv', ['reveal', 'surface://x'])
    args = SimpleNamespace(format='grep')
    require_supported_format(args, ('text', 'json'), 'surface://')
    assert args.format == 'text'
    assert 'REVEAL_FORMAT=grep is not supported by surface://' in capsys.readouterr().err


def test_grep_declarations_are_the_measured_ones():
    """A 'grep' claim must be re-measured before it is added: imports, stats,
    mysql and claude declared it and rendered text."""
    import reveal.adapters  # noqa: F401 -- registers every adapter
    claims = {
        scheme for scheme in list_supported_schemes()
        if 'grep' in (declared_output_formats(get_adapter_class(scheme)) or ())
    }
    assert claims - {'demo'} == {'ast', 'env', 'markdown'}  # demo: the template adapter, when a test registers it


@pytest.mark.parametrize('argv', [
    (DISPLAY, '--format', 'grep'),
    (DISPLAY, '--format', 'typed'),
    (f'calls://{DISPLAY}?target=listed_item_line', '--format', 'grep'),
    (f'imports://{DISPLAY}', '--format', 'grep'),
    (f'stats://{DISPLAY}', '--format', 'grep'),
    (f'ast://{DISPLAY}', '--format', 'typed'),
    ('help://quick', '--format', 'grep'),
    ('surface', DISPLAY, '--format', 'grep'),
    ('hotspots', DISPLAY, '--format', 'typed'),
    ('review', DISPLAY, '--format', 'grep'),
    ('health', DISPLAY, '--format', 'typed'),
], ids=lambda a: ' '.join(str(x).replace(str(PKG), 'reveal') for x in a))
def test_unrendered_format_is_rejected(argv):
    result = _run_reveal_direct(*argv)
    assert result.returncode == 2, result.stdout[:200]
    assert 'is not supported by' in result.stderr
    assert result.stdout == ''


@pytest.mark.parametrize('argv', [
    (ELEMENT_PY, '--format', 'grep'),
    (ELEMENT_PY, '--format', 'typed'),
    (f'ast://{DISPLAY}', '--format', 'grep'),
    ('check', ELEMENT_PY, '--format', 'grep'),
], ids=lambda a: ' '.join(str(x).replace(str(PKG), 'reveal') for x in a))
def test_rendered_format_still_renders(argv):
    result = _run_reveal_direct(*argv)
    assert 'is not supported by' not in result.stderr
    assert result.stdout


@pytest.mark.parametrize('argv, honored', [
    ((ELEMENT_PY,), False),
    ((DISPLAY,), False),
    ((ELEMENT_PY, '--grep', 'def'), False),
    (('overview', DISPLAY), False),
    ((f'ast://{DISPLAY}',), True),
    ((DISPLAY, '--name', 'listed_item_line'), True),  # routes to ast://
    (('check', ELEMENT_PY), True),
], ids=lambda a: ' '.join(str(x).replace(str(PKG), 'reveal') for x in a) if isinstance(a, tuple) else str(a))
def test_also_json_is_written_or_rejected(tmp_path, argv, honored):
    out = tmp_path / 'also.json'
    result = _run_reveal_direct(*argv, '--also-json', out)
    if honored:
        assert out.exists()
        assert '--also-json is not supported' not in result.stderr
    else:
        assert result.returncode == 2
        assert '--also-json is not supported by' in result.stderr
        assert not out.exists()


def test_also_json_with_json_format_is_redundant_not_rejected():
    args = SimpleNamespace(also_json='x.json', format='json')
    reject_unhonored_also_json(args, 'the file view')  # no exit
