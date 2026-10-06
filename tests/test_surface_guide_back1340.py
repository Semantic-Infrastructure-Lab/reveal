"""BACK-1340: SURFACE_ADAPTER_GUIDE.md says what surface:// is and is not, and carries one
semantics row per category that matches the code.

The table is pinned to the live adapter: one row per `surface_matrix.CATEGORIES` entry in
order, the 'No detector for' column equals the coverage matrix, and the entry `type` each
row names is the `type` a real scan emits.
"""

import re
from pathlib import Path

import pytest

from reveal.adapters.ast.surface_matrix import CATEGORIES, SCANNER_MODULES, coverage_matrix
from reveal.adapters.surface import _scan_surface

pytestmark = pytest.mark.component

GUIDE = (Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'adapters'
         / 'SURFACE_ADAPTER_GUIDE.md')

FIXTURE = '''import argparse
import os
import subprocess
import sqlite3
import requests
import boto3
from flask import Flask
from mcp.server import MCPServer

app = Flask(__name__)
mcp = MCPServer("x")


@app.route("/items", methods=["GET"])
def items():
    return os.environ.get("HOME")


@mcp.tool()
def lookup(q):
    return q


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flag")
    subprocess.run(["ls"])
    with open("out.txt", "w") as fh:
        fh.write("x")
'''


@pytest.fixture(scope='module')
def guide():
    return GUIDE.read_text(encoding='utf-8')


def _section(guide, heading):
    match = re.search(rf'^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', guide, flags=re.MULTILINE | re.DOTALL)
    assert match, f'missing section: {heading}'
    return match.group(1)


def _rows(guide):
    """{category: [cell, ...]} from the 'Categories at a glance' table."""
    rows = {}
    for line in _section(guide, 'Categories at a glance').splitlines():
        if line.startswith('|') and not line.startswith('|--') and not line.startswith('| Category'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows[cells[0].strip('`')] = cells[1:]
    return rows


def test_what_it_is_and_is_not_section_exists(guide):
    text = _section(guide, 'What surface:// is and is not')
    assert 'boundary' in text.lower()
    for neighbour in ('architecture://', 'imports://', 'calls://'):
        assert neighbour in text, f'should point to {neighbour} for what surface:// does not answer'


def test_one_row_per_category_in_code_order(guide):
    assert list(_rows(guide)) == list(CATEGORIES)


def test_no_detector_column_equals_the_coverage_matrix(guide):
    missing = coverage_matrix(sorted(SCANNER_MODULES))['not_implemented']
    for category, cells in _rows(guide).items():
        documented = {name.strip('` ') for name in cells[-1].split(',') if name.strip('` ') not in ('', 'none')}
        assert documented == set(missing.get(category, [])), category


def test_named_entry_type_is_what_a_real_scan_emits(guide, tmp_path):
    (tmp_path / 'app.py').write_text(FIXTURE, encoding='utf-8')
    surfaces = _scan_surface(tmp_path)['surfaces']
    rows = _rows(guide)
    for category in CATEGORIES:
        emitted = {entry['type'] for entry in surfaces.get(category, [])}
        assert emitted, f'fixture produced no {category} entry'
        for entry_type in emitted:
            assert f'`{entry_type}`' in rows[category][1], f'{category}: type `{entry_type}` not in its row'


def test_negative_control_fixture_scan_is_not_vacuous(tmp_path):
    (tmp_path / 'app.py').write_text(FIXTURE, encoding='utf-8')
    surfaces = _scan_surface(tmp_path)['surfaces']
    assert all(surfaces.get(category) for category in CATEGORIES)
