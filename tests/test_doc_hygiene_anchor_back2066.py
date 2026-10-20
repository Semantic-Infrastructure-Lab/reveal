"""scripts/check_doc_hygiene.py must resolve anchors the way GitHub renders them.

GitHub turns each space of a heading into its own hyphen after dropping punctuation, so
"reveal calls — Cross-File Call Graph" is ``#reveal-calls--cross-file-call-graph``. The checker
collapsed whitespace runs into one hyphen and called that working link broken (BACK-2066's
calls guide link). Plain headings and a missing anchor are the controls.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def hygiene():
    spec = importlib.util.spec_from_file_location('check_doc_hygiene', ROOT / 'scripts' / 'check_doc_hygiene.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guide(tmp_path):
    path = tmp_path / 'guide.md'
    path.write_text('# Guide\n\n## reveal calls — Cross-File Call Graph\n\n## Plain Heading\n', encoding='utf-8')
    return path


def test_em_dash_heading_resolves_to_githubs_double_hyphen(hygiene, guide):
    assert hygiene._anchor_exists(guide, 'reveal-calls--cross-file-call-graph')


def test_plain_heading_still_resolves(hygiene, guide):
    assert hygiene._anchor_exists(guide, 'plain-heading')


def test_missing_anchor_is_still_broken(hygiene, guide):
    assert not hygiene._anchor_exists(guide, 'reveal-calls-cross-file-call-graph-typo')
