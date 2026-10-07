"""BACK-1715: a flag that reads no element must refuse a second positional path.

`reveal a.conf b.conf --check-acl` parses b.conf as the ELEMENT argument. These flags never
read an element, so the run answered for a.conf only, exited 0 and said nothing about b.conf
(the BACK-1687 hole, found for --validate-schema, was wider than that one flag). Each is now a
usage error (stderr names the ignored argument, exit 2), declared once as ELEMENT_LESS_FLAGS.
"""

import subprocess
import sys

import pytest

CONF = ('server {{\n  listen 443 ssl;\n  server_name {name}.example.com;\n'
        '  ssl_certificate /etc/ssl/{name}.pem;\n  location / {{ return 200; }}\n}}\n')
PY = 'def f():\n    return 1\n\n\ndef g():\n    return 2\n'

# flag argv -> file kind it is exercised on (nginx flags need nginx configs)
NGINX_FLAGS = [
    ['--check-acl'], ['--diagnose'], ['--global-audit'], ['--validate-nginx-acme'],
    ['--extract', 'domains'], ['--check-conflicts'], ['--cpanel-certs'],
]
PY_FLAGS = [['--check'], ['--meta'], ['--explain-file'], ['--capabilities'], ['--show-ast']]


def _reveal(cwd, *args, stdin=None):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.fixture
def files(tmp_path):
    for name in ('a', 'b'):
        (tmp_path / f'{name}.conf').write_text(CONF.format(name=name), encoding='utf-8')
        (tmp_path / f'{name}.py').write_text(PY, encoding='utf-8')
    return tmp_path


def _ids(flags):
    return [' '.join(f) for f in flags]


@pytest.mark.parametrize('flag', NGINX_FLAGS, ids=_ids(NGINX_FLAGS))
def test_nginx_flag_refuses_a_second_path(files, flag):
    proc = _reveal(files, 'a.conf', 'b.conf', *flag)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert 'b.conf' in proc.stderr
    assert flag[0] in proc.stderr
    assert '--stdin' in proc.stderr


@pytest.mark.parametrize('flag', PY_FLAGS, ids=_ids(PY_FLAGS))
def test_generic_flag_refuses_a_second_path(files, flag):
    proc = _reveal(files, 'a.py', 'b.py', *flag)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert 'b.py' in proc.stderr
    assert flag[0] in proc.stderr


def test_line_suffix_form_is_refused_too(files):
    proc = _reveal(files, 'a.py:3', '--meta')
    assert proc.returncode == 2
    assert ':3' in proc.stderr


# Negative controls: what must not change.
@pytest.mark.parametrize('flag', NGINX_FLAGS, ids=_ids(NGINX_FLAGS))
def test_nginx_flag_on_one_path_still_runs(files, flag):
    proc = _reveal(files, 'a.conf', *flag)
    assert 'reads no element' not in proc.stderr
    assert proc.returncode != 2 or flag == ['--global-audit']  # global-audit exits 2 on findings
    assert 'usage' not in proc.stderr.lower()


@pytest.mark.parametrize('flag', PY_FLAGS, ids=_ids(PY_FLAGS))
def test_generic_flag_on_one_path_still_runs(files, flag):
    proc = _reveal(files, 'a.py', *flag)
    assert 'reads no element' not in proc.stderr
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize('flag', [['--meta'], ['--check']], ids=['--meta', '--check'])
def test_stdin_still_runs_every_path(files, flag):
    proc = _reveal(files, '--stdin', *flag, stdin='a.conf\nb.conf\n')
    assert 'reads no element' not in proc.stderr
    assert 'a.conf' in proc.stdout and 'b.conf' in proc.stdout


def test_stdin_check_acl_still_answers_every_path(files):
    proc = _reveal(files, '--stdin', '--check-acl', stdin='a.conf\nb.conf\n')
    assert 'reads no element' not in proc.stderr
    assert proc.stdout.count('No root directives found') == 2


def test_file_and_element_still_work(files):
    proc = _reveal(files, 'a.py', 'f')
    assert proc.returncode == 0
    assert 'return 1' in proc.stdout


@pytest.mark.parametrize('flag', [['--boundary'], ['--head', '1'], ['--format', 'json']],
                         ids=_ids([['--boundary'], ['--head', '1'], ['--format', 'json']]))
def test_flags_that_take_an_element_still_take_one(files, flag):
    proc = _reveal(files, 'a.py', 'f', *flag)
    assert proc.returncode == 0, proc.stderr
    assert 'reads no element' not in proc.stderr


def test_every_declared_flag_is_a_real_parser_option():
    """A declaration naming a dest the parser lacks would silently guard nothing."""
    from reveal.cli.parser import create_argument_parser
    from reveal.cli.routing import ELEMENT_LESS_FLAGS
    dests = {a.dest: a.option_strings for a in create_argument_parser('x')._actions}
    for dest, spelling in ELEMENT_LESS_FLAGS.items():
        assert spelling in dests.get(dest, []), dest
