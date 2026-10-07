"""BACK-1699: every install command reveal prints or documents names a real package and extra.

The extras are the keys of ``[project.optional-dependencies]`` in pyproject.toml. This guard
reads that table and scans the install commands (``pip install``, ``pip3 install``,
``python -m pip install``, ``uv pip install``, ``pipx install``) in reveal/'s source and data
files (string literals, docstrings and comments alike), the bundled docs (help topics,
AGENT_HELP.md, adapter guides), pyproject.toml's own comments and the root *.md files
(README.md, INSTALL.md, ...; CHANGELOG.md is history and is not scanned). It fails on:

  (a) our own package spelled as anything but ``reveal-cli`` (``reveal[whois]``, ``reveal-tool``);
  (b) ``reveal-cli[x]`` (or a local ``.[x]``) whose ``x`` is not a defined extra;
  (c) a bare install of a package that is the sole content of a defined extra
      (``pip install dnspython`` where ``reveal-cli[dns]`` exists).

Third-party packages that no extra provides (beautifulsoup4 for a broken base install,
tree-sitter grammars, the user's own packages in python:// doctor hints) are not checked.
Templated tokens (``{pkg_name}``, ``<extra>``, ``${VERSION}``) are skipped.
"""

import re
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # Python 3.10: tomli is a base dependency there (pyproject.toml)
    tomllib = pytest.importorskip('tomli', reason='no tomllib/tomli to read pyproject.toml')

pytestmark = pytest.mark.conformance

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / 'pyproject.toml'
OUR_DIST = 'reveal-cli'

# (repo-relative posix path, rule, canonical package name) -> reason. Keep it short and reviewed.
ALLOWLIST = {
    ('reveal/adapters/git/adapter.py', 'bare-extra-package', 'pygit2'):
        'reveal/adapters/git/* is owned by wave-9 agent A (BACK-1690); the replacement strings '
        'are in agent D\'s report. Drop this entry when they land.',
}

_INSTALL = re.compile(
    r'(?<![\w-])(?:pip3?|python3?\s+-m\s+pip|uv\s+pip|pipx)\s+install(?![\w-])')
_WORD = re.compile(r'[A-Za-z0-9._\-\[\],<>=!~+$/:@{}]+')
_NAME = re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[([^\]]*)\])?')
_TEMPLATE = re.compile(r'[{}$]|<[A-Za-z_-]+>')
# pip options whose value is the next token (that value is not a requirement)
_ARG_OPTIONS = {
    '-r', '--requirement', '-c', '--constraint', '-i', '--index-url', '--extra-index-url',
    '-f', '--find-links', '-t', '--target', '--prefix', '--root', '--src',
    '--upgrade-strategy', '--python', '--platform', '--python-version',
}


def _canon(name):
    """PEP 503 normalised project name."""
    return re.sub(r'[-_.]+', '-', name).lower()


def _optional_dependencies():
    with PYPROJECT.open('rb') as f:
        return tomllib.load(f)['project']['optional-dependencies']


def _sole_package_extras(extras):
    """{package: extra} for every extra that installs exactly one package (dev excluded)."""
    sole = {}
    for extra, reqs in extras.items():
        if extra != 'dev' and len(reqs) == 1:
            sole[_canon(_NAME.match(reqs[0]).group(1))] = extra
    return sole


def _commands(line):
    """The text after each install keyword in a line, up to the next install keyword."""
    matches = list(_INSTALL.finditer(line))
    for m, nxt in zip(matches, matches[1:] + [None]):
        yield line[m.end():nxt.start() if nxt else len(line)]


def _tokens(rest):
    """Shell-ish words after 'install' up to the end of the command: (text, quote char)."""
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch.isspace():
            i += 1
        elif ch in '"\'':
            end = rest.find(ch, i + 1)
            if end < 0:  # an unmatched quote closes the enclosing literal: command over
                return
            yield rest[i + 1:end], ch
            i = end + 1
        else:
            m = _WORD.match(rest, i)
            if not m:  # backtick, ')', '#', ';', '|', '&', a '\n' escape ...: command over
                return
            yield m.group(), ''
            i = m.end()


def _requirements(rest):
    """The requirement-like tokens of one install command (options and their values skipped)."""
    skip_value = False
    for text, quote in _tokens(rest):
        if skip_value:
            skip_value = False
            continue
        if not quote and text.startswith('-'):
            if text in ('-e', '--editable'):
                continue  # its value is a requirement (a local path, maybe with extras)
            skip_value = text.split('=', 1)[0] in _ARG_OPTIONS and '=' not in text
            continue
        yield text, quote


def check_command(rest, extras, sole):
    """Findings for one install command: list of (rule, canonical name, token, message)."""
    findings = []
    for text, _quote in _requirements(rest):
        if _TEMPLATE.search(text) or '://' in text:
            continue
        if text.startswith(('.', '/')):  # local checkout: '.', '.[dev]', './reveal'
            m = re.search(r'\[([^\]]*)\]', text)
            name, wanted = OUR_DIST, (m.group(1) if m else None)
        else:
            m = _NAME.match(text)
            if not m:
                continue
            name, wanted = _canon(m.group(1)), m.group(2)
        if name != OUR_DIST and (name == 'reveal' or name.startswith('reveal-')):
            findings.append(('wrong-dist-name', name, text,
                             f'our distribution is {OUR_DIST!r}, not {m.group(1)!r}'))
            continue
        if name == OUR_DIST and wanted:
            unknown = [e.strip() for e in wanted.split(',') if e.strip() not in extras]
            if unknown:
                findings.append(('unknown-extra', name, text,
                                 f'extra(s) {unknown} not in [project.optional-dependencies] '
                                 f'({sorted(extras)})'))
        elif name in sole:
            findings.append(('bare-extra-package', name, text,
                             f'{name} is the {sole[name]!r} extra: '
                             f'pip install "{OUR_DIST}[{sole[name]}]"'))
    return findings


def _scanned_files():
    files = [p for p in ROOT.glob('*.md') if p.name != 'CHANGELOG.md']
    files.append(PYPROJECT)
    for pattern in ('*.py', '*.md', '*.yaml', '*.yml'):
        files.extend((ROOT / 'reveal').rglob(pattern))
    return sorted(set(files))


def _scan():
    """(commands seen, findings) over the whole scanned tree; findings are dicts."""
    extras = _optional_dependencies()
    sole = _sole_package_extras(extras)
    commands, findings = [], []
    for path in _scanned_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding='utf-8')
        for lineno, line in enumerate(text.split('\n'), 1):
            for rest in _commands(line):
                commands.append((rel, lineno, rest))
                for rule, name, token, message in check_command(rest, extras, sole):
                    findings.append({'path': rel, 'line': lineno, 'rule': rule,
                                     'name': name, 'token': token, 'message': message})
    return commands, findings


def _allowlisted(finding):
    return (finding['path'], finding['rule'], finding['name']) in ALLOWLIST


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

def test_every_install_hint_names_reveal_cli_and_a_defined_extra():
    commands, findings = _scan()
    # positive control: the scan sees the tree (a zero here would make the guard vacuous)
    assert len(commands) >= 50, f'only {len(commands)} install commands found under {ROOT}'
    assert any(rel == 'INSTALL.md' and 'reveal-cli[git]' in rest for rel, _, rest in commands)
    bad = [f for f in findings if not _allowlisted(f)]
    assert not bad, 'install hints that name a wrong package or extra:\n' + '\n'.join(
        f"  {f['path']}:{f['line']}: {f['rule']}: {f['token']!r}: {f['message']}" for f in bad)


def test_allowlist_entries_are_still_needed():
    """A fixed site must leave the allowlist, or the allowlist hides the next regression."""
    _, findings = _scan()
    used = {(f['path'], f['rule'], f['name']) for f in findings}
    stale = sorted(set(ALLOWLIST) - used)
    assert not stale, f'allowlist entries that match nothing (remove them): {stale}'


# ---------------------------------------------------------------------------
# The scanner on known lines (negative and positive controls)
# ---------------------------------------------------------------------------

EXTRAS = {'git': ['pygit2>=1.14.0'], 'dns': ['dnspython>=2.0.0'], 'whois': ['python-whois>=0.9.0'],
          'mcp': ['mcp>=2.0.0'], 'dev': ['pytest>=7.0', 'pygit2>=1.14.0'], 'treesitter': []}
SOLE = _sole_package_extras(EXTRAS)


def _rules(line):
    commands = list(_commands(line))
    assert commands, line
    return [(rule, token) for rest in commands
            for rule, _, token, _ in check_command(rest, EXTRAS, SOLE)]


def test_sole_package_map_skips_dev_and_empty_extras():
    assert SOLE == {'pygit2': 'git', 'dnspython': 'dns', 'python-whois': 'whois', 'mcp': 'mcp'}


@pytest.mark.parametrize('line, expected', [
    ('whois: WHOIS data (optional: pip install reveal[whois])',
     [('wrong-dist-name', 'reveal[whois]')]),
    ('        run: pip install reveal-tool', [('wrong-dist-name', 'reveal-tool')]),
    ('RUN pip install reveal-tool dnspython',
     [('wrong-dist-name', 'reveal-tool'), ('bare-extra-package', 'dnspython')]),
    ('pip install "reveal-cli[git,nosuch]"', [('unknown-extra', 'reveal-cli[git,nosuch]')]),
    ('pip install -e ".[all]"', [('unknown-extra', '.[all]')]),
    ('"Install with: pip install dnspython")', [('bare-extra-package', 'dnspython')]),
    ('"Alternative: pip install pygit2>=1.14.0\\n\\n"', [('bare-extra-package', 'pygit2>=1.14.0')]),
    ('pip install "mcp>=2.0.0"', [('bare-extra-package', 'mcp>=2.0.0')]),
    ('python -m pip install Python_Whois', [('bare-extra-package', 'Python_Whois')]),
    # two commands on one line: each is checked once, the second is not re-read by the first
    ("'Install: pip install reveal-cli[dns] OR pip install dnspython'",
     [('bare-extra-package', 'dnspython')]),
])
def test_scanner_flags_wrong_installs(line, expected):
    assert _rules(line) == expected


@pytest.mark.parametrize('line', [
    'pip install reveal-cli',
    'pip install --upgrade reveal-cli',
    'pip install "reveal-cli[git,dns]"            # several',
    'pip install reveal_cli[git]',  # PEP 503: the same distribution
    'pip install -e ".[dev]"',
    'pip install -e .',
    'pip install reveal-cli[treesitter]',  # a defined (empty) extra
    'pip install beautifulsoup4',  # base dependency, no extra
    'pip install -r requirements.txt',
    'pip install --index-url https://test.pypi.org/simple/ reveal-cli',
    "f\"pip install {pkg_name} --force-reinstall\",",
    'Install one with `pip install "reveal-cli[<extra>]"`, several with',
    'pip3 install reveal-cli==${VERSION} --quiet',
    'pip install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git@main',
    '**Note:** PyPI releases can\'t be deleted, only "yanked" (hidden from pip install):',
    'pip install reveal-cli  # then: pygit2 comes with reveal-cli[git]',  # '#' ends the command
])
def test_scanner_accepts_correct_installs(line):
    assert _rules(line) == []
