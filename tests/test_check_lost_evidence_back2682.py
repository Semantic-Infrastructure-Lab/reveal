"""check names the evidence it lost in ``meta.warnings``, as every other noun does (BACK-2682, BACK-2668).

``check`` exited 3 on a recovered or unreadable file, yet ``meta.warnings`` was empty: the files were only in
``files[].detail`` and a count, so a consumer reading the shared lost-evidence list (``utils.results.lost_evidence``)
saw a complete answer. A recovered C file and a notebook that is not JSON were both just ``status: warning``.
Now a recovered parse is ``parse_recovered``, a file the analyzer could not read is ``analysis_failed`` with
its cause, and a rule that raised is ``check_rules_failed``, on a directory and on a single file alike.

A configured rule module that did not load (BACK-2668, Scott 2026-11-17) was a ``plugin_warning`` only: check
printed "No issues found" and exited 0 while that rule checked nothing. It is now lost evidence too
(``check_rules_failed``, code ``rule_module_not_loaded``): incomplete, exit 3.
"""
import json
import os
import subprocess
import sys

import pytest

from reveal.utils.results import lost_evidence

pytestmark = pytest.mark.cli

OK_C = 'int ok(void) { return 1; }\n'
RECOVERED_C = 'int bad(void) { return (1; }\nint g(void) { return 2; }\n'
NOT_JSON = '{not json'


def _cli(root, *argv):
    """The real process, cwd at the project (project rules are discovered from the cwd)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(root.parent / 'xdg-config'),
               XDG_DATA_HOME=str(root.parent / 'xdg-data'))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=root, timeout=180)


def _project(root, files):
    root.mkdir(parents=True)
    (root / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _check(root, target='.'):
    result = _cli(root, 'check', target, '--format', 'json')
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def _lost(answer):
    return {w['type']: w for w in answer['meta']['warnings'] if lost_evidence([w])}


def test_directory_check_names_recovered_and_failed_files(tmp_path):
    root = _project(tmp_path / 'proj', {'ok.c': OK_C, 'bad.c': RECOVERED_C, 'nb.ipynb': NOT_JSON})
    code, answer = _check(root)
    assert code == 3
    lost = _lost(answer)
    assert sorted(lost) == ['analysis_failed', 'parse_recovered'], answer['meta']['warnings']
    assert lost['parse_recovered']['files'] == ['bad.c']
    assert lost['analysis_failed']['files'] == ['nb.ipynb']
    [failure] = lost['analysis_failed']['failures']
    assert failure['path'] == 'nb.ipynb' and 'Expecting property name' in failure['reason']
    # The summary counts are unchanged; the warnings name what they count.
    assert answer['summary']['files_degraded'] == 2


@pytest.mark.parametrize('name, text, kind', [
    ('bad.c', RECOVERED_C, 'parse_recovered'),
    ('nb.ipynb', NOT_JSON, 'analysis_failed'),
])
def test_single_file_check_names_the_loss(tmp_path, name, text, kind):
    root = _project(tmp_path / 'proj', {name: text})
    code, answer = _check(root, name)
    assert code == 3
    lost = _lost(answer)
    assert list(lost) == [kind], answer['meta']['warnings']
    assert lost[kind]['files'] == [name]


def test_clean_files_carry_no_lost_evidence(tmp_path):
    root = _project(tmp_path / 'proj', {'ok.c': OK_C, 'ok.py': 'def ok():\n    return 1\n'})
    for target in ('.', 'ok.c'):
        code, answer = _check(root, target)
        assert code == 0, answer
        assert _lost(answer) == {}


RAISING_RULE = '''from reveal.rules.base import BaseRule, Severity


class X911(BaseRule):
    code = "X911"
    message = "raises"
    severity = Severity.LOW
    category = "X"
    file_patterns = ["*.py"]

    def check(self, file_path, structure, content):
        raise RuntimeError("rule blew up")
'''


def test_a_rule_that_raised_is_check_rules_failed(tmp_path):
    root = _project(tmp_path / 'proj', {'ok.py': 'def ok():\n    return 1\n',
                                        '.reveal/rules/custom/X911.py': RAISING_RULE})
    for target in ('.', 'ok.py'):
        code, answer = _check(root, target)
        assert code == 3, answer
        failed = _lost(answer)['check_rules_failed']
        # A directory check also checks the rule module itself (a .py file in the tree).
        assert 'ok.py' in failed['files'] and 'code' not in failed, failed


def test_a_rule_module_that_did_not_load_makes_check_incomplete(tmp_path):
    files = {'ok.py': 'def ok():\n    return 1\n'}
    control = _project(tmp_path / 'clean', files)
    root = _project(tmp_path / 'proj', {**files, '.reveal/rules/custom/X912.py': 'raise RuntimeError("boom")\n'})
    module = (root / '.reveal' / 'rules' / 'custom' / 'X912.py').as_posix()
    for target in ('.', 'ok.py'):
        assert _check(control, target)[0] == 0
        code, answer = _check(root, target)
        assert code == 3, answer
        failed = _lost(answer)['check_rules_failed']
        assert failed['code'] == 'rule_module_not_loaded' and failed['files'] == [module], failed
        assert failed['failures'] == [{'path': module, 'cause': 'plugin_load_failed', 'reason': 'RuntimeError: boom'}]
        # The plugin_warning that named it before stays.
        assert any(w['type'] == 'plugin_warning' and w.get('path') == module for w in answer['meta']['warnings'])


def test_text_check_no_longer_says_clean_when_a_rule_module_did_not_load(tmp_path):
    root = _project(tmp_path / 'proj', {'ok.py': 'def ok():\n    return 1\n',
                                        '.reveal/rules/custom/X912.py': 'raise RuntimeError("boom")\n'})
    result = _cli(root, 'check', '.')
    assert result.returncode == 3
    assert 'No issues found' not in result.stdout
    assert 'scan incomplete' in result.stdout
