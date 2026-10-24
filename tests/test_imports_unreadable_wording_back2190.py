"""An unreadable file is not "parsed with errors" (BACK-2190).

``files_failed`` holds files tree-sitter recovered with ERROR nodes (their recovered imports are
edges) and files never parsed because they could not be read (no tree, their imports are missing).
Every command that discloses the import build's files says which, as ``calls`` already did.
"""
import os
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter

pytestmark = [pytest.mark.component]

skip_root = pytest.mark.skipif(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                               reason='chmod 000 does not make a file unreadable here')


def _tree(root: Path) -> Path:
    root.mkdir()
    (root / 'a.py').write_text('import b\n', encoding='utf-8')
    (root / 'b.py').write_text('X = 1\n', encoding='utf-8')
    (root / 'bad.js').write_text('import { a } from "./a";\nfunction broken( {\n  return a;\n', encoding='utf-8')
    (root / 'c.py').write_text('import a\n', encoding='utf-8')
    return root


def _warnings(root: Path):
    adapter = ImportsAdapter(str(root))
    adapter.get_structure()
    return {w['type']: w for w in adapter.integrity_warnings(root)}


@skip_root
def test_unreadable_file_is_named_unreadable_not_parsed_with_errors(tmp_path):
    root = _tree(tmp_path / 'fx')
    (root / 'c.py').chmod(0)
    try:
        warnings = _warnings(root)
    finally:
        (root / 'c.py').chmod(0o644)
    assert warnings['analysis_failed']['files'] == ['c.py']
    assert 'PermissionError' in warnings['analysis_failed']['message']
    assert 'imports are missing' in warnings['analysis_failed']['message']
    # The syntax-error file keeps its own wording, and the unreadable one is not in it.
    assert warnings['partial_parse']['files'] == ['bad.js']
    assert 'parsed with errors' in warnings['partial_parse']['message']


def test_readable_tree_has_no_unreadable_warning(tmp_path):
    warnings = _warnings(_tree(tmp_path / 'fx'))
    assert 'analysis_failed' not in warnings
    assert warnings['partial_parse']['files'] == ['bad.js']
