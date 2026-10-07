"""BACK-1739: V026 follows a ``.relative_to()`` result one hop inside a function.

``rel = p.relative_to(base)`` followed by ``str(rel)`` or ``f"{rel}"`` leaks
backslashes on Windows exactly like ``str(p.relative_to(base))`` does, but the
single-line regex never saw it (3 of 15 macOS/Windows-only CI breaks since 09-01).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.rules.validation.V026 import V026

pytestmark = pytest.mark.component


def _scan(tmp_path: Path, source: str, name: str = "mod.py"):
    root = tmp_path / "reveal"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / name).write_text(source, encoding="utf-8")
    with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
         patch("reveal.rules.validation.V026.is_dev_checkout", return_value=True):
        return V026().check("reveal://.", None, "")


class TestOneHopPositives:
    def test_str_of_relative_to_local(self, tmp_path):
        found = _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return str(rel)\n"
        ))
        assert [(d.rule_code, d.line) for d in found] == [("V026", 3)]

    def test_fstring_of_relative_to_local(self, tmp_path):
        found = _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return f'{rel}/x'\n"
        ))
        assert [d.line for d in found] == [3]

    def test_dict_key_use_is_still_flagged_until_noqa(self, tmp_path):
        found = _scan(tmp_path, (
            "def f(p, base, out):\n"
            "    rel = p.relative_to(base)\n"
            "    out[str(rel)] = 1\n"
        ))
        assert [d.line for d in found] == [3]

    def test_async_function_and_nested_function(self, tmp_path):
        found = _scan(tmp_path, (
            "async def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    def inner():\n"
            "        other = p.relative_to(base)\n"
            "        return str(other)\n"
            "    return rel\n"
        ))
        assert [d.line for d in found] == [5]


class TestOneHopNegatives:
    def test_to_posix_applied(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return to_posix(rel)\n"
        )) == []

    def test_as_posix_applied(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return str(rel.as_posix()) + f'{rel.as_posix()}'\n"
        )) == []

    def test_used_only_as_a_path(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return rel.parts[0], rel / 'x', rel.name\n"
        )) == []

    def test_assignment_and_use_in_different_functions(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    return rel\n"
            "\n"
            "def g(rel):\n"
            "    return str(rel)\n"
        )) == []

    def test_name_rebound_before_use(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base):\n"
            "    rel = p.relative_to(base)\n"
            "    rel = to_posix(rel)\n"
            "    return str(rel)\n"
        )) == []

    def test_noqa_suppresses(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, base, out):\n"
            "    rel = p.relative_to(base)\n"
            "    out[str(rel)] = 1  # noqa: V026 -- same-platform dict key\n"
        )) == []

    def test_unparseable_file_is_skipped_not_raised(self, tmp_path):
        assert _scan(tmp_path, "def f(:\n") == []

    def test_existing_single_line_form_still_reported_once(self, tmp_path):
        found = _scan(tmp_path, (
            "def f(p, base):\n"
            "    return str(p.relative_to(base))\n"
        ))
        assert [d.line for d in found] == [2]


class TestBranchRebinding:
    """A rebinding in a branch does not dominate a later use (tree_view.py shape)."""

    def test_except_branch_rebind_does_not_clear(self, tmp_path):
        found = _scan(tmp_path, (
            "def f(p, root):\n"
            "    try:\n"
            "        rel = p.relative_to(root)\n"
            "    except ValueError:\n"
            "        rel = p\n"
            "    return f'{rel}'\n"
        ))
        assert [d.line for d in found] == [6]

    def test_rebind_in_same_block_clears(self, tmp_path):
        assert _scan(tmp_path, (
            "def f(p, root):\n"
            "    try:\n"
            "        rel = p.relative_to(root)\n"
            "        rel = to_posix(rel)\n"
            "        return str(rel)\n"
            "    except ValueError:\n"
            "        return ''\n"
        )) == []
