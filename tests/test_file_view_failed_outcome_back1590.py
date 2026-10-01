"""A file whose own parser failed is a failed outcome in the file view too (BACK-1590).

XML, CSV and notebook analyzers return ``ResultBuilder.create_error`` when their parser
fails. The URI router turns a top-level ``error`` into stderr + exit 1 (BACK-1059), but the
file view rendered that result under a clean header and exited 0, and its text never showed
the error -- only "Parse recovered from syntax tree-sitter could not read", which is wrong
twice: XML isn't parsed by tree-sitter, and nothing was recovered. A recovered parse
(invalid JSON) is not a failure and still exits 0 with its note.
"""

import json

import pytest

from conftest import _run_reveal_direct

# BACK-1149: drives the CLI in process
pytestmark = pytest.mark.component

FAILED = [
    ('broken.xml', '<root><a>unclosed</root>\n', 'XML parse error'),
    ('broken.ipynb', '{"cells": [}', 'Expecting value'),
]


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    return tmp_path


@pytest.mark.parametrize('name,source,error', FAILED, ids=[f[0] for f in FAILED])
def test_failed_parse_reports_and_exits_1(cwd, name, source, error):
    (cwd / name).write_text(source, encoding='utf-8')
    run = _run_reveal_direct(name)
    assert run.returncode == 1
    assert f'Error ({name}): {error}' in run.stderr
    assert 'Parse recovered' not in run.stdout


@pytest.mark.parametrize('name,source,error', FAILED, ids=[f[0] for f in FAILED])
def test_failed_parse_json_envelope_carries_the_error(cwd, name, source, error):
    (cwd / name).write_text(source, encoding='utf-8')
    run = _run_reveal_direct(name, '--format', 'json')
    payload = json.loads(run.stdout)
    assert run.returncode == 1
    assert error in payload['error']
    assert 'parse_recovered' not in payload['meta']


def test_valid_xml_is_ok(cwd):
    (cwd / 'good.xml').write_text('<root><a>ok</a></root>\n', encoding='utf-8')
    run = _run_reveal_direct('good.xml')
    assert run.returncode == 0 and not run.stderr.strip()


def test_a_recovered_parse_is_not_a_failure(cwd):
    (cwd / 'broken.json').write_text('{"a": 1,,}\n', encoding='utf-8')
    run = _run_reveal_direct('broken.json')
    assert run.returncode == 0
    assert 'Parse recovered' in run.stdout
