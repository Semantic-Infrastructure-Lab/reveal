"""depends:// file target: no Tip promising detail that --verbose does not add.

A file target already prints one row per importing statement; `--verbose`
changed nothing but the Tip line that recommended it. `--verbose` matters only
for a directory target, where it lists each module's importers.
"""

import contextlib
import io

from reveal.adapters.depends import DependsRenderer


def _file_result():
    return {'type': 'module_dependents', 'target': 'pkg/mod.py', 'count': 1,
            'dependents': [{'file': 'pkg/user.py', 'line': 3, 'module': 'pkg.mod',
                            'names': ['f'], 'type': 'from_import', 'alias': None}]}


def _render(verbose):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        DependsRenderer._render_dependents(_file_result(), verbose)
    return buf.getvalue()


def test_file_target_has_no_verbose_tip():
    assert '--verbose' not in _render(False)


def test_file_target_text_is_the_same_with_and_without_verbose():
    assert _render(False) == _render(True)
