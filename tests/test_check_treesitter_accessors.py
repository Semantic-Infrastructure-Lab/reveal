"""Unit tests for scripts/check_treesitter_accessors.py (bare Node accessor guard)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    'check_treesitter_accessors', _ROOT / 'scripts' / 'check_treesitter_accessors.py')
cta = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cta)


@pytest.mark.parametrize('src, expected', [
    # The BACK-1406 helper that went red on the language-pack 1.8.1 floor.
    ("data[node.start_byte:node.end_byte]", [(1, 'end_byte'), (1, 'start_byte')]),
    ("n = node.child_count", [(1, 'child_count')]),
    ("root.has_error", [(1, 'has_error')]),
    ("node.start_point.row", [(1, 'start_point')]),
    ("node.to_sexp()", [(1, 'to_sexp')]),
    ("x = (\n    node\n    .end_byte)", [(2, 'end_byte')]),
])
def test_flags_bare_reads(src, expected):
    assert cta.find_offenders(src) == expected


@pytest.mark.parametrize('src', [
    "data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')]",
    "node.start_byte = 3",                                   # write, not a read
    "m.child_count.return_value = 2",                         # MagicMock standing in for the method
    "m.start_byte.side_effect = lambda: 1",
    "node.start_point  # noqa: ts-accessor (the seam)",
    "node.type",                                             # not a guarded accessor
    "obj.start_time",
])
def test_allows(src):
    assert cta.find_offenders(src) == []


def test_repo_has_no_bare_accessors():
    """Strict, not baselined: the only bare reads are the seam's own, marked noqa."""
    result = subprocess.run([sys.executable, str(_ROOT / 'scripts' / 'check_treesitter_accessors.py')],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout
