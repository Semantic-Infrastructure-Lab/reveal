"""Tests for --grep flag: text search with structural context."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def run_reveal(*args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal.main'] + list(args),
        capture_output=True, text=True, encoding='utf-8',
    )


class TestGrepMarkdown(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        self.f.write(
            '# Overview\n\nThis doc covers foo and bar.\n\n'
            '## Installation\n\nRun foo install.\n\n'
            '## Configuration\n\nSet bar=true in config.\n'
            '| Key | Value |\n|-----|-------|\n| bar | true  |\n'
        )
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_hits_grouped_by_heading(self):
        r = run_reveal(self.f.name, '--grep', 'foo')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Overview', r.stdout)
        self.assertIn('Installation', r.stdout)
        self.assertNotIn('Configuration', r.stdout)

    def test_table_cell_content_found(self):
        r = run_reveal(self.f.name, '--grep', 'bar')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Configuration', r.stdout)

    def test_term_in_table_not_found_by_search_gets_grep_hint(self):
        r = run_reveal(self.f.name, '--search', 'bar')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--grep', r.stdout)

    def test_no_matches(self):
        r = run_reveal(self.f.name, '--grep', 'zzznomatch')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('No matches found', r.stdout)
        self.assertIn('--name', r.stdout)

    def test_hit_count_in_header(self):
        r = run_reveal(self.f.name, '--grep', 'foo')
        self.assertIn('hits', r.stdout)

    def test_case_insensitive(self):
        r = run_reveal(self.f.name, '--grep', 'FOO', '--ignore-case')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Overview', r.stdout)

    def test_case_sensitive_by_default(self):
        r = run_reveal(self.f.name, '--grep', 'FOO')
        self.assertIn('No matches found', r.stdout)

    def test_regex_pattern(self):
        r = run_reveal(self.f.name, '--grep', r'foo|bar')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('hits', r.stdout)

    def test_json_output(self):
        r = run_reveal(self.f.name, '--grep', 'foo', '--format', 'json')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data['type'], 'grep_results')
        self.assertGreater(data['total_hits'], 0)
        self.assertTrue(all('name' in g for g in data['groups']))


class TestGrepPython(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        self.f.write(
            'def parse_token(s):\n'
            '    if s.startswith("escape"):\n'
            '        return escape(s)\n'
            '    return s\n\n'
            'def sanitize(s):\n'
            '    return s.replace("escape", "")\n\n'
            'class Lexer:\n'
            '    def tokenize(self, s):\n'
            '        return escape(s)\n'
        )
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_hits_grouped_by_function(self):
        r = run_reveal(self.f.name, '--grep', 'escape')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('parse_token', r.stdout)
        self.assertIn('sanitize', r.stdout)

    def test_multiple_hits_same_function(self):
        r = run_reveal(self.f.name, '--grep', 'escape')
        self.assertIn('parse_token', r.stdout)
        lines_for_parse = [l for l in r.stdout.splitlines() if 'parse_token' in l]
        self.assertTrue(lines_for_parse)

    def test_class_method_grouped(self):
        r = run_reveal(self.f.name, '--grep', 'escape')
        self.assertIn('tokenize', r.stdout)


class TestGrepFlatFile(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        self.f.write('line one\nfoo here\nline three\nfoo again\n')
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_flat_file_shows_line_numbers(self):
        r = run_reveal(self.f.name, '--grep', 'foo')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('line 2', r.stdout)
        self.assertIn('line 4', r.stdout)


class TestGrepBackslashI(unittest.TestCase):
    """--ignore-case short form -i works."""

    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        self.f.write('# Heading\n\nSome TEXT here.\n')
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_short_flag_i(self):
        r = run_reveal(self.f.name, '--grep', 'text', '-i')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Heading', r.stdout)


class TestGrepInvalidPattern(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        self.f.write('hello\n')
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_invalid_regex_exits_nonzero(self):
        r = run_reveal(self.f.name, '--grep', '[invalid')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('invalid pattern', r.stderr)


class TestGrepDirectoryBinaryDetection(unittest.TestCase):
    """BACK-743: extensionless binaries must not be grepped as text."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, 'notes.txt'), 'w') as f:
            f.write('needle in a text file\n')
        # No extension, but contains a NUL byte early on, like an ELF binary --
        # the tell _BINARY_EXTENSIONS' suffix allowlist can't catch.
        with open(os.path.join(self.d, 'compiled-binary'), 'wb') as f:
            f.write(b'\x7fELF\x00\x00\x00needle\x00' + os.urandom(256))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def test_extensionless_binary_not_matched(self):
        r = run_reveal(self.d, '--grep', 'needle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('notes.txt', r.stdout)
        self.assertNotIn('compiled-binary', r.stdout)

    def test_extensionless_text_file_still_matched(self):
        with open(os.path.join(self.d, 'plain-no-ext'), 'w') as f:
            f.write('needle here too\n')
        r = run_reveal(self.d, '--grep', 'needle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('plain-no-ext', r.stdout)


class TestGrepSearchHintHyphen(unittest.TestCase):
    """BACK-308: --search on terms with hyphens that exist in file should show --grep hint."""

    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        self.f.write('# Backlog\n\n| ID | Item |\n|----|------|\n| BACK-308 | Fix hint |\n')
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_hyphen_term_gets_grep_hint(self):
        r = run_reveal(self.f.name, '--search', 'BACK-308')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--grep', r.stdout)
        self.assertIn('BACK-308', r.stdout)

    def test_hyphen_term_found_by_grep(self):
        r = run_reveal(self.f.name, '--grep', 'BACK-308')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('No matches found', r.stdout)
        self.assertIn('Backlog', r.stdout)
