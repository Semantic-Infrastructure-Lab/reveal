#!/usr/bin/env python3
"""Ratchet: the first screen teaches no retired spelling (BACK-2196).

Retired spellings still run and print a "replaced by" note, so the executable-docs gate cannot see a
README that teaches them. This reads the one ``RETIREMENTS`` table (reveal/cli/invocation.py) and fails
when a teaching surface names a retired spelling outside a sentence that says it is retired:

- ``README.md`` and ``ROADMAP.md`` (minus its release history),
- the first section of ``reveal/docs/AGENT_HELP.md`` (everything before "Common Tasks"),
- ``help://quick`` and every ``help://examples/<task>`` recipe.

A new ``RETIREMENTS`` row is covered the day it lands: the patterns are derived from the key's kind
(``subcommand:``, ``scheme:``, ``param:``, ``value:``, ``flag:``, ``target:``). Spellings that are due
to retire but have no row yet (``hotspots``) join when their rows land (BACK-2149). tests/test_retired_names_ratchet_back2196.py holds the positive controls.

Run:
    python scripts/check_retired_names.py        # exits 1 and names each line that teaches one
"""
import re
import shlex
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reveal.adapters.help import HelpAdapter  # noqa: E402
from reveal.cli.invocation import RETIREMENTS  # noqa: E402

# A unit that says the spelling is retired, replaced or renamed may name it. A table row counts with its
# header row, so a "Replaces" column may list old names.
REPLACED_BY_CONTEXT = re.compile(r'retired|retiring|deprecated|replaced|replaces|renamed|\(was\b|\bwas:|formerly|instead of|\bnote:',
                                 re.IGNORECASE)

LIST_ITEM = re.compile(r'\s*(?:[-*+]|\d+\.)\s')

# `--check` / `--lint` are retired for the file route only: `reveal ssl://host --check`,
# `reveal @hosts.txt --check` and `reveal --stdin --check` are the live spellings.
FILE_ROUTE_CHECK = re.compile(r"reveal\s+(?!@|-|\S*://)[^\s|'\"]+\s[^|\n]*--(?:check|lint)(?![\w-])")
# `reveal health` takes ops targets; a plain path (code) is `reveal check`'s. `.conf` stays an ops target.
HEALTH_ARG = re.compile(r"reveal\s+health\b([^|\n#]*)")
def _outline_names_a_code_element(line):
    from reveal.cli.invocation import Invocation
    from reveal.cli.parser import create_argument_parser
    from reveal.registry import get_markdown_extensions

    if '--outline' not in line:
        return False
    for match in re.finditer(r'\breveal\s+([^`\n]+)', line):
        lexer = shlex.shlex(match[1], posix=True, punctuation_chars='|;')
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            continue  # Prose with an unmatched quote is not a command example.
        end = next((i for i, token in enumerate(tokens) if token in {'|', ';'}), len(tokens))
        invocation = Invocation.parse(['reveal', *tokens[:end]])
        if invocation.command is not None:
            continue
        parser = create_argument_parser('', full_help=False)
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            try:
                args = parser.parse_args(invocation.argv)
            except SystemExit:
                continue  # Only accepted path-form invocations establish this context.
        if (args.outline and args.path and args.element
                and Path(args.path).suffix.lower() not in get_markdown_extensions()):
            return True
    return False


def _health_names_a_code_path(line):
    match = HEALTH_ARG.search(line)
    if not match:
        return False
    for token in match.group(1).split():
        if token.startswith(('-', '[', '<')) or '://' in token or token.endswith('.conf'):  # a flag, a placeholder, an ops target
            continue
        return True
    return False


def _patterns(key):
    """Regexes (or predicates) that find the retired spelling *key* in a line of teaching text."""
    kind, _, rest = key.partition(':')
    if kind == 'subcommand':
        # `reveal review`, and the bare backticked name a prose list uses (`review` 0 pass, 1 findings)
        return [re.compile(rf'(?<![\w/.-])reveal\s+{re.escape(rest)}\b(?!://)'),
                re.compile(rf'(?<![\w`]){{1}}`{re.escape(rest)}`(?![\w`:/])')]
    if kind == 'scheme':
        return [re.compile(rf'(?<![\w-]){re.escape(rest)}://')]
    if kind == 'param':
        scheme, _, param = rest.partition('.')
        return [re.compile(rf"{re.escape(scheme)}://[^\s'\"`]*[?&]{re.escape(param)}(?![\w-])"),
                re.compile(rf'reveal\s+{re.escape(scheme)}\b[^\n`|]*\s--{re.escape(param)}(?![\w-])')]
    if kind == 'value':
        scheme, _, pair = rest.partition('.')
        param, _, value = pair.partition('=')
        return [re.compile(rf"{re.escape(scheme)}://[^\s'\"`]*[?&]{re.escape(param)}={re.escape(value)}\b")]
    if kind == 'flag':
        if key == 'flag:--check':
            return [FILE_ROUTE_CHECK]
        return [re.compile(rf'(?<![\w-]){re.escape(rest)}(?![\w-])')]
    if kind == 'target' and key == 'target:health.code':
        return [_health_names_a_code_path]
    if kind == 'target' and key == 'target:nav.outline':
        return [_outline_names_a_code_element]
    return []


def _sample(key):
    """One line that spells *key* the way a README would, for the positive control."""
    kind, _, rest = key.partition(':')
    if kind == 'subcommand':
        return f'reveal {rest} src/'
    if kind == 'scheme':
        return f'reveal {rest}://src/'
    if kind == 'param':
        scheme, _, param = rest.partition('.')
        return f"reveal '{scheme}://src/?{param}=x'"
    if kind == 'value':
        scheme, _, pair = rest.partition('.')
        param, _, value = pair.partition('=')
        return f"reveal '{scheme}://src/?{param}={value}'"
    if kind == 'flag':
        return f'reveal src/app.py {rest}'
    if key == 'target:health.code':
        return 'reveal health ./src'
    if key == 'target:nav.outline':
        return 'reveal app.py work --outline'
    raise AssertionError(f'no sample for {key}')


def _matches(pattern, line):
    return pattern(line) if callable(pattern) else bool(pattern.search(line))


def _units(text):
    """(line number, the unit it sits in, the line): a fenced line or a table row stands alone, prose is
    judged by its whole paragraph, because a "replaced by" sentence wraps across lines."""
    lines = text.split('\n')
    out, fence, i, header = [], False, 0, ''
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith('```'):
            fence = not fence
            i += 1
        elif not fence and line.lstrip().startswith('|'):
            header = header if i and lines[i - 1].lstrip().startswith('|') else line
            out.append((i + 1, f'{header}\n{line}', line))
            i += 1
        elif fence or not line.strip():
            out.append((i + 1, line, line))
            i += 1
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not lines[j].lstrip().startswith(('```', '|')):
                j += 1
            # a list item is its own unit: its neighbours' "retired" says nothing about it
            starts = [k for k in range(i, j) if k == i or LIST_ITEM.match(lines[k])] + [j]
            for a, b in zip(starts, starts[1:]):
                block = '\n'.join(lines[a:b])
                out.extend((k + 1, block, lines[k]) for k in range(a, b))
            i = j
    return out


def scan(text, table=None):
    """Every (line number, key, line) where *text* teaches a retired spelling."""
    table = RETIREMENTS if table is None else table
    hits = []
    for number, unit, line in _units(text):
        if REPLACED_BY_CONTEXT.search(unit):
            continue
        for key in table:
            if any(_matches(p, line) for p in _patterns(key)):
                hits.append((number, key, line.strip()[:140]))
    return hits


# --- the surfaces --------------------------------------------------------------------------

def _read(name):
    return (ROOT / name).read_text(encoding='utf-8')


def _agent_help_first_section():
    head, sep, _ = _read('reveal/docs/AGENT_HELP.md').partition('\n## Common Tasks')
    assert sep, 'AGENT_HELP.md lost its "Common Tasks" heading, the first section has no end'
    return head


def _roadmap_without_release_history():
    """The ROADMAP minus "What We've Shipped": a release entry names what shipped at the time."""
    head, sep, rest = _read('ROADMAP.md').partition("\n## What We've Shipped")
    assert sep, "ROADMAP.md lost its \"What We've Shipped\" section (release prep and V011 need it)"
    return head + '\n## ' + rest.partition('\n## ')[2]


def _help_quick():
    out = subprocess.run([sys.executable, '-m', 'reveal', 'help://quick'], capture_output=True, text=True,
                         encoding='utf-8', cwd=ROOT, check=False)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _example_recipes():
    adapter = HelpAdapter()
    lines = []
    for task in adapter.get_element('examples')['available_tasks']:
        for recipe in adapter.get_element(f'examples/{task}')['recipes']:
            lines.append(f"{recipe['query']}  # {recipe.get('description', '')}")
    return '\n'.join(lines)


SURFACES = {
    'README.md': lambda: _read('README.md'),
    'ROADMAP.md (without release history)': _roadmap_without_release_history,
    'AGENT_HELP.md (first section)': _agent_help_first_section,
    'help://quick': _help_quick,
    'help://examples': _example_recipes,
}


def surface_hits(name):
    """The (line number, key, line) hits of one surface; an empty surface is an error, not a pass."""
    text = SURFACES[name]()
    assert len(text) > 500, f'{name} came back empty'
    return scan(text)


def main():
    failed = 0
    for name in SURFACES:
        hits = surface_hits(name)
        for number, key, line in hits:
            print(f'{name}: line {number}: {key}: {line}')
        failed += len(hits)
    if failed:
        print(f'\n{failed} line(s) teach a retired spelling: name it only in a "replaced by" sentence '
              '(or use its replacement). See scripts/check_retired_names.py.')
        return 1
    print(f'retired-names ratchet OK ({len(RETIREMENTS)} retired spellings, {len(SURFACES)} surfaces)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
