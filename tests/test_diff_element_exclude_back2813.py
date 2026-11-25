"""``api.query('diff://A:B', NAME, exclude=P)`` applies ``exclude`` as ``reveal diff A B/NAME --exclude P`` does (BACK-2813).

The API's element form (a ``target:diff.element`` row: ``api.query(URI, ELEMENT)``) did not take the CLI's join of the
element onto the pair; it called the adapter's ``get_element`` itself, outside the declared route's ``exclusion_scope``,
decline seam and envelope. So ``exclude`` was accepted and never applied (h is only in the excluded skip.py, and the
API still answered it), and a file pair's element answer lacked the CLI's ``contract_version``, ``source`` and
``source_type``. ``api.query`` now joins a declared noun's legacy element as the CLI does and answers the joined URI
through the bound route (``reveal/api.py`` ``_declared_element_uri``). The siblings passed before and still pass.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import ElementNotFoundError

pytestmark = [pytest.mark.component]

@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """dA and dB: m.py's f differs in its body, skip.py's h in its signature; a.py and b.py: f differs in its body."""
    monkeypatch.chdir(tmp_path)
    for side, f_body, h_text in (('dA', '1', 'def h():\n    return 1\n'), ('dB', '2', 'def h(x, y):\n    return 3\n')):
        (tmp_path / side).mkdir()
        (tmp_path / side / 'm.py').write_text(f'def f():\n    return {f_body}\n', encoding='utf-8')
        (tmp_path / side / 'skip.py').write_text(h_text, encoding='utf-8')
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def f():\n    return 2\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('uri,keywords', [('diff://dA:dB', {'exclude': 'skip.py'}),
                                          ('diff://dA:dB?exclude=skip.py', {})], ids=['keyword', 'uri-query'])
def test_api_element_form_applies_exclude(dirs, uri, keywords):
    with pytest.raises(ElementNotFoundError, match="Element 'h' not found"):
        api.query(uri, 'h', **keywords)


def test_api_element_form_equals_the_cli_on_a_file_pair(dirs):
    run = _run_reveal_direct('diff://a.py:b.py', 'f', '--format', 'json')
    assert run.returncode == 0, run.stderr
    assert api.query('diff://a.py:b.py', 'f') == json.loads(run.stdout)


# --- siblings: green before and after the fix ------------------------------------------------------------------------------

def test_api_element_form_answers_without_exclude(dirs):
    doc = api.query('diff://dA:dB', 'h')
    assert (doc['type'], doc['name'], doc['change']) == ('diff_element', 'h', 'modified'), doc


def test_api_comparison_applies_exclude(dirs):
    """h (signature changed) is the pair's one modified function; excluding skip.py, its file, removes it."""
    names = [entry['name'] for entry in api.query('diff://dA:dB')['diff']['functions']]
    assert names == ['h']
    doc = api.query('diff://dA:dB', exclude='skip.py')
    assert doc['type'] == 'diff_comparison' and doc['summary']['functions']['modified'] == 0, doc
    assert doc['diff']['functions'] == [], doc['diff']
