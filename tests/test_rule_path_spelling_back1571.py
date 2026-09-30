"""BACK-1571: a rule's answer must not depend on how the file's path is spelled, or on the cwd.

`reveal check .` hands every rule an absolute path; `reveal check main.py` handed them the
path as typed. Rules that walk up from the file then stopped at '.': from inside a package,
B005 missed a dead import, M102 an orphan module, U502 a wrong repo URL, I003 a layer
violation, L004/L005 a docs directory. Rule settings were read from the cwd's .reveal.yaml
(BaseRule.get_config, E501's skip_categories), so `reveal check /abs/f.py` from another
directory ignored the project's C901 threshold. Each file below is checked three ways and must give one answer.
"""
import json
from pathlib import Path

import pytest

from reveal.api import check

_FILES = {
    'pyproject.toml': '[project]\nname = "pkg"\nversion = "0"\n\n[project.urls]\n'
                      'Homepage = "https://github.com/goodowner/goodrepo"\n',
    '.reveal.yaml': ('root: true\n'
                     'rules:\n  C901:\n    threshold: 50\n  E501:\n    skip_categories: []\n'
                     'architecture:\n  layers:\n    - name: ui\n      paths: ["app/ui/**"]\n'
                     '      deny_imports: ["app/db"]\n'),
    'pkg/__init__.py': '',
    'pkg/used.py': 'def used():\n    return 1\n',
    'pkg/main.py': 'from pkg.used import used\nfrom pkg.missing import gone\n\n\n'
                   'def main():\n    return used() + gone()\n',
    'pkg/orphan.py': 'def lonely():\n    return 42\n',
    'pkg/tangled.py': 'from pkg.used import used\n\n\ndef tangled(x):\n' + ''.join(
        f'    if x == {i}:\n        x += used()\n' for i in range(12)) + '    return x\n',
    'app/__init__.py': '',
    'app/ui/__init__.py': '',
    'app/db/__init__.py': '',
    'app/db/models.py': 'def q():\n    return 1\n',
    'app/ui/views.py': 'from app.db.models import q\n\n\ndef view():\n    return q()\n',
    'docs/guide.md': '# Guide\n\nSee https://github.com/wrongowner/wrongrepo for more.\n\n'
                     + 'A paragraph long enough to pass the 100-column limit. ' * 3 + '\n',
    'tsconfig.json': json.dumps({'compilerOptions': {'baseUrl': '.', 'paths': {'@lib/*': ['lib/*']}}}),
    'lib/util.js': 'export const util = 1;\n',
    'src/app.js': "import { util } from '@lib/util';\nimport { nope } from '@lib/nope';\n"
                  'export const a = util + nope;\n',
}

# What each file must be flagged for, so a spelling that finds nothing cannot pass by
# agreeing with another spelling that also found nothing.
_EXPECTED = {
    'pkg/main.py': {'B005'},
    'pkg/orphan.py': {'M102'},
    'app/ui/views.py': {'I003'},
    'docs/guide.md': {'U502', 'L004', 'L005', 'E501'},  # E501: the project's skip_categories: []
    'src/app.js': {'B005'},
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    for rel, text in _FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding='utf-8')
    (tmp_path / 'elsewhere').mkdir()
    return root


def _answer(spelled, cwd, monkeypatch):
    monkeypatch.chdir(cwd)
    detections = check(spelled)
    return sorted({(d.rule_code, d.line, d.column, d.message) for d in detections}), detections


@pytest.mark.parametrize('rel', sorted(set(_EXPECTED) | {'pkg/tangled.py', 'pkg/used.py'}))
def test_one_answer_whatever_the_spelling_and_cwd(project, monkeypatch, rel):
    target = project / rel
    by_absolute, _ = _answer(str(target), project.parent / 'elsewhere', monkeypatch)
    from_root, _ = _answer(rel, project, monkeypatch)
    from_own_dir, _ = _answer(target.name, target.parent, monkeypatch)
    assert from_root == by_absolute
    assert from_own_dir == by_absolute
    codes = {code for code, *_ in by_absolute}
    assert _EXPECTED.get(rel, set()) <= codes


def test_rule_settings_come_from_the_file_s_project_not_the_cwd(project, monkeypatch):
    """.reveal.yaml raises C901's threshold to 50; tangled() scores 13."""
    target = project / 'pkg' / 'tangled.py'
    for cwd in (project.parent / 'elsewhere', project, target.parent):
        answer, _ = _answer(str(target), cwd, monkeypatch)
        assert 'C901' not in {code for code, *_ in answer}, cwd
    (project / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    from reveal.config import RevealConfig
    RevealConfig._cache.clear()
    answer, _ = _answer(str(target), project, monkeypatch)
    assert 'C901' in {code for code, *_ in answer}  # the control: it scores over the default 10


def test_a_detection_names_the_file_as_the_caller_spelled_it(project, monkeypatch):
    _, detections = _answer('main.py', project / 'pkg', monkeypatch)
    assert detections and {d.file_path for d in detections} == {'main.py'}
    _, detections = _answer(str(project / 'pkg' / 'main.py'), project, monkeypatch)
    assert {d.file_path for d in detections} == {str(project / 'pkg' / 'main.py')}
