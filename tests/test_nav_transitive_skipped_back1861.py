"""nav --sideeffects/--boundary --transitive disclose a file whose analysis raised (BACK-1861).

collect_effects_transitive read collect_structures and dropped StructureList.skipped, so a
call chain ending in an unanalyzable file listed no effect behind it and said nothing.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast import analysis

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def a():\n    return b()\n\n\ndef b():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'bad.py').write_text('import os\n\n\ndef c():\n    os.remove("x")\n', encoding='utf-8')
    real = analysis.create_element_dict

    def boom(file_path, *args, **kwargs):
        if file_path.endswith('bad.py'):
            raise ValueError('synthetic analyzer bug')
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', boom)
    return tmp_path


def _nav(tree, flag, *extra):
    return _run_reveal_direct(str(tree / 'ok.py'), 'a', flag, '--transitive', *extra)


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_text_names_the_skipped_file(tree, flag):
    out = _nav(tree, flag).stdout
    assert 'could not be analyzed' in out
    assert 'bad.py' in out
    assert 'ValueError' in out


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_json_warns_about_the_skipped_file(tree, flag):
    data = json.loads(_nav(tree, flag, '--format', 'json').stdout)
    (warning,) = data['warnings']
    assert 'bad.py' in warning and 'ValueError' in warning


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_nothing_skipped_adds_no_warning(tmp_path, flag):
    (tmp_path / 'ok.py').write_text('def a():\n    return b()\n\n\ndef b():\n    return 1\n', encoding='utf-8')
    result = _run_reveal_direct(str(tmp_path / 'ok.py'), 'a', flag, '--transitive', '--format', 'json')
    assert json.loads(result.stdout)['warnings'] == []
    text = _run_reveal_direct(str(tmp_path / 'ok.py'), 'a', flag, '--transitive').stdout
    assert 'could not be analyzed' not in text
