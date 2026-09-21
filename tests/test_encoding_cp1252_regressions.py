"""Regression tests for BACK-1350: bare text I/O that broke on Windows (cp1252).

Each test runs a child interpreter with ``scripts/cp1252_sim`` on PYTHONPATH, which
makes any encoding-less open()/read_text() decode as cp1252 (what Windows does) on
every OS.  Fixtures contain U+2764 (bytes e2 9d a4; 0x9d is undefined in cp1252).
See internal-docs/design/ENCODING_ROBUSTNESS_2026-09-21.md.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIM = REPO / 'scripts' / 'cp1252_sim'


def _run(code, *args, cwd=None):
    env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='utf-8',
               PYTHONPATH=os.pathsep.join([str(SIM), str(REPO)]))
    env.pop('PYTHONPYCACHEPREFIX', None)
    return subprocess.run([sys.executable, '-c', textwrap.dedent(code), *args],
                          capture_output=True, text=True, encoding='utf-8',
                          env=env, cwd=cwd, timeout=120)


def test_simulator_is_faithful(tmp_path):
    f = tmp_path / 'x.txt'
    f.write_text('❤', encoding='utf-8')
    r = _run("import sys, pathlib; print(pathlib.Path(sys.argv[1]).read_text(errors='replace'))", str(f))
    # Bare read under the simulator must NOT round-trip; otherwise the tests below prove nothing.
    assert '❤' not in r.stdout


def test_nginx_rules_survive_non_ascii_includes(tmp_path):
    inc = tmp_path / 'inc.conf'
    inc.write_text('# ❤ café\n', encoding='utf-8')
    conf = tmp_path / 'nginx.conf'
    conf.write_text(f'# ❤\nevents {{}}\nhttp {{\n  include {inc.as_posix()};\n'
                    '  server { listen 80; server_name a.example.com;\n'
                    '    location /a { proxy_pass http://127.0.0.1:1; }\n  }\n}\n', encoding='utf-8')
    r = _run("import sys; from reveal.main import main; sys.argv=['reveal','check',sys.argv[1]]; main()",
             str(conf))
    assert 'crashed' not in r.stdout + r.stderr
    assert 'UnicodeDecodeError' not in r.stdout + r.stderr


def test_blame_ignore_revs_and_stats_yaml_read_as_utf8(tmp_path):
    (tmp_path / '.git-blame-ignore-revs').write_text('# ❤\nabcdef1234567\n', encoding='utf-8')
    yml = tmp_path / 'q.yaml'
    yml.write_text('# ❤\nthresholds:\n  complexity: 3\n', encoding='utf-8')
    r = _run("""
        import sys
        from pathlib import Path
        from reveal.adapters.git.files import _read_blame_ignore_revs
        from reveal.adapters.stats.queries import _apply_yaml_config_file
        cfg = {'thresholds': {'complexity': 10}, 'penalties': {}}
        print(_read_blame_ignore_revs(sys.argv[1]), _apply_yaml_config_file(Path(sys.argv[2]), cfg), cfg['thresholds']['complexity'])
    """, str(tmp_path), str(yml))
    assert r.returncode == 0, r.stderr
    assert "['abcdef1']" in r.stdout and 'True 3' in r.stdout


def test_grep_finds_non_ascii_pattern(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return "❤"\n', encoding='utf-8')
    r = _run("""
        import sys
        from argparse import Namespace
        from reveal.grep_handler import handle_grep
        handle_grep(sys.argv[1] + '/a.py', '❤', Namespace(format='json'))
    """, str(tmp_path))
    assert '"total_hits": 1' in r.stdout, r.stdout + r.stderr
