"""BACK-1687: --validate-schema must not drop paths silently.

`reveal a.md b.md --validate-schema X` parses b.md as the ELEMENT argument, which the
validation branch never reads, so a batch looked clean after checking only a.md. It is now
refused (usage error, exit 2). `--stdin --validate-schema` validated paths until the first
failing one, whose sys.exit ended the run before the rest were read; it now validates every
path and exits 1 if any failed.
"""

import subprocess
import sys

import pytest


def _reveal(cwd, *args, stdin=None):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.fixture
def docs(tmp_path):
    (tmp_path / 'good.md').write_text('---\ntitle: Good\n---\n# Good\n', encoding='utf-8')
    (tmp_path / 'good2.md').write_text('---\ntitle: Good Two\n---\n# Good Two\n', encoding='utf-8')
    (tmp_path / 'bad.md').write_text('# No front matter\n', encoding='utf-8')
    (tmp_path / 'bad2.md').write_text('# Also no front matter\n', encoding='utf-8')
    return tmp_path


def test_second_positional_path_is_refused_not_dropped(docs):
    proc = _reveal(docs, 'good.md', 'bad.md', '--validate-schema', 'hugo')
    assert proc.returncode == 2
    assert 'bad.md' in proc.stderr
    assert '--stdin' in proc.stderr
    assert 'No issues found' not in proc.stdout


def test_stdin_reports_the_failure_after_a_clean_file(docs):
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo', stdin='good.md\nbad.md\n')
    assert proc.returncode == 1
    assert 'bad.md' in proc.stdout


def test_stdin_validates_every_path_after_the_first_failure(docs):
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo',
                   stdin='bad.md\ngood.md\nbad2.md\n')
    assert proc.returncode == 1
    assert 'bad.md' in proc.stdout
    assert 'good.md' in proc.stdout
    assert 'bad2.md' in proc.stdout


# Negative controls: what must not change.
def test_single_valid_file_still_passes(docs):
    proc = _reveal(docs, 'good.md', '--validate-schema', 'hugo')
    assert proc.returncode == 0
    assert 'No issues found' in proc.stdout


def test_single_invalid_file_still_fails(docs):
    proc = _reveal(docs, 'bad.md', '--validate-schema', 'hugo')
    assert proc.returncode == 1
    assert 'bad.md' in proc.stdout


def test_stdin_all_valid_exits_zero(docs):
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo', stdin='good.md\ngood2.md\n')
    assert proc.returncode == 0
    assert 'good2.md' in proc.stdout


def test_two_positionals_without_the_flag_are_still_file_and_element(docs):
    proc = _reveal(docs, 'good.md', 'Good')
    assert proc.returncode == 0
    assert 'Good' in proc.stdout


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_unknown_schema_is_one_usage_error(docs, fmt):
    import json
    proc = _reveal(docs, '--stdin', '--validate-schema', 'missing-sprint-schema',
                   '--format', fmt, stdin='good.md\ngood2.md\n')
    assert proc.returncode == 2
    if fmt == 'json':
        result = json.loads(proc.stdout)
        assert 'not found' in result['error']
        assert result['type'] == 'schema_validation_batch'
    else:
        assert proc.stderr.count("Schema 'missing-sprint-schema' not found") == 1


def test_batch_json_is_one_document_with_per_file_outcomes(docs):
    import json
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo', '--format', 'json',
                   stdin='bad.md\ngood.md\nmissing.md\nbad2.md\n')
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result['type'] == 'schema_validation_batch'
    assert result['source_type'] == 'runtime'
    assert [row['source'] for row in result['results']] == ['bad.md', 'good.md', 'missing.md', 'bad2.md']
    assert [row['status'] for row in result['results']] == ['invalid', 'valid', 'error', 'invalid']
    assert result['summary'] == {'total': 4, 'valid': 1, 'invalid': 2, 'errors': 1}
    assert result['results'][0]['detections']
    assert result['results'][2]['error']


@pytest.mark.parametrize('stdin', ['missing.md\n', '', '.\n'])
def test_missing_empty_or_directory_batch_cannot_pass(docs, stdin):
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo', stdin=stdin)
    assert proc.returncode == 1


def test_non_markdown_input_is_not_a_clean_schema_check(docs):
    import json
    (docs / 'code.py').write_text('x = 1\n', encoding='utf-8')
    proc = _reveal(docs, '--stdin', '--validate-schema', 'hugo', '--format', 'json', stdin='code.py\ngood.md\n')
    result = json.loads(proc.stdout)
    assert proc.returncode == 1
    assert [row['status'] for row in result['results']] == ['error', 'valid']
