"""MCP tool descriptions are what an agent reads before calling: their examples must run.

BACK-1611 item 7. Every literal `reveal_<tool>(...)` call quoted in a tool description is
executed against a small fixture and must not return an error sentinel; every tool it names
exists; every rule code or series quoted as an example for `select`/`ignore` exists.
"""
import ast
import asyncio
import re

import pytest

import reveal.mcp_server as mcp_server
from reveal.rules import RuleRegistry

PLACEHOLDER = re.compile(r'<|\.\.\.|my_fn')
TOOL_NAME = re.compile(r'\breveal_[a-z]+\b')
EXAMPLE_CODES = re.compile(r'(?:select|ignore):[^\n]*?e\.g\.,? ([^\n(]*)')


def _descriptions():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    return {tool.name: tool.description or '' for tool in tools}


def _calls(text):
    """Source of each `reveal_x(...)` call in `text`, parentheses balanced."""
    for match in re.finditer(r'\breveal_[a-z]+\(', text):
        depth, end = 0, match.end() - 1
        for index in range(end, len(text)):
            depth += (text[index] == '(') - (text[index] == ')')
            if depth == 0:
                yield text[match.start():index + 1]
                break


def _runnable_examples():
    seen = {}
    for text in _descriptions().values():
        for call in _calls(re.sub(r'\s*\n\s*', ' ', text)):
            if not PLACEHOLDER.search(call):
                seen[call] = None
    return sorted(seen)


def _evaluate(call, directory):
    node = ast.parse(call, mode='eval').body
    name = node.func.id

    def value(arg):
        if isinstance(arg, ast.Name):
            assert arg.id == 'dir', f'{call}: unknown name {arg.id}'
            return directory
        return ast.literal_eval(arg)

    args = [value(a) for a in node.args]
    kwargs = {k.arg: value(k.value) for k in node.keywords}
    return name, args, kwargs


@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text(
        'def process_order(order):\n    total = order["total"]\n    return total\n', encoding='utf-8')
    (tmp_path / 'notes.md').write_text('# Notes\n\nbody\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return str(tmp_path)


def test_example_inventory_is_not_vacuous():
    examples = _runnable_examples()
    assert len(examples) >= 4, examples
    assert any(e.startswith('reveal_nav(') for e in examples), examples


@pytest.mark.parametrize('call', _runnable_examples())
def test_description_example_runs(call, fixture_dir):
    name, args, kwargs = _evaluate(call, fixture_dir)
    result = getattr(mcp_server, name)(*args, **kwargs)
    assert not str(result).lstrip().startswith('[reveal error'), f'{call}: {str(result)[:200]}'
    assert str(result).strip(), f'{call}: printed nothing'


def test_every_tool_a_description_names_exists():
    descriptions = _descriptions()
    named = {n for text in descriptions.values() for n in TOOL_NAME.findall(text)}
    assert named - set(descriptions) == set(), named - set(descriptions)


def _unknown_codes(text, known):
    series = {code[0] for code in known}
    problems = []
    for chunk in EXAMPLE_CODES.findall(text):
        for token in re.findall(r"'([^']+)'", chunk):
            for code in token.split(','):
                code = code.strip()
                if code not in known and code not in series:
                    problems.append(code)
    return problems


def test_example_rule_codes_exist():
    known = {rule['code'] for rule in RuleRegistry.list_rules(include_internal=True)}
    descriptions = _descriptions()
    checked = [c for text in descriptions.values() for c in EXAMPLE_CODES.findall(text)]
    assert len(checked) >= 3, 'the rule-code example inventory went vacuous'
    assert not {n: _unknown_codes(t, known) for n, t in descriptions.items() if _unknown_codes(t, known)}


def test_docstring_gate_bites(fixture_dir):
    """Negative control: a bad flag and an invented rule code are each reported."""
    name, args, kwargs = _evaluate("reveal_nav('app.py', 'process_order', 'no_such_flag')", fixture_dir)
    assert str(getattr(mcp_server, name)(*args, **kwargs)).startswith('[reveal error')
    known = {rule['code'] for rule in RuleRegistry.list_rules(include_internal=True)}
    assert _unknown_codes("select: rules, e.g. 'B006,Z999'", known) == ['Z999']
