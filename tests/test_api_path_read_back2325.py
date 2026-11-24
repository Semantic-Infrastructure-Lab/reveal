"""reveal.api.analyze(PATH) answers the JSON document ``reveal PATH --format json`` prints and raises as api.query's noun
form does (D21, BACK-2325): through the CLI's own path-read route, a file and a directory alike.

Each case compares the API with the CLI's JSON for the same request (both given the same spelling of the path: answers
echo it, BACK-1366), or pins the class the API raises where the CLI exits 2 or 3.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import (AnalysisFailedError, ConfigValidationError, PathNotFoundError, RequestValidationError,
                           UnsupportedOverrideError)

POSIX_ONLY = pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows')
NOT_ROOT = pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')

OK_PY = ('import os\n\n\ndef foo():\n    return 1\n\n\ndef bar():\n    return 2\n\n\ndef baz():\n    return 3\n\n\n'
         'class K:\n    def m(self):\n        return os.sep\n')


@pytest.fixture
def fx(tmp_path, monkeypatch):
    """A1's fixture set, in the current directory."""
    files = {'ok.py': OK_PY, 'syn.py': 'def ok():\n    pass\n\ndef bad(:\n    pass\n', 'bad.xml': '<a><b></a>\n',
             'bad.ipynb': 'nope', 'shape.ipynb': '[1, 2, 3]\n', 'bad.docx': 'notzip', 'README.rst': 'Title\n=====\n\ntext\n',
             'd/a.py': OK_PY, 'd/sub/b.py': 'x = 1\n'}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr


# --- R1, R2: the answer is the CLI's document, for a file and a directory ---------------------------------------------

def test_r1_a_file_answers_the_clis_document(fx):
    code, expected, stderr = _cli('ok.py')
    assert code == 0, stderr
    assert expected['type'] == 'python' and expected['structure']['functions']
    assert api.analyze('ok.py') == expected


def test_r1_a_recovered_parse_answers_the_clis_document(fx):
    code, expected, _ = _cli('syn.py')
    assert code == 0 and expected['meta'].get('parse_recovered') is True
    assert api.analyze('syn.py') == expected


def test_r2_a_directory_answers_the_clis_tree_document(fx):
    code, expected, stderr = _cli('d')
    assert code == 0, stderr
    assert expected['type'] == 'directory_tree'
    assert api.analyze('d') == expected


# --- R3, R4: a failed structure raises as the noun form does -----------------------------------------------------------

@pytest.mark.parametrize('name, cause', [('bad.xml', 'XML parse error'), ('bad.ipynb', 'notebook')])
def test_r3_a_parse_failure_raises_analysis_failed_carrying_the_clis_document(fx, name, cause):
    code, expected, _ = _cli(name)
    assert code == 3 and expected['error']
    with pytest.raises(AnalysisFailedError) as caught:
        api.analyze(name)
    assert caught.value.result == expected
    assert cause.lower() in str(caught.value).lower()


@pytest.mark.parametrize('name', ['shape.ipynb', 'bad.docx'])
def test_r4_a_wrong_document_shape_raises_the_invalid_request_with_the_clis_error(fx, name):
    code, expected, _ = _cli(name)
    assert code == 2 and expected['error']
    with pytest.raises(RequestValidationError) as caught:
        api.analyze(name)
    error = expected['error']
    assert str(caught.value) == (error if isinstance(error, str) else error['message'])


# --- R5, R6: invalid requests raise the request's own class -----------------------------------------------------------

def test_r5_a_missing_path_is_an_invalid_request_and_a_file_not_found_error(fx):
    assert _cli('missing.py')[0] == 2
    with pytest.raises(PathNotFoundError) as caught:
        api.analyze('missing.py')
    assert isinstance(caught.value, RequestValidationError) and isinstance(caught.value, FileNotFoundError)
    assert 'missing.py not found' in str(caught.value)


def test_r5_sibling_a_missing_path_is_still_a_file_not_found_error(fx):
    with pytest.raises(FileNotFoundError):
        api.analyze('missing.py')


def test_r6_a_file_no_analyzer_reads_is_an_invalid_request_with_the_clis_message(fx):
    code, _, stderr = _cli('README.rst')
    assert code == 2
    with pytest.raises(RequestValidationError) as caught:
        api.analyze('README.rst')
    assert str(caught.value).splitlines()[0] in stderr


# --- R7: the cuts are the CLI's flags, as keywords ---------------------------------------------------------------------

def test_r7_head_is_the_clis_head(fx):
    code, expected, _ = _cli('ok.py', '--head', '2')
    assert code == 0 and len(expected['structure']['functions']) == 2
    assert any(w.get('type') == 'truncated' for w in expected['meta']['warnings'])
    assert api.analyze('ok.py', head=2) == expected


def test_r7_a_range_tuple_is_the_clis_range(fx):
    code, expected, _ = _cli('ok.py', '--range', '2-3')
    assert code == 0
    assert api.analyze('ok.py', range=(2, 3)) == expected
    assert api.analyze('ok.py', range='2-3') == expected


def test_r7_outline_and_depth_are_the_clis_flags(fx):
    assert api.analyze('ok.py', outline=True) == _cli('ok.py', '--outline')[1]
    assert api.analyze('d', depth=1) == _cli('d', '--depth', '1')[1]


# --- R8: the configuration the path read selects -----------------------------------------------------------------------

def test_r8_a_selected_configuration_that_does_not_exist_raises(fx, monkeypatch):
    monkeypatch.setenv('REVEAL_CONFIG', str(fx / 'no-such-dir' / 'config.yaml'))
    assert _cli('ok.py')[0] == 2
    with pytest.raises(ConfigValidationError):
        api.analyze('ok.py')


# --- R9: keywords are the path read's flags ----------------------------------------------------------------------------

def test_r9_an_unknown_keyword_is_an_unsupported_control(fx):
    with pytest.raises(UnsupportedOverrideError) as caught:
        api.analyze('ok.py', bogus=1)
    assert isinstance(caught.value, TypeError) and 'bogus' in str(caught.value)


@pytest.mark.parametrize('old, new', [('extract_links', 'links'), ('extract_code', 'code'), ('inline_code', 'inline'),
                                      ('extract_frontmatter', 'frontmatter'), ('extract_related', 'related')])
def test_r9_an_old_analyzer_word_is_refused_naming_the_flag_keyword(fx, old, new):
    with pytest.raises(UnsupportedOverrideError) as caught:
        api.analyze('ok.py', **{old: True})
    assert f'{new}=' in str(caught.value)


@pytest.mark.parametrize('keyword', ['format', 'output', 'stdin', 'meta', 'check', 'view', 'section', 'help'])
def test_r9_output_options_modes_and_element_reads_are_not_keywords(fx, keyword):
    with pytest.raises(UnsupportedOverrideError):
        api.analyze('ok.py', **{keyword: 'json' if keyword in ('format', 'view', 'section') else True})


# --- R10: negative control, a file that cannot be read raises its cause, before and after -----------------------------

@POSIX_ONLY
@NOT_ROOT
def test_r10_an_unreadable_file_raises_its_os_error(fx):
    (fx / 'denied.py').write_text('x = 1\n', encoding='utf-8')
    os.chmod(fx / 'denied.py', 0)
    try:
        assert _cli('denied.py')[0] == 3
        with pytest.raises(PermissionError):
            api.analyze('denied.py')
    finally:
        os.chmod(fx / 'denied.py', 0o644)


# --- siblings that pass before and after: the CLI's own answers ---------------------------------------------------------

@pytest.mark.parametrize('argv, code', [(['ok.py'], 0), (['d'], 0), (['bad.xml'], 3), (['shape.ipynb'], 2),
                                        (['README.rst'], 2), (['missing.py'], 2)])
def test_the_clis_exit_codes_these_compare_with(fx, argv, code):
    assert _run_reveal_direct(*argv).returncode == code
