"""A `# noqa` on an import survives a non-UTF-8 source file (BACK-1857).

extract_imports re-read the file as strict UTF-8 for its noqa lines; a latin-1 file landed in
the except branch and every noqa comment in it was lost, so I005 and friends reported
imports the author had suppressed.
"""
from pathlib import Path

import pytest

from reveal.analyzers.imports.python import PythonExtractor

pytestmark = pytest.mark.component


def _imports(tmp_path, data: bytes):
    path = tmp_path / 'mod.py'
    path.write_bytes(data)
    return PythonExtractor().extract_imports(Path(path))


@pytest.mark.parametrize('encoding', ['utf-8', 'latin-1'])
def test_noqa_comment_is_seen_in_the_import_line(tmp_path, encoding):
    source = '# café\nimport os  # noqa: F401\nfrom sys import path  # noqa: I001\n'
    imports = _imports(tmp_path, source.encode(encoding))
    assert len(imports) == 2
    assert all('noqa' in imp.source_line for imp in imports)
