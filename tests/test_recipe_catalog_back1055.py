"""One home for the help://examples task catalog (BACK-1055 slice 4).

`_EXAMPLE_RECIPES` (reveal/adapters/help.py) owns the task names and each task's one-line
description; `help://examples` lists the names and `help://examples/<task>` prints the
description as its **Task:** line. AGENT_HELP.md restates the catalog as a fenced block of
`reveal help://examples/<task> --format=json  # <description>` lines; that block is checked
against the declaration here: every task listed once, each comment the task's own
description. Every concrete `help://examples/<name>` a doc or the package source names must
also be a task, so a renamed or removed task cannot leave a dead pointer behind.

What this does not check: the recipes' queries against AGENT_HELP's own "Common Tasks"
sections. Those are a separate, larger taxonomy (39 task headings vs 11 recipe tasks), and
only 22 of the 71 recipe queries appear in AGENT_HELP verbatim, so there is no shared fact to
agree on there. Whether a recipe does what it says is BACK-1611 (tests/test_example_recipes_run.py).
"""
import re
from pathlib import Path

from reveal.adapters.help import _EXAMPLE_RECIPES

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'reveal' / 'docs'
AGENT_HELP = DOCS / 'AGENT_HELP.md'

FENCE = re.compile(r'```(?:bash|sh|shell)\n(.*?)```', re.S)
CATALOG_LINE = re.compile(
    r"^reveal '?help://examples/([a-z][a-z0-9-]*)'?(?: --format[= ]json)?\s+#\s*(.+?)\s*$",
    re.MULTILINE)
NAMED_TASK = re.compile(r'help://examples/([a-z][a-z0-9-]*)')


def _doc_catalog(markdown):
    """[(task, comment)] for every commented `reveal help://examples/<task>` line in a fence."""
    rows = []
    for block in FENCE.findall(markdown):
        rows.extend(CATALOG_LINE.findall(block))
    return rows


def _catalog_problems(recipes, rows):
    problems = []
    names = [task for task, _ in rows]
    for task in sorted({t for t in names if names.count(t) > 1}):
        problems.append(f'{task}: listed {names.count(task)} times in AGENT_HELP.md')
    missing = sorted(set(recipes) - set(names))
    if missing:
        problems.append(f'AGENT_HELP.md does not list tasks {missing}')
    for task, comment in rows:
        if task not in recipes:
            problems.append(f'{task}: AGENT_HELP.md lists a task help://examples does not have')
        elif comment != recipes[task]['description']:
            problems.append(f'{task}: AGENT_HELP.md says {comment!r}, the task says '
                            f'{recipes[task]["description"]!r}')
    return problems


def test_agent_help_catalog_agrees_with_the_recipes():
    rows = _doc_catalog(AGENT_HELP.read_text(encoding='utf-8'))
    problems = _catalog_problems(_EXAMPLE_RECIPES, rows)
    assert not problems, '\n'.join(problems)
    assert len(rows) == len(_EXAMPLE_RECIPES)


def test_catalog_gate_bites():
    """Negative control: a dropped row, a renamed task, a drifted comment and a duplicate
    are each reported; the unchanged rows are not."""
    rows = [(task, group['description']) for task, group in _EXAMPLE_RECIPES.items()]
    assert _catalog_problems(_EXAMPLE_RECIPES, rows) == []
    dropped = [r for r in rows if r[0] != 'data']
    assert any("['data']" in p for p in _catalog_problems(_EXAMPLE_RECIPES, dropped))
    renamed = [('database' if t == 'data' else t, c) for t, c in rows]
    assert any(p.startswith('database:') for p in _catalog_problems(_EXAMPLE_RECIPES, renamed))
    drifted = [(t, 'SQLite recipes' if t == 'data' else c) for t, c in rows]
    assert [p.split(':')[0] for p in _catalog_problems(_EXAMPLE_RECIPES, drifted)] == ['data']
    assert any('2 times' in p for p in _catalog_problems(_EXAMPLE_RECIPES, rows + rows[:1]))


def test_catalog_parser_reads_the_doc_forms():
    block = ("```bash\n"
             "reveal help://examples/quality --format=json   # Code quality\n"
             "reveal 'help://examples/<task>'    # a template, not a task\n"
             "reveal help://examples                # the bare listing\n"
             "```\n")
    assert _doc_catalog(block) == [('quality', 'Code quality')]


def _named_task_sources():
    yield from sorted((ROOT / 'reveal').rglob('*.py'))
    yield from sorted(DOCS.rglob('*.md'))
    yield ROOT / 'README.md'


def _unknown_task_references(recipes, sources):
    """`file: name` for every concrete help://examples/<name> that is not a task."""
    unknown = []
    for path in sources:
        for name in NAMED_TASK.findall(path.read_text(encoding='utf-8')):
            if name not in recipes:
                unknown.append(f'{path.as_posix()}: {name}')
    return unknown


def test_every_named_example_task_exists():
    sources = list(_named_task_sources())
    assert AGENT_HELP in sources and ROOT / 'reveal' / 'adapters' / 'help.py' in sources
    assert not _unknown_task_references(_EXAMPLE_RECIPES, sources)


def test_named_task_gate_bites(tmp_path):
    """Negative control: a pointer at a task that was renamed away is reported; templates
    (`<task>`) and real tasks are not."""
    doc = tmp_path / 'README.md'
    doc.write_text("reveal help://examples/quality\nreveal 'help://examples/<task>'\n"
                   "reveal help://examples/sql-security\n", encoding='utf-8')
    found = _unknown_task_references(_EXAMPLE_RECIPES, [doc])
    assert len(found) == 1 and found[0].endswith('README.md: sql-security')
