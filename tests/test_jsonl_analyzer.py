"""Tests for JSONL (JSON Lines) analyzer."""

import unittest
import tempfile
import os
import json
from reveal.analyzers.jsonl import JsonlAnalyzer


class TestJsonlAnalyzer(unittest.TestCase):
    """Test JSONL analyzer."""

    def create_temp_jsonl(self, records: list) -> str:
        """Helper: Create temp JSONL file from list of dicts."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.jsonl")
        with open(path, 'w') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')
        return path

    def create_temp_jsonl_raw(self, content: str) -> str:
        """Helper: Create temp JSONL file from raw string."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.jsonl")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_basic_structure(self):
        """Test basic JSONL structure extraction."""
        records = [
            {"type": "user", "name": "Alice"},
            {"type": "user", "name": "Bob"},
            {"type": "event", "action": "login"}
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('records', structure)
            # Summary + records
            records_out = structure['records']
            self.assertGreater(len(records_out), 0)

            # First should be summary
            self.assertIn('Summary', records_out[0]['name'])

        finally:
            self.teardown_file(path)

    def test_record_type_distribution(self):
        """Test record type counting."""
        records = [
            {"type": "a"},
            {"type": "a"},
            {"type": "b"},
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            summary = structure['records'][0]
            # Should show type distribution
            self.assertIn('a: 2', summary['preview'])
            self.assertIn('b: 1', summary['preview'])

        finally:
            self.teardown_file(path)

    def test_empty_file(self):
        """Test with empty JSONL file."""
        path = self.create_temp_jsonl_raw("")
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            # Should have summary showing 0 records
            self.assertIn('0 records', structure['records'][0]['name'])

        finally:
            self.teardown_file(path)

    def test_invalid_json_line(self):
        """Test handling of malformed JSON lines."""
        content = '{"valid": true}\n{invalid json\n{"also": "valid"}\n'
        path = self.create_temp_jsonl_raw(content)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            records = structure['records']
            # Should include invalid marker
            invalid_records = [r for r in records if 'Invalid' in r['name']]
            self.assertEqual(len(invalid_records), 1)

        finally:
            self.teardown_file(path)

    def test_extract_by_number(self):
        """Test extracting specific record by number."""
        records = [
            {"id": 1, "data": "first"},
            {"id": 2, "data": "second"},
            {"id": 3, "data": "third"}
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)

            # Extract record 2
            result = analyzer.extract_element('record', '2')

            self.assertIsNotNone(result)
            self.assertIn('Record 2', result['name'])
            self.assertIn('"id": 2', result['source'])

        finally:
            self.teardown_file(path)

    def test_extract_by_type(self):
        """Test extracting records by type."""
        records = [
            {"type": "user", "name": "Alice"},
            {"type": "event", "action": "click"},
            {"type": "user", "name": "Bob"},
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)

            # Extract all 'user' records
            result = analyzer.extract_element('record', 'user')

            self.assertIsNotNone(result)
            self.assertIn('user records', result['name'])
            self.assertIn('Alice', result['source'])
            self.assertIn('Bob', result['source'])

        finally:
            self.teardown_file(path)

    def test_extract_nonexistent_record(self):
        """Test extracting nonexistent record returns None."""
        records = [{"id": 1}]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)

            result = analyzer.extract_element('record', '999')
            self.assertIsNone(result)

        finally:
            self.teardown_file(path)

    def test_conversation_message_preview(self):
        """Test preview generation for conversation logs."""
        records = [
            {"message": {"role": "user", "content": "Hello there!"}},
            {"message": {"role": "assistant", "content": "Hi! How can I help?"}}
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            # Check preview contains role info
            records_out = structure['records']
            user_record = [r for r in records_out if 'user' in r.get('preview', '').lower()]
            self.assertGreater(len(user_record), 0)

        finally:
            self.teardown_file(path)

    def test_conversation_content_blocks(self):
        """Test preview for Claude API style content blocks."""
        records = [
            {"message": {"role": "user", "content": [{"type": "text", "text": "Hello from blocks!"}]}}
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            records_out = structure['records']
            # Should extract text from content block
            preview_texts = [r.get('preview', '') for r in records_out]
            self.assertTrue(any('Hello from blocks' in p for p in preview_texts))

        finally:
            self.teardown_file(path)

    def test_head_slicing(self):
        """Test --head slicing on records."""
        records = [{"id": i} for i in range(20)]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure(head=3)

            # Summary + 3 records
            self.assertEqual(len(structure['records']), 4)

        finally:
            self.teardown_file(path)

    def test_tail_slicing(self):
        """Test --tail slicing on records."""
        records = [{"id": i} for i in range(20)]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure(tail=3)

            # Summary + 3 records
            self.assertEqual(len(structure['records']), 4)

        finally:
            self.teardown_file(path)

    def test_default_limit(self):
        """Test default 10-record limit."""
        records = [{"id": i} for i in range(50)]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            # Summary + 10 default records
            self.assertEqual(len(structure['records']), 11)

        finally:
            self.teardown_file(path)

    def test_skip_empty_lines(self):
        """Test that empty lines are skipped."""
        content = '{"id": 1}\n\n{"id": 2}\n\n\n{"id": 3}\n'
        path = self.create_temp_jsonl_raw(content)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            # Should find 3 records despite empty lines
            self.assertIn('3 records', structure['records'][0]['name'])

        finally:
            self.teardown_file(path)

    def test_line_numbers_accurate(self):
        """Test that line numbers are accurate."""
        content = '{"id": 1}\n\n{"id": 2}\n'
        path = self.create_temp_jsonl_raw(content)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            records = structure['records']
            # Skip summary
            data_records = [r for r in records if 'Summary' not in r['name']]

            # First record at line 1
            self.assertEqual(data_records[0]['line'], 1)
            # Second record at line 3 (after empty line)
            self.assertEqual(data_records[1]['line'], 3)

        finally:
            self.teardown_file(path)

    def test_record_without_type(self):
        """Test records without 'type' field default to 'record'."""
        records = [
            {"name": "Alice"},
            {"name": "Bob"}
        ]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            # Check record naming
            data_records = [r for r in structure['records'] if 'Summary' not in r['name']]
            self.assertTrue(all('record' in r['name'].lower() for r in data_records))

        finally:
            self.teardown_file(path)

    def test_build_preview_fallback(self):
        """Test preview fallback shows keys when no message format."""
        records = [{"foo": 1, "bar": 2, "baz": 3}]
        path = self.create_temp_jsonl(records)
        try:
            analyzer = JsonlAnalyzer(path)
            structure = analyzer.get_structure()

            records_out = structure['records']
            data_record = [r for r in records_out if 'Summary' not in r['name']][0]

            # Should show keys
            self.assertIn('foo', data_record['preview'])
            self.assertIn('bar', data_record['preview'])

        finally:
            self.teardown_file(path)


if __name__ == '__main__':
    unittest.main()
