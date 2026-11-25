"""``api.query(URI, ELEMENT)`` on a declared noun answers what ``reveal URI ELEMENT --format json`` answers (BACK-2813).

A positional element that a noun still answers until the cut (a ``target:NOUN.element`` row) is joined onto the URI by
the CLI's declared route (``legacy_element_resource``: ``help:// quick`` is ``help://quick``, ``diff://A:B NAME`` is
``diff://A:B/NAME``) and answered there, with its walk exclusion, decline, failure mapping and envelope. The API called
the adapter's ``get_element`` itself instead: a second computation of the answer (D21), which lacked the CLI's
``source``/``source_type`` (and diff's ``contract_version``), raised a plain ValueError where the CLI exits 2 on an
element miss, and answered a diff pair the CLI refuses (a file left with a directory right: the child is read as a
file, ruling A2 on BACK-2812).

The diff cases (exclude, the env decline, the file and directory pairs) are in the BACK-2812/2813/2817 diff test
files. The control: reveal:// is not a declared noun, its CLI reads the element through get_element, and both
transports keep answering it that way.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.diff.resolution import DiffTargetNotFoundError
from reveal.errors import ElementNotFoundError

pytestmark = [pytest.mark.component]


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    """a.py and b.py (files whose f differs) and dB/skip.py (a directory holding h)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def f():\n    return 2\n', encoding='utf-8')
    (tmp_path / 'dB').mkdir()
    (tmp_path / 'dB' / 'skip.py').write_text('def h(x, y):\n    return 3\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('topic', ['quick', 'ast'])
def test_help_element_equals_the_cli(topic):
    code, cli = _cli('help://', topic)
    assert code == 0, cli
    assert api.query('help://', topic) == cli


def test_help_element_miss_raises_the_clis_invalid_request():
    code, cli = _cli('help://', 'no-such-topic')
    assert code == 2 and cli['error'] == "Element 'no-such-topic' not found", cli
    with pytest.raises(ElementNotFoundError, match="^Element 'no-such-topic' not found$"):
        api.query('help://', 'no-such-topic')


def test_diff_element_beside_a_uri_query_answers_and_notes_in_the_clis_order(pair):
    """The element's row, then the request note, as the CLI says them; the request note's replacement is each
    transport's own spelling (``reveal ...`` / ``api.query(...)``), so the notes compare by field."""
    code, cli = _cli('diff://a.py:b.py?exclude=x', 'f')
    assert code == 0, cli
    answer = api.query('diff://a.py:b.py?exclude=x', 'f')
    fields = [[warning.get('field') for warning in doc['meta']['warnings']] for doc in (cli, answer)]
    assert fields[0] == fields[1] == ['target:diff.element', 'request:diff'], fields
    assert {k: v for k, v in answer.items() if k != 'meta'} == {k: v for k, v in cli.items() if k != 'meta'}


def test_diff_file_left_directory_right_element_is_refused_alike(pair):
    """The accepted cost of ruling A2: with a file left, ``dB/h`` names a file, which is not there (CLI exit 2)."""
    code, cli = _cli('diff://a.py:dB', 'h')
    assert code == 2 and cli['error'] == 'File not found: dB/h', cli
    with pytest.raises(DiffTargetNotFoundError, match='^File not found: dB/h$'):
        api.query('diff://a.py:dB', 'h')


@pytest.mark.parametrize('scheme,uri,element,joined', [
    ('help', 'help://', 'quick', 'help://quick'),
    ('diff', 'diff://dA:dB', 'h', 'diff://dA:dB/h'),
    ('diff', 'diff://dA/:dB/', 'h', 'diff://dA/:dB/h'),
    ('diff', 'diff://dA:dB?exclude=skip.py', 'h', 'diff://dA:dB/h?exclude=skip.py'),
    ('diff', 'diff://env://:env://', 'PATH', 'diff://env://:env:///PATH'),
    ('reveal', 'reveal://adapters/env.py', 'EnvAdapter', None),
])
def test_the_join_is_the_clis(scheme, uri, element, joined):
    """The API's join is the CLI's (``legacy_element_resource``) on the path, the query kept; none off the declared
    route (reveal://)."""
    from reveal.api import _declared_element_uri
    assert _declared_element_uri(scheme, uri, element) == joined


# --- control: green before and after ---------------------------------------------------------------------------------

def test_reveal_element_still_answers_through_get_element_alike():
    code, cli = _cli('reveal://adapters/env.py', 'EnvAdapter')
    assert code == 0 and cli['type'] == 'code_element', cli
    assert api.query('reveal://adapters/env.py', 'EnvAdapter') == cli
