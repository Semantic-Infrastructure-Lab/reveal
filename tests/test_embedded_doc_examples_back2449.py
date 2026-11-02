"""Inventory embedded Markdown commands without qualifying them for execution."""
import shlex
from pathlib import Path

import pytest

import test_example_recipes_run as recipes

pytestmark = pytest.mark.contract

EMBEDDED = '#embedded-md'
README = '../../README.md' + EMBEDDED
README_COMMANDS = (
    "reveal 'ast://src/?type=function'",
    "reveal 'calls://src/?callers=my_fn'",
    'reveal imports://src/',
    "reveal 'git://.?message~=fix'",
    "reveal 'claude://sessions/?search=auth-refactor'",
    "reveal 'codex://sessions/?search=auth-refactor'",
    "reveal docs/ --grep 'decision'",
    'reveal sqlite:///app.db',
    'reveal env://',
    'reveal help://adapters',
    'reveal help://quick',
    "reveal 'help://schemas/<adapter>' --format=json",
)


def _write(docs, source, text):
    path = docs / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.mark.parametrize('command', README_COMMANDS)
def test_readme_embedded_examples_keep_text_tokens_and_distinct_provenance(command):
    readme = Path(recipes.__file__).parents[1] / 'README.md'
    assert f'`{command}`' in readme.read_text(encoding='utf-8')
    rows = [row for row in recipes._documented_commands() if row[0] == README]
    assert (README, command, shlex.split(command), False) in rows
    assert 'embedded Markdown' in recipes._source_cohort_reason(README, shlex.split(command))


@pytest.mark.parametrize('fence', ['md', 'markdown'])
def test_embedded_table_and_list_examples_are_bounded_and_unqualified(tmp_path, fence):
    _write(tmp_path, 'AGENT_HELP.md', f'''```{fence}
| Need | Examples |
|------|----------|
| Map | `reveal overview .` and `reveal env://` |
1. `reveal help://quick` — compact router
2) `reveal 'help://schemas/<adapter>' --format=json` — template
- `reveal src/ --top 1`
* `reveal app.py ghost # not valid`
```
''')
    rows = list(recipes._documented_commands(tmp_path))
    assert [(source, shlex.join(tokens), failing) for source, _, tokens, failing in rows] == [
        ('AGENT_HELP.md' + EMBEDDED, 'reveal overview .', False),
        ('AGENT_HELP.md' + EMBEDDED, 'reveal env://', False),
        ('AGENT_HELP.md' + EMBEDDED, 'reveal help://quick', False),
        ('AGENT_HELP.md' + EMBEDDED, "reveal 'help://schemas/<adapter>' --format=json", False),
        ('AGENT_HELP.md' + EMBEDDED, 'reveal src/ --top 1', False),
        ('AGENT_HELP.md' + EMBEDDED, 'reveal app.py ghost', True),
    ]
    assert all(recipes._source_cohort_reason(source, tokens)
               for source, _, tokens, _ in rows)
    params = recipes._named_fixture_commands(tmp_path)
    assert params and all(p.marks for p in params)
    assert all('embedded Markdown' in mark.kwargs['reason'] or 'doc shows it failing' in mark.kwargs['reason']
               for p in params for mark in p.marks)


def test_prose_noncommands_and_other_fences_are_not_embedded_commands(tmp_path):
    _write(tmp_path, 'AGENT_HELP.md', '''An inline prose mention: `reveal help://quick`.
```md
Regular prose mentions `reveal help://quick` without instructing a step.
1. Explain `ast://src/` and `echo reveal help://quick`.
2. `reveal` is the program name.
3. ``reveal help://quick`` is outside the single-backtick grammar.
4. `reveal # explanation` is a program name with a shell comment.
| Need | `ast://` | `echo reveal env://` |
reveal env://
```
```python
1. `reveal help://quick`
```
```text
| Need | `reveal env://` |
```
''')
    assert list(recipes._documented_commands(tmp_path)) == []


@pytest.mark.parametrize('fence', ['````', '~~~'])
def test_markdown_fence_literal_inside_other_fence_is_not_an_instruction(tmp_path, fence):
    _write(tmp_path, 'AGENT_HELP.md', f'''{fence}text
```md
1. `reveal help://quick`
```
{fence}
''')
    assert list(recipes._documented_commands(tmp_path)) == []


def test_unclosed_inline_command_quote_fails_clearly_without_partial_tokens(tmp_path):
    _write(tmp_path, 'AGENT_HELP.md', '```md\n1. `reveal "unterminated`\n```\n')
    with pytest.raises(AssertionError, match='Unterminated documented command'):
        list(recipes._documented_commands(tmp_path))


def test_embedded_identity_cannot_borrow_shell_qualification(tmp_path):
    docs = tmp_path / 'reveal' / 'docs'
    _write(docs, '../../README.md', '''```md
1. `reveal overview .`
```
''')
    rows = list(recipes._documented_commands(docs))
    assert len(rows) == 1 and rows[0][0] == README
    assert recipes._source_cohort_reason('../../README.md', ['reveal', 'overview', '.']) is None
    assert 'embedded Markdown' in recipes._source_cohort_reason(rows[0][0], rows[0][2])
    assert recipes._named_fixture_commands(docs)[0].marks


def test_embedded_commands_do_not_shadow_later_legacy_shell_examples(tmp_path):
    _write(tmp_path, 'AGENT_HELP.md', '```md\n1. `reveal app.py`\n```\n')
    _write(tmp_path, 'guides/LATER.md', '```bash\nreveal app.py\n```\n')
    rows = list(recipes._documented_commands(tmp_path))
    assert [row[0] for row in rows] == ['guides/LATER.md', 'AGENT_HELP.md' + EMBEDDED]
    [param] = recipes._named_fixture_commands(tmp_path)
    assert param.id == 'guides/LATER.md:reveal app.py' and not param.marks


def test_existing_shell_inventory_and_execution_eligibility_remain_identical(monkeypatch):
    rows = list(recipes._documented_commands())
    shell_rows = [row for row in rows if not row[0].endswith(EMBEDDED)]
    assert len(rows) > len(shell_rows)
    named = recipes._named_fixture_commands()
    discovery = recipes._documentation_commands()
    monkeypatch.setattr(recipes, '_documented_commands', lambda docs=None: iter(shell_rows))
    prior_named = recipes._named_fixture_commands()
    prior_discovery = recipes._documentation_commands()
    by_query = {p.values: p for p in named}
    assert all(by_query[p.values] == p for p in prior_named)
    assert discovery[:len(prior_discovery)] == prior_discovery
    assert {p.values for p in named if not p.marks} == {p.values for p in prior_named if not p.marks}
    assert {p.values for p in discovery if not p.marks} == {p.values for p in prior_discovery if not p.marks}
    assert all(p.marks for p in discovery[len(prior_discovery):])
