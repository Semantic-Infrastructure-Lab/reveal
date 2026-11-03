"""External rule discoveries belong to a host request, not the host process."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


_DRIVER = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

from reveal import api, mcp_server
from reveal.rules import RuleRegistry

root, host, operation, location = Path(sys.argv[1]), *sys.argv[2:5]
rule_root = root / '.reveal' if location == 'project' else root / 'data' / 'reveal'
rule = rule_root / 'rules' / 'custom' / 'Q901.py'

def write(message):
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text(
        'from reveal.rules.base import BaseRule, Severity, RulePrefix, RuleScope\n'
        'class Q901(BaseRule):\n code="Q901"\n message=' + repr(message) + '\n'
        ' category=RulePrefix.B\n severity=Severity.HIGH\n file_patterns=["*.py"]\n'
        ' scope=RuleScope.FILE\n def check(self,file_path,structure,content):\n'
        '  return [self.create_detection(file_path,1)]\n', encoding='utf-8')

def snapshot():
    target = str(root / 'f.py')
    if host == 'mcp':
        text = mcp_server.reveal_check(target)
        return 'custom_old' in text, 'custom_new' in text
    rows = api.check(target)
    messages = [row.message for row in rows if row.rule_code == 'Q901']
    return 'custom_old' in messages, any(message.startswith('custom_new') for message in messages)

if operation != 'added':
    write('custom_old')
before = snapshot()
builtin = RuleRegistry.get_rule('B001')
if operation == 'added':
    write('custom_new')
elif operation == 'edited':
    write('custom_new_and_longer')
elif operation == 'same_stat':
    old_stat = rule.stat()
    write('custom_new')
    # Equal byte count and timestamps: don't let Python's bytecode cache hide the edit.
    os.utime(rule, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
elif operation == 'deleted':
    rule.unlink()
after = snapshot()
assert RuleRegistry.get_rule('B001') is builtin
# A new CLI process is the one-shot reference; no host cache survives into it.
cli = subprocess.run([sys.executable, '-m', 'reveal', 'check', str(root / 'f.py')],
                     text=True, encoding='utf-8', capture_output=True, timeout=30)
assert cli.returncode in (0, 1), cli.stderr
fresh = ('custom_old' in cli.stdout, 'custom_new' in cli.stdout)
print('RESULT_JSON ' + json.dumps({'before': before, 'after': after, 'fresh': fresh}))
'''


@pytest.mark.parametrize('host', ['api', 'mcp'])
@pytest.mark.parametrize('location', ['project', 'user'])
@pytest.mark.parametrize('operation', ['added', 'edited', 'same_stat', 'deleted', 'unchanged'])
def test_custom_rules_follow_host_requests(tmp_path, host, location, operation):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    (tmp_path / 'f.py').write_text('VALUE = 1\n', encoding='utf-8')
    (tmp_path / 'data' / 'reveal' / 'rules').mkdir(parents=True)
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(repo), REVEAL_DISK_CACHE='0',
               XDG_DATA_HOME=str(tmp_path / 'data'), XDG_CONFIG_HOME=str(tmp_path / 'config'))
    result = subprocess.run(
        [sys.executable, '-c', _DRIVER, str(tmp_path), host, operation, location],
        cwd=tmp_path, env=env, text=True, encoding='utf-8', capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    row = json.loads(next(line.removeprefix('RESULT_JSON ') for line in result.stdout.splitlines()
                          if line.startswith('RESULT_JSON ')))
    assert row['before'] == ([False, False] if operation == 'added' else [True, False])
    expected = [True, False] if operation == 'unchanged' else [False, operation != 'deleted']
    assert row['fresh'] == expected, 'one-shot CLI must see the current rule source'
    assert row['after'] == expected, 'long-lived host retained stale custom-rule discovery'


def test_nested_host_reuses_rules_and_builtin_discovery(tmp_path, monkeypatch):
    """External discovery is once per outer request; package discovery stays reusable."""
    from reveal import api
    from reveal.rules import RuleRegistry
    from reveal.utils.request_cache import host_request

    (tmp_path / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    target = tmp_path / 'f.py'
    target.write_text('VALUE = 1\n', encoding='utf-8')
    (tmp_path / 'data' / 'reveal' / 'rules').mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    # Restore even private process state after this in-process preservation control.
    for attr in ('_rules', '_rules_by_code', '_discovered', '_built_in_rules'):
        if hasattr(RuleRegistry, attr):
            monkeypatch.setattr(RuleRegistry, attr, getattr(RuleRegistry, attr))
    counts = {'builtin': 0, 'user': 0, 'project': 0}

    def counted(kind, method):
        def discover(cls, *args):
            counts[kind] += 1
            return method(*args)
        return classmethod(discover)

    for kind, name in [('builtin', '_discover_built_in_rules'),
                       ('user', '_discover_user_rules'), ('project', '_discover_project_rules')]:
        monkeypatch.setattr(RuleRegistry, name, counted(kind, getattr(RuleRegistry, name)))
    RuleRegistry.discover(force=True)
    builtin = RuleRegistry.get_rule('B001')
    with host_request():
        api.check(str(target))
        first_rules = RuleRegistry._rules
        first_codes = RuleRegistry.effective_codes()
        with host_request():
            api.check(str(target))
            assert RuleRegistry._rules is first_rules
            assert RuleRegistry.effective_codes() is first_codes
        assert counts == {'builtin': 1, 'user': 2, 'project': 2}
    api.check(str(target))
    assert counts == {'builtin': 1, 'user': 3, 'project': 3}
    assert RuleRegistry.get_rule('B001') is builtin
    RuleRegistry.discover(force=True)
    assert counts == {'builtin': 2, 'user': 4, 'project': 4}


def test_external_reload_preserves_module_metadata_and_source_encoding(tmp_path, monkeypatch):
    """Source compilation still provides the module lookup dataclasses/typing require."""
    from typing import get_type_hints
    from reveal.rules import RuleRegistry

    plugin = tmp_path / 'Q2473.py'
    plugin.write_bytes(
        b'# coding: latin-1\nfrom __future__ import annotations\n'
        b'import sys\nfrom dataclasses import dataclass\n'
        b'@dataclass\nclass Payload:\n label: str = "caf\xe9"\n'
        b'def identity(value: Payload) -> Payload:\n return value\n'
        b'self_module = sys.modules[__name__]\n'
    )
    name = 'reveal._external_rules.test.Q2473'
    monkeypatch.setitem(sys.modules, name, None)
    module = RuleRegistry._load_module_from_path(plugin, name)
    assert module is sys.modules[name] is module.self_module
    assert Path(module.__file__).resolve() == plugin.resolve()
    assert Path(module.__spec__.origin).resolve() == plugin.resolve()
    assert module.__loader__ is module.__spec__.loader
    assert module.__package__ == 'reveal._external_rules.test'
    assert module.Payload().label == 'café'
    assert get_type_hints(module.identity) == {'value': module.Payload, 'return': module.Payload}
