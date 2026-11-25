"""api.element(PATH, NAME, **controls) takes the element read's controls, as api.analyze takes the path read's (BACK-2627
note #10, ruling K-A of BACK-2325): the flags of ``reveal PATH NAME`` with ``-`` as ``_``, answered through the CLI's own
element route, so ``api.element(F, 'f', view='boundary')`` is the document ``reveal F f --view boundary --format json``
prints (D21). An unknown keyword raises UnsupportedOverrideError, and so does ``element_type`` beside a control (ruling 7:
no element syntax of the CLI names a kind and a view); a legacy element keyword answers with its note, as its flag does;
an invalid request raises RequestValidationError with the CLI's exit-2 message.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import ElementNotFoundError, RequestValidationError, UnsupportedOverrideError

SOURCE = '''import logging

log = logging.getLogger(__name__)


class Store:
    def save(self, items, cfg):
        total = 0
        for item in items:
            if item.ok:
                log.info("saving %s", item)
                self.count = total
                total += helper(item)
            else:
                try:
                    cfg.pop("path")
                except KeyError:
                    return None
        mode = cfg.get("mode")
        return total


def helper(item):
    print(item)
    return 1
'''


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


VIEWS = [
    ({'view': 'boundary'}, ['--view', 'boundary']),
    ({'view': 'boundary', 'transitive': True, 'depth': 3}, ['--view', 'boundary', '--transitive', '--depth', '3']),
    ({'view': 'effects'}, ['--view', 'effects']),
    ({'view': 'effects', 'in_loops': True, 'nesting_depth': 1}, ['--view', 'effects', '--in-loops', '--nesting-depth', '1']),
    ({'view': 'effects', 'state': True}, ['--view', 'effects', '--state']),
    ({'view': 'flow', 'kind': ['if', 'loop']}, ['--view', 'flow', '--kind', 'if', '--kind', 'loop']),
    ({'view': 'exits', 'range': '9-14'}, ['--view', 'exits', '--range', '9-14']),
    ({'inputs': True}, ['--inputs']),
    ({'outputs': True}, ['--outputs']),
    ({'callsites': '10-14'}, ['--callsites', '10-14']),
    ({'varflow': 'total', 'cross_calls': True}, ['--varflow', 'total', '--cross-calls']),
    ({'keys': 'cfg'}, ['--keys', 'cfg']),
]


@pytest.mark.parametrize('controls, flags', VIEWS, ids=[' '.join(flags) for _, flags in VIEWS])
def test_an_element_view_is_the_clis_document(fx, controls, flags):
    assert api.element('m.py', 'Store.save', **controls) == _cli('m.py', 'Store.save', *flags)


@pytest.mark.parametrize('controls, flags', [({'scope': True}, ['--scope']), ({'around': 2}, ['--around', '2'])])
def test_a_line_view_is_the_clis_document(fx, controls, flags):
    assert api.element('m.py', ':12', **controls) == _cli('m.py', ':12', *flags)


def test_the_element_reads_slices_are_its_keywords_too(fx):
    assert api.element('m.py', 'Store.save', head=2) == _cli('m.py', 'Store.save', '--head', '2')


LEGACY = [({'boundary': True}, ['--boundary'], 'flag:--boundary'),
          ({'sideeffects': True}, ['--sideeffects'], 'flag:--sideeffects'),
          ({'flow': 'if,try'}, ['--flow=if,try'], 'flag:--flow'),
          ({'deps': True}, ['--deps'], 'flag:--deps')]


@pytest.mark.parametrize('controls, flags, field', LEGACY, ids=[field for *_, field in LEGACY])
def test_a_legacy_element_keyword_answers_with_its_note_as_its_flag_does(fx, controls, flags, field):
    answer = api.element('m.py', 'Store.save', **controls)
    assert answer == _cli('m.py', 'Store.save', *flags)
    assert field in [w.get('field') for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']


INVALID = [({'view': 'nope'}, ['--view', 'nope']),
           ({'view': 'boundary', 'head': 2}, ['--view', 'boundary', '--head', '2']),
           ({'view': 'flow', 'kind': 'if,try'}, ['--view', 'flow', '--kind', 'if,try']),
           ({'view': 'boundary', 'transitive': True, 'depth': 9}, ['--view', 'boundary', '--transitive', '--depth', '9']),
           ({'view': 'effects', 'in_loops': True, 'state': True}, ['--view', 'effects', '--in-loops', '--state'])]


@pytest.mark.parametrize('controls, flags', INVALID, ids=[' '.join(flags) for _, flags in INVALID])
def test_an_invalid_request_raises_the_clis_exit_2_message(fx, controls, flags):
    run = _run_reveal_direct('m.py', 'Store.save', *flags)
    assert run.returncode == 2 and run.stdout == ''
    with pytest.raises(RequestValidationError) as caught:
        api.element('m.py', 'Store.save', **controls)
    assert f'error: {caught.value}' == run.stderr.strip()


def test_a_view_of_an_element_that_is_not_there_raises_element_not_found(fx, capfd):
    run = _run_reveal_direct('m.py', 'Store.nope', '--view', 'boundary')
    assert run.returncode == 2
    capfd.readouterr()
    with pytest.raises(ElementNotFoundError) as caught:
        api.element('m.py', 'Store.nope', view='boundary')
    assert str(caught.value) == "could not find function or method 'Store.nope' in m.py"
    assert str(caught.value) in run.stderr and caught.value.element == 'Store.nope'
    assert capfd.readouterr() == ('', ''), 'the library API prints nothing; the exception carries the line'


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows')
@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')
def test_a_view_of_a_file_that_cannot_be_read_raises_its_os_error(fx, capfd):
    os.chmod(fx / 'm.py', 0)
    try:
        assert _run_reveal_direct('m.py', 'Store.save', '--view', 'boundary').returncode == 3
        capfd.readouterr()
        with pytest.raises(PermissionError):
            api.element('m.py', 'Store.save', view='boundary')
    finally:
        os.chmod(fx / 'm.py', 0o644)
    assert capfd.readouterr() == ('', '')


@pytest.mark.parametrize('keywords', [{'bogus': 1}, {'format': 'json'}, {'check': True}])
def test_an_unknown_keyword_or_an_output_option_is_unsupported(fx, keywords):
    with pytest.raises(UnsupportedOverrideError, match=repr(next(iter(keywords)))):
        api.element('m.py', 'Store.save', **keywords)


def test_element_type_beside_a_control_is_refused_naming_element_type(fx):
    with pytest.raises(UnsupportedOverrideError, match='element_type'):
        api.element('m.py', 'helper', element_type='function', view='boundary')


def test_sibling_the_bare_element_and_element_type_are_unchanged(fx):
    assert api.element('m.py', 'Store.save') == _cli('m.py', 'Store.save')
    typed = api.element('m.py', 'helper', element_type='function')
    assert typed['name'] == 'helper'
    assert 'python:element.element_type' in [w.get('field') for w in typed['meta']['warnings']]


def test_control_analyze_still_refuses_an_elements_controls(fx):
    with pytest.raises(UnsupportedOverrideError, match="'view'"):
        api.analyze('m.py', view='boundary')


@pytest.mark.parametrize('controls, flags', [({'scope': True}, ['--scope']), ({'around': 2}, ['--around', '2'])])
def test_a_range_given_to_a_line_view_raises_the_clis_refusal(fx, capfd, controls, flags):
    """``reveal F :A-B --scope`` exits 2 (BACK-2272); the library raises it as RequestValidationError with the CLI's text
    and prints nothing, instead of the SystemExit the CLI's exit was."""
    run = _run_reveal_direct('m.py', ':12-14', *flags)
    assert run.returncode == 2 and run.stdout == ''
    capfd.readouterr()
    with pytest.raises(RequestValidationError) as caught:
        api.element('m.py', ':12-14', **controls)
    assert f'error: {caught.value}' == run.stderr.strip()
    assert capfd.readouterr() == ('', '')
