"""BACK-1591: element results and the directory view carry the Output Contract envelope.

`env://HOME`, every `python://<element>` and `reveal <dir> --format json` answered bare
data with no `type` or `contract_version`, while every structure result had both. The
contract harness only ran base URIs, so it never saw an element. The router now wraps
every element result (the adapter's own fields win; the type defaults to the adapter's
ELEMENT_RESULT_TYPE, else `<scheme>_element`), and the directory/file-list views build it.
"""

import json
import subprocess
import sys

import pytest


def _json(*argv):
    out = subprocess.run([sys.executable, '-m', 'reveal', *argv, '--format', 'json'],
                         capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize('argv, expected_type', [
    (('env://PATH',), 'env_variable'),
    (('python://version',), 'python_runtime'),
    (('python://packages',), 'python_packages'),
    (('python://doctor',), 'python_doctor'),
    (('reveal://adapters/reveal/adapter.py', 'get_element'), 'code_element'),
])
def test_element_results_carry_the_envelope(argv, expected_type):
    payload = _json(*argv)
    assert payload['type'] == expected_type
    assert payload['contract_version']


def test_directory_and_file_list_views_carry_the_envelope(tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    tree = _json(str(tmp_path))
    assert (tree['type'], bool(tree['contract_version'])) == ('directory_tree', True)
    files = _json(str(tmp_path), '--files')
    assert (files['type'], bool(files['contract_version'])) == ('file_list', True)


def test_router_keeps_an_adapters_own_type():
    """The envelope fills gaps; it never renames a type the adapter set."""
    from reveal.cli.routing.uri import _element_envelope

    class Plain:
        pass

    assert _element_envelope(Plain(), {'type': 'mine', 'x': 1}, 'demo', 'r')['type'] == 'mine'
    assert _element_envelope(Plain(), {'x': 1}, 'demo', 'r')['type'] == 'demo_element'
