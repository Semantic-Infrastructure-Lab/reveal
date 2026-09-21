"""BACK-1278 conformance for the language-convention axes (BACK-1272).

Runs calls://?uncalled, imports:// and hotspots:// over the tiny per-language
projects in tests/fixtures/conventions/ and asserts against expected.yaml. See
that file's header for the row format and the xfail / not_supported policy.
"""

import json
from pathlib import Path

import pytest
import yaml
from conftest import _run_reveal_direct

pytestmark = pytest.mark.conformance

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conventions"
EXPECTED = yaml.safe_load((FIXTURES_DIR / "expected.yaml").read_text(encoding="utf-8"))


@pytest.fixture(params=sorted(EXPECTED))
def lang(request) -> str:
    return request.param


def _json(uri: str, *args: str) -> dict:
    result = _run_reveal_direct(uri, "--format", "json", *args)
    return json.loads(result.stdout)


def _row(request, lang: str, key: str):
    """Row value, or None when declared not_supported; applies a strict xfail if declared."""
    row = EXPECTED[lang][key]
    if isinstance(row, dict) and 'not_supported' in row:
        pytest.skip(f"{lang}.{key} not supported: {row['not_supported']}")
    if isinstance(row, dict) and 'xfail' in row:
        request.applymarker(pytest.mark.xfail(reason=row['xfail'], strict=True))
        return row['expected']
    return row


def test_uncalled_excludes_implicit_entry_points(lang, request):
    expected = _row(request, lang, 'uncalled')
    result = _json(f"calls://{FIXTURES_DIR / lang}?uncalled")
    assert sorted(e['name'] for e in result['entries']) == sorted(expected)


def test_uncalled_counts_test_entry_points(lang, request):
    result = _json(f"calls://{FIXTURES_DIR / lang}?uncalled")
    assert result['test_entrypoints_excluded'] == EXPECTED[lang]['test_entrypoints_excluded']


def test_stdlib_import_classification(lang, request):
    expected = _row(request, lang, 'imports')
    result = _json(f"imports://{FIXTURES_DIR / lang}")
    got = {}

    def walk(node):
        if isinstance(node, dict):
            if 'classification' in node and 'module' in node:
                got[node['module']] = node['classification']
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(result)
    assert {m: got.get(m) for m in expected} == expected


def test_has_test_hint(lang, request):
    expected = _row(request, lang, 'has_test_hint')
    result = _json(f"hotspots://{FIXTURES_DIR / lang}?min_complexity=1&functions_only=true&top=50")
    got = {f['name']: f['has_test_hint'] for f in result['function_hotspots']}
    assert {n: got.get(n) for n in expected} == expected
