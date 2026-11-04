"""A C file whose last line is an #include with no final newline parses cleanly (BACK-2501).

tree-sitter-c ends that file with a zero-width MISSING ``preproc_include_token2`` inside the last
``preproc_include``. ``tree_has_recovery_artifacts`` accepted that end-of-file quirk only as a direct
child of the root, so ``reveal check`` called every such file "did not parse cleanly" and exited 3,
and since BACK-2497 ``imports://`` also listed it in ``files_failed``. A MISSING that is a real
missing token (a ``)`` at the end of the file), or a second MISSING, is still a recovery.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct


def analyzer(tmp_path: Path, name: str, text: str):
    from reveal.registry import get_analyzer
    f = tmp_path / name
    f.write_bytes(text.encode('utf-8'))
    return get_analyzer(str(f))(str(f))


@pytest.mark.parametrize('text', [
    '#include <stdio.h>',
    '#include "a.h"',
    '#include <stdio.h>\n#include "a.h"',
    'int x = 1;\n#include "a.h"',
])
def test_trailing_include_without_newline_is_clean(tmp_path, text):
    found = analyzer(tmp_path, 'a.c', text)
    assert not found._has_recovery_artifacts()
    assert '_has_errors' not in found.get_structure()


def test_check_and_imports_take_it_as_complete(tmp_path):
    (tmp_path / 'a.c').write_bytes(b'#include <stdio.h>\n#include "b.h"')
    (tmp_path / 'b.h').write_bytes(b'int b(void);\n')
    check = _run_reveal_direct('check', tmp_path / 'a.c')
    assert check.returncode == 0, (check.stdout, check.stderr)
    imports = _run_reveal_direct(f'imports://{tmp_path.as_posix()}', '--format', 'json')
    assert imports.returncode == 0, (imports.stdout, imports.stderr)
    assert not json.loads(imports.stdout).get('files_failed')


@pytest.mark.parametrize('name,text', [
    ('a.c', 'int f(void) {\n  return (1;\n}\n#include "a.h"'),  # a real MISSING ")" plus the quirk
    ('a.lua', 'local x = (1'),  # a real missing ")" at the very end of the file
    ('a.c', 'int f(void) { return 1;'),  # missing "}" at end of file
])
def test_a_real_missing_token_at_the_end_is_still_a_recovery(tmp_path, name, text):
    assert analyzer(tmp_path, name, text)._has_recovery_artifacts()
