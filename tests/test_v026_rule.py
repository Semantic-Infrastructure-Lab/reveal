"""Tests for V026: path-handling convention (portability) rule."""

from pathlib import Path
from unittest.mock import patch

from reveal.rules.validation.V026 import V026


class TestV026Init:
    """Test rule initialization."""

    def test_rule_attributes(self):
        rule = V026()

        assert rule.code == "V026"
        assert rule.version == "1.0.0"
        assert rule.internal is True
        assert rule.uri_patterns == ['^reveal://.*']


class TestV026NonRevealUri:
    """The rule only fires via reveal:// self-check."""

    def test_ignores_regular_file_calls(self):
        rule = V026()
        detections = rule.check(
            "some/file.py", None, "str(x.relative_to(root))"
        )
        assert detections == []


class TestV026Detection:
    """Detection logic against a fabricated reveal-root tree."""

    def _make_fake_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "reveal"
        root.mkdir()
        (root / "__init__.py").write_text("")
        return root

    def test_no_violations_in_clean_file(self, tmp_path):
        root = self._make_fake_root(tmp_path)
        (root / "clean.py").write_text(
            "from .utils.path_utils import to_posix, is_unsafe_scan_root\n"
            "\n"
            "def f(p, base):\n"
            "    return to_posix(p.relative_to(base))\n"
        )

        rule = V026()
        with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
             patch("reveal.rules.validation.V026.is_dev_checkout", return_value=True):
            detections = rule.check("reveal://.", None, "")

        assert detections == []

    def test_detects_str_wrapping_relative_to(self, tmp_path):
        root = self._make_fake_root(tmp_path)
        (root / "bad.py").write_text(
            "def f(p, base):\n"
            "    return str(p.relative_to(base))\n"
        )

        rule = V026()
        with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
             patch("reveal.rules.validation.V026.is_dev_checkout", return_value=True):
            detections = rule.check("reveal://.", None, "")

        assert len(detections) == 1
        assert detections[0].rule_code == "V026"
        assert "bad.py" in detections[0].file_path
        assert detections[0].line == 2

    def test_detects_hardcoded_root_literal_comparison(self, tmp_path):
        root = self._make_fake_root(tmp_path)
        (root / "bad_root.py").write_text(
            "def is_root(path):\n"
            "    return path == '/tmp'\n"
        )

        rule = V026()
        with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
             patch("reveal.rules.validation.V026.is_dev_checkout", return_value=True):
            detections = rule.check("reveal://.", None, "")

        assert len(detections) == 1
        assert detections[0].rule_code == "V026"
        assert "bad_root.py" in detections[0].file_path

    def test_exempts_path_utils_itself(self, tmp_path):
        root = self._make_fake_root(tmp_path)
        utils_dir = root / "utils"
        utils_dir.mkdir()
        # path_utils.py legitimately contains str(path) and the root literals
        # themselves — it's the canonical implementation, must not self-flag.
        (utils_dir / "path_utils.py").write_text(
            "def to_posix(path):\n"
            "    return str(path).replace('\\\\', '/')\n"
            "\n"
            "_STATIC_UNSAFE_ROOTS = ('/', '/tmp', '/var')\n"
        )

        rule = V026()
        with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
             patch("reveal.rules.validation.V026.is_dev_checkout", return_value=True):
            detections = rule.check("reveal://.", None, "")

        assert detections == []

    def test_no_dev_checkout_returns_empty(self, tmp_path):
        root = self._make_fake_root(tmp_path)
        (root / "bad.py").write_text("str(p.relative_to(base))\n")

        rule = V026()
        with patch("reveal.rules.validation.V026.find_reveal_root", return_value=root), \
             patch("reveal.rules.validation.V026.is_dev_checkout", return_value=False):
            detections = rule.check("reveal://.", None, "")

        assert detections == []
