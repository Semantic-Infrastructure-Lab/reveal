"""A path read's invalid request exits 2 on the CLI, as D6 says and as the Python API already raises it (BACK-2765).

``--related``/``--related-all`` or ``--section`` on a file that is not Markdown, and an adapter's flag on a plain file
(``--summary`` is ssl://'s, ``--check-acl`` nginx's), were refused with exit 1, the findings code, while their answers
already carried invalid-request facts (``api.analyze`` raises ``RequestValidationError``). They exit 2 now, stderr and
the JSON document unchanged.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n'
DOC_MD = '# Intro\n\nSee [b](b.md).\n'

# argv, the message (the site's first stderr line without its label)
REFUSALS = [
    (['ok.py', '--related'], '--related only works with markdown files'),
    (['ok.py', '--related-all'], '--related-all only works with markdown files'),
    (['ok.py', '--section', 'X'], '--section only works with markdown files (.md, .markdown)'),
    (['ok.py', '--summary'], '--summary only works with the ssl:// adapter'),
    (['ok.py', '--check-acl'], '--check-acl only works with nginx config files'),
]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    (tmp_path / 'doc.md').write_text(DOC_MD, encoding='utf-8')
    (tmp_path / 'b.md').write_text('# B\n', encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('argv, message', REFUSALS, ids=[' '.join(r[0]) for r in REFUSALS])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_a_flag_for_another_kind_of_file_exits_2(fx, argv, message, fmt):
    run = _run_reveal_direct(*argv, '--format', fmt)
    assert run.returncode == 2, run.stderr
    assert message in run.stderr.splitlines()[0]
    if fmt == 'json':
        document = json.loads(run.stdout)
        assert document['meta']['errors'] == [{'code': 'invalid_request', 'message': message}]


# The ones api.analyze takes as keywords (--section is an element read's flag; --check-acl is not a path read's keyword)
API_REFUSALS = [r for r in REFUSALS if r[0][1] in ('--related', '--related-all', '--summary')]


@pytest.mark.parametrize('argv, message', API_REFUSALS, ids=[' '.join(r[0]) for r in API_REFUSALS])
def test_control_the_api_already_raised_the_refusal(fx, argv, message):
    with pytest.raises(RequestValidationError, match=message):
        api.analyze(argv[0], **{argv[1].lstrip('-').replace('-', '_'): True})


def test_sibling_the_same_flags_where_they_apply(fx):
    assert _run_reveal_direct('doc.md', '--related', '--format', 'json').returncode == 0
    assert _run_reveal_direct('doc.md', '--section', 'Intro').returncode == 0
    assert api.analyze('doc.md', related=True)['type'] == 'markdown'


def test_sibling_an_invalid_request_that_already_exited_2(fx):
    assert _run_reveal_direct('ok.py', '--hotspots').returncode == 2
    assert _run_reveal_direct('missing.py').returncode == 2
