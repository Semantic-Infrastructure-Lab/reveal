"""BACK-1773: the per-file extraction flags read no element, so a second path must be refused.

`reveal a.html b.html --metadata` parsed b.html as the ELEMENT, printed "Element 'b.html' not
found in a.html" (exit 1) and never mentioned --metadata. Every per-file flag of the parser's
Markdown, HTML, Type-aware and Quality groups that only the no-element view reads (the
structure view, show_structure) is now declared in ELEMENT_LESS_FLAGS, so it is refused like
--check-acl (exit 2, stderr names the flag and the ignored argument, BACK-1715).

The parser-derived guard fails when a flag is added to one of those groups and classified in
no table, so the next one cannot be missed.
"""

import subprocess
import sys

import pytest

HTML = '<html><head><title>T</title></head><body><h1 id="x">hi</h1><script>1</script></body></html>\n'
MD = '# T\n\n## S\n\nhello [l](http://x.y) `c`\n\n```python\nprint(1)\n```\n'
PY = 'def f():\n    return 1\n'
CONF = 'server {\n  listen 80;\n  server_name a.example.com;\n}\n'

# (kind, flag argv) for every flag newly declared element-less.
CASES = [
    ('html', ['--metadata']), ('html', ['--semantic', 'all']),
    ('html', ['--scripts', 'all']), ('html', ['--styles', 'all']),
    ('md', ['--links']), ('md', ['--link-type', 'internal']), ('md', ['--broken-only']),
    ('md', ['--domain', 'x.y']), ('md', ['--code']), ('md', ['--language', 'python']),
    ('md', ['--inline']), ('md', ['--frontmatter']), ('md', ['--related']),
    ('md', ['--related-all']), ('md', ['--related-flat']),
    ('py', ['--typed']), ('py', ['--filter', 'function']),
    ('conf', ['--server-name', 'a.example.com']), ('conf', ['--log-path', 'x.log']),
    ('py', ['--select', 'E501']), ('py', ['--ignore', 'E501']), ('py', ['--severity', 'high']),
    ('py', ['--no-group']),
]
CONTENT = {'html': HTML, 'md': MD, 'py': PY, 'conf': CONF}


def _reveal(cwd, *args, stdin=None):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.fixture
def files(tmp_path):
    for ext, text in CONTENT.items():
        for name in ('a', 'b'):
            (tmp_path / f'{name}.{ext}').write_text(text, encoding='utf-8')
    return tmp_path


def _ids(cases):
    return [' '.join(flag) for _, flag in cases]


@pytest.mark.parametrize('kind,flag', CASES, ids=_ids(CASES))
def test_flag_refuses_a_second_path(files, kind, flag):
    proc = _reveal(files, f'a.{kind}', f'b.{kind}', *flag)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert f'b.{kind}' in proc.stderr and flag[0] in proc.stderr
    assert 'not found' not in proc.stderr


@pytest.mark.parametrize('kind,flag', CASES, ids=_ids(CASES))
def test_flag_refuses_an_element(files, kind, flag):
    """`reveal a.html '#x' --metadata` dropped --metadata the same way (element wins)."""
    element = {'html': '#x', 'md': 'S', 'py': 'f', 'conf': 'server'}[kind]
    proc = _reveal(files, f'a.{kind}', element, *flag)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert flag[0] in proc.stderr


@pytest.mark.parametrize('kind,flag', CASES, ids=_ids(CASES))
def test_the_stdin_hint_is_truthful(files, kind, flag):
    """The refusal names `ls PATHS | reveal --stdin FLAG`; run that form: it covers both paths."""
    refused = _reveal(files, f'a.{kind}', f'b.{kind}', *flag)
    assert f'reveal --stdin {flag[0]}' in refused.stderr
    proc = _reveal(files, '--stdin', *flag, stdin=f'a.{kind}\nb.{kind}\n')
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr  # 1: a --check-family verdict
    assert 'usage:' not in proc.stderr and 'not found' not in proc.stderr
    assert f'a.{kind}' in proc.stdout + proc.stderr and f'b.{kind}' in proc.stdout + proc.stderr


# Negative controls: what must not change.
@pytest.mark.parametrize('kind,flag', [c for c in CASES if c[1][0] not in ('--log-path', '--severity')],
                         ids=_ids([c for c in CASES if c[1][0] not in ('--log-path', '--severity')]))
def test_one_path_with_the_flag_still_works(files, kind, flag):
    proc = _reveal(files, f'a.{kind}', *flag)
    assert 'reads no element' not in proc.stderr
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert 'Traceback' not in proc.stderr


def test_metadata_on_one_html_file_prints_the_head(files):
    proc = _reveal(files, 'a.html', '--metadata')
    assert proc.returncode == 0, proc.stderr
    assert 'a.html' in proc.stdout


def test_an_html_element_alone_still_extracts(files):
    proc = _reveal(files, 'a.html', '#x')
    assert proc.returncode == 0, proc.stderr
    assert '<h1 id="x">hi</h1>' in proc.stdout


def test_a_second_path_without_a_flag_is_still_an_element_lookup(files):
    proc = _reveal(files, 'a.html', 'b.html')
    assert proc.returncode == 1
    assert "Element 'b.html' not found" in proc.stderr


@pytest.mark.parametrize('argv', [
    ['a.md', 'S', '--head', '1'],
    ['a.py', 'f', '--boundary'],
    ['a.py', 'f', '--format', 'json'],
])
def test_flags_that_read_the_element_still_work_with_one(files, argv):
    proc = _reveal(files, *argv)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'reads no element' not in proc.stderr


def test_section_still_names_its_own_element(files):
    proc = _reveal(files, 'a.md', '--section', 'S')
    assert proc.returncode == 0, proc.stderr
    assert 'S' in proc.stdout


# The guard: every flag of a file-specific parser group is classified.
# Flags that stay out of ELEMENT_LESS_FLAGS although their group is file-specific, with the reason.
NOT_ELEMENT_LESS = {
    'related_depth': 'modifier of --related with a truthy default (1): truthiness cannot tell it was given; '
                     '--related, which is declared, carries the refusal',
    'related_limit': 'modifier of --related with a truthy default (100); same as related_depth',
    'config': 'a config-file path read by the rule engine for every view, not only the structure view',
    'recursive': 'directory walk switch for --check; --check is declared',
}


def _file_specific_dests():
    from reveal.cli.parser import create_argument_parser
    parser = create_argument_parser('')
    return {a.dest for group in parser._action_groups if 'file-specific' in (group.title or '')
            for a in group._group_actions}


def test_every_file_specific_flag_is_classified():
    from reveal.cli.routing import ELEMENT_FLAGS, ELEMENT_LESS_FLAGS, PATHLESS_FLAGS
    classified = set(ELEMENT_LESS_FLAGS) | set(ELEMENT_FLAGS) | set(PATHLESS_FLAGS) | set(NOT_ELEMENT_LESS)
    dests = _file_specific_dests()
    assert {'metadata', 'links', 'typed', 'section', 'validate_schema'} <= dests, \
        'the guard found no file-specific groups: it no longer measures anything'
    assert sorted(dests - classified) == [], \
        'a file-specific flag is in no table: declare it in ELEMENT_LESS_FLAGS (reads no element), ' \
        'ELEMENT_FLAGS (is the element) or PATHLESS_FLAGS, or give its reason in NOT_ELEMENT_LESS'


def test_the_guard_sees_a_missing_declaration():
    """Negative control: with --metadata unclassified the guard names exactly it."""
    from reveal.cli.routing import ELEMENT_FLAGS, ELEMENT_LESS_FLAGS, PATHLESS_FLAGS
    classified = (set(ELEMENT_LESS_FLAGS) | set(ELEMENT_FLAGS) | set(PATHLESS_FLAGS)
                  | set(NOT_ELEMENT_LESS)) - {'metadata'}
    assert sorted(_file_specific_dests() - classified) == ['metadata']


def test_no_table_names_a_flag_the_parser_lacks():
    from reveal.cli.parser import create_argument_parser
    from reveal.cli.routing import ELEMENT_FLAGS, ELEMENT_LESS_FLAGS
    parser = create_argument_parser('')
    dests = {a.dest for a in parser._actions}
    spellings = {opt for a in parser._actions for opt in a.option_strings}
    for table in (ELEMENT_LESS_FLAGS, ELEMENT_FLAGS):
        assert [d for d in table if d not in dests] == []
        assert [s for s in table.values() if s not in spellings] == []
    assert [d for d in NOT_ELEMENT_LESS if d not in dests] == []
