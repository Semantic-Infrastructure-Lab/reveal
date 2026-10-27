"""An unknown --validate-schema name is a usage error (exit 2) on every path (BACK-2213 C19)."""
import subprocess
import sys


def _run(tmp_path, stdin):
    doc = tmp_path / 'd.md'
    doc.write_text('# t\n', encoding='utf-8')
    base = [sys.executable, '-m', 'reveal']
    flag = ['--validate-schema', 'no-such-schema']
    if stdin:
        return subprocess.run(base + flag + ['--stdin'], input=f'{doc}\n',
                              capture_output=True, text=True, encoding='utf-8')
    return subprocess.run(base + [str(doc)] + flag, capture_output=True, text=True, encoding='utf-8')


def test_single_file_unknown_schema_exits_2(tmp_path):
    assert _run(tmp_path, stdin=False).returncode == 2


def test_stdin_unknown_schema_exits_2(tmp_path):
    assert _run(tmp_path, stdin=True).returncode == 2
