"""A path read the file route refuses answers its document in JSON (D16, ruling S4 of BACK-2325, P1 21j step (c)).

``reveal missing.py --format json`` printed nothing on stdout: the refusal was a print and an exit. Each refusal site of
the file route is now an answer, so JSON carries the path read's invalid-request document (its ``error`` the message
the site prints, its facet the path read's: ``file_structure``, ``code_element``, ``directory_tree``), while stderr and
the exit code stay exactly what they were, in text and JSON alike.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n'

# argv, exit code, facet, the message (the site's first stderr line without its "Error: " label)
SITES = [
    (['missing.py'], 2, 'file_structure', 'missing.py not found'),
    (['README.rst'], 2, 'file_structure', "No analyzer found for file 'README.rst' (extension: .rst)"),
    (['d', 'foo'], 2, 'code_element', "d is a directory; it has no element 'foo'"),
    (['ok.py', 'foo', '--grep', 'x'], 2, 'code_element', "--grep answers for the whole of ok.py; it does not select 'foo'"),
    (['ok.py', '--hotspots'], 2, 'file_structure',
     "--hotspots is not a path option: the hotspot ranking is the metrics noun's view"),
    (['ok.py', '--related'], 1, 'file_structure', '--related only works with markdown files'),
    (['ok.py', '--section', 'X'], 1, 'file_structure', '--section only works with markdown files (.md, .markdown)'),
    (['nginx'], 2, 'file_structure', 'nginx is a URI noun: reveal nginx://.'),
]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    (tmp_path / 'README.rst').write_text('Title\n=====\n', encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('argv, code, facet, message', SITES, ids=[' '.join(s[0]) for s in SITES])
def test_a_refusal_answers_the_invalid_request_document_in_json(fx, argv, code, facet, message):
    text = _run_reveal_direct(*argv)
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == code
    assert run.stderr == text.stderr, 'stderr is the site\'s own text in JSON as in text'
    document = json.loads(run.stdout)
    assert document['type'] == facet and document['source'] == argv[0]
    assert document['error'] == message
    assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': message}]


@pytest.mark.parametrize('argv, code, facet, message', SITES, ids=[' '.join(s[0]) for s in SITES])
def test_sibling_the_text_refusal_is_unchanged(fx, argv, code, facet, message):
    run = _run_reveal_direct(*argv)
    assert run.returncode == code and run.stdout == ''
    first = run.stderr.splitlines()[0]
    assert first.endswith(message) and 'Error' in first


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows')
@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')
def test_an_unreadable_file_answers_the_failed_document_exit_3(fx):
    (fx / 'denied.py').write_text('x = 1\n', encoding='utf-8')
    os.chmod(fx / 'denied.py', 0)
    try:
        text = _run_reveal_direct('denied.py')
        run = _run_reveal_direct('denied.py', '--format', 'json')
    finally:
        os.chmod(fx / 'denied.py', 0o644)
    assert text.returncode == run.returncode == 3
    assert run.stderr == text.stderr == 'Error: cannot read denied.py: Permission denied\n'
    document = json.loads(run.stdout)
    assert document['type'] == 'file_structure'
    assert document['error'] == 'cannot read denied.py: Permission denied'
    assert document['meta']['errors'] == [{'code': 'analysis', 'message': document['error']}]


# B11: the navigation check of a path read (--head/--tail/--range, main._prepare) refuses before the file route runs.
# In JSON it answers the path read's invalid-request document (invalid_path_read, the main parser's usage-error
# answer: stderr labels the path, as `reveal ok.py --zz --format json` does); in text its two lines are unchanged.
_RANGE = ("Invalid range format 'zz': range must be START-END or START- (1-indexed, e.g. 10-20 or 300-), got 'zz'\n"
          'Expected format: START-END or START- for open-ended (e.g., 10-20, 300-, 1-indexed)')
NAVIGATION = [
    (['ok.py', '--range', 'zz'], 'file_structure', _RANGE),
    (['ok.py', '--head', '1', '--tail', '1'], 'file_structure', '--head, --tail, and --range are mutually exclusive'),
    (['ok.py', '--head', '-1'], 'file_structure', '--head must be 0 or more, got -1'),
    (['ok.py', 'foo', '--tail', '-2'], 'code_element', '--tail must be 0 or more, got -2'),
    (['d', '--head', '-1'], 'directory_tree', '--head must be 0 or more, got -1'),
]


@pytest.mark.parametrize('argv, facet, message', NAVIGATION, ids=[' '.join(s[0]) for s in NAVIGATION])
def test_a_navigation_refusal_answers_the_invalid_request_document_in_json(fx, argv, facet, message):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 2
    document = json.loads(run.stdout)
    assert document['type'] == facet and document['source'] == argv[0]
    assert document['error'] == message
    assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': message}]
    assert run.stderr == f'Error ({argv[0]}): {message}\n'


@pytest.mark.parametrize('argv, facet, message', NAVIGATION, ids=[' '.join(s[0]) for s in NAVIGATION])
def test_sibling_the_text_navigation_refusal_is_unchanged(fx, argv, facet, message):
    run = _run_reveal_direct(*argv)
    assert run.returncode == 2 and run.stdout == ''
    assert run.stderr == f'Error: {message}\n'
