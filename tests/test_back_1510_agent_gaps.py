"""BACK-1510: small agent-facing gaps found by the 0.129.0 help audit."""

import subprocess
import sys
from pathlib import Path

import pytest

from reveal.adapters.ast.queries import format_query
from reveal.adapters.json.parsing import load_json


def test_glob_filter_prints_readably():
    # 'nameglob*x*' was then read by the hint code as an unknown key 'nameglob'.
    assert format_query({'name': {'op': 'glob', 'value': '*auth*'}}) == 'name=*auth* (glob)'
    assert format_query({'complexity': {'op': '>', 'value': 10}}) == 'complexity>10'


def test_json_on_a_directory_says_so(tmp_path):
    with pytest.raises(ValueError, match='needs a JSON file, not a directory'):
        load_json(tmp_path)


def test_json_on_jsonl_points_at_the_file_analyzer(tmp_path):
    f = tmp_path / 'log.jsonl'
    f.write_text('{"a": 1}\n{"a": 2}\n', encoding='utf-8')
    with pytest.raises(ValueError, match="(?s)JSON Lines file.*Use 'reveal "):
        load_json(f)


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX pipe semantics')
def test_small_output_into_a_closed_pipe_is_quiet(tmp_path):
    # Output smaller than the buffer failed at interpreter exit with
    # "Exception ignored ... BrokenPipeError" and exit 120.
    src = tmp_path / 'm.py'
    src.write_text('def f():\n    return 1\n', encoding='utf-8')
    proc = subprocess.run(
        f'"{sys.executable}" -m reveal "{src}" f | head -c 1 >/dev/null',
        shell=True, capture_output=True, text=True, encoding='utf-8',
        executable='/bin/bash', cwd=str(Path(__file__).parent.parent),
    )
    assert 'BrokenPipeError' not in proc.stderr
    assert 'Exception ignored' not in proc.stderr
