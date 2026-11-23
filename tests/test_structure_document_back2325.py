"""``display.structure.structure_document`` (BACK-2325, D21): the JSON document ``reveal FILE --format json`` prints,
built and returned instead of printed, so the Python API can return the CLI's own document. ``_render_json_output``
prints exactly that document with the invocation's warnings attached (refactor: no output change).

Owner: ``display/structure.py``. Effect on other routes: none (``show_structure``'s JSON branch prints through
``_render_json_output`` as before; ``adapters/pack.py`` and the text renderers do not call it).
"""
import json

import pytest

from reveal.display.structure import _render_json_output, structure_document
from reveal.registry import get_analyzer

pytestmark = [pytest.mark.unit]


@pytest.fixture
def files(tmp_path):
    (tmp_path / 'ok.py').write_text('import os\n\n\ndef foo():\n    return 1\n\n\nclass K:\n    def m(self):\n'
                                    '        return os.sep\n', encoding='utf-8')
    (tmp_path / 'syn.py').write_text('def f(:\n  pass\n', encoding='utf-8')
    (tmp_path / 'bad.xml').write_text('<a><b></a>', encoding='utf-8')
    (tmp_path / 'notes.md').write_text('# Title\n\n## Part\n\ntext [a link](ok.py)\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('name', ['ok.py', 'syn.py', 'bad.xml', 'notes.md'])
def test_the_document_is_what_the_renderer_prints(files, capsys, name):
    path = str(files / name)
    analyzer = get_analyzer(path)(path)
    structure = analyzer.get_structure()
    document = structure_document(analyzer, structure)
    assert capsys.readouterr() == ('', '')  # built, never printed
    _render_json_output(analyzer, structure)
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(document))
    assert {'source', 'contract_version', 'type', 'structure'} <= set(document)


def test_a_failed_parse_keeps_its_error_in_the_document(files):
    path = str(files / 'bad.xml')
    analyzer = get_analyzer(path)(path)
    document = structure_document(analyzer, analyzer.get_structure())
    assert 'XML parse error' in json.dumps(document['error'])
