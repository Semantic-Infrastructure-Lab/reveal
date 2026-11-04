"""I005 compares imported bindings, not first source lines (BACK-2490).

A grouped import (Rust ``use std::{a, b}``) yields one statement per name, all on one
line, so keying on the line made the line a duplicate of itself; two different
multi-line ``use std::{`` statements shared that first line and collided; and the
comparison was case-insensitive, so Kotlin ``Dp`` and ``dp`` were one import.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import pytest

from reveal.rules.imports.I005 import I005

pytestmark = pytest.mark.component


class TestI005Bindings(unittest.TestCase):
    def setUp(self):
        self.rule = I005()
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, name, code):
        path = self.tmp / name
        path.write_text(code, encoding='utf-8')
        return self.rule.check(str(path), {}, code)

    def test_rust_grouped_use_is_not_its_own_duplicate(self):
        result = self._check('help.rs', (
            "use std::{collections::BTreeMap, fmt::Write};\n"
            "\n"
            "use crate::flags::{Category, Flag, defs::FLAGS, doc::version};\n"
        ))
        self.assertEqual([(d.line, d.message) for d in result], [])

    def test_rust_two_multiline_groups_from_one_crate_do_not_collide(self):
        result = self._check('main.rs', (
            "use std::{\n"
            "    io,\n"
            "    path::Path,\n"
            "};\n"
            "\n"
            "fn run() {\n"
            "    use std::{\n"
            "        sync::mpsc,\n"
            "        thread,\n"
            "    };\n"
            "}\n"
        ))
        self.assertEqual([(d.line, d.message) for d in result], [])

    def test_kotlin_names_differing_only_in_case_are_different_imports(self):
        result = self._check('Layout.kt', (
            "package app\n"
            "\n"
            "import androidx.compose.ui.unit.Dp\n"
            "import androidx.compose.ui.unit.dp\n"
        ))
        self.assertEqual([(d.line, d.message) for d in result], [])

    def test_rust_real_duplicate_is_still_reported(self):
        result = self._check('lib.rs', (
            "use std::io;\n"
            "use std::fmt;\n"
            "use std::io;\n"
        ))
        self.assertEqual([d.line for d in result], [3])
        self.assertIn('first imported at line 1', result[0].message)

    def test_rust_name_repeated_in_a_later_group_is_reported(self):
        result = self._check('lib.rs', (
            "use std::{io, fmt};\n"
            "use std::{io, path::Path};\n"
        ))
        self.assertEqual([d.line for d in result], [2])

    def test_python_module_level_duplicate_is_still_reported(self):
        result = self._check('mod.py', (
            "import os\n"
            "from a import b\n"
            "import os\n"
        ))
        self.assertEqual([d.line for d in result], [3])

    def test_python_case_differing_modules_are_different_imports(self):
        result = self._check('mod.py', (
            "import Foo\n"
            "import foo\n"
        ))
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
