"""The recovered-parse warning has one owner, shared by every noun that reads AST structures (BACK-2658).

``recovered_files`` lists the files a structure collection marks ``parse_recovered``;
``recovered_files_warning`` names them. ``parse_recovered_warning`` (AST, trace) is their composition,
and the nouns that hold only paths (patches, testability, calls) call the warning with the paths.
"""
import pytest

from reveal.adapters.ast.analysis import parse_recovered_warning, recovered_files, recovered_files_warning

pytestmark = pytest.mark.unit


def _structures(*files, recovered=()):
    return [{'file': f, 'elements': [], **({'parse_recovered': True} if f in recovered else {})} for f in files]


def test_recovered_files_lists_only_flagged_files_sorted_and_slash_spelled():
    structures = _structures('pkg\\z.c', 'a.c', 'pkg\\b.c', recovered=('pkg\\z.c', 'pkg\\b.c'))  # noqa: win-path
    assert recovered_files(structures) == ('pkg/b.c', 'pkg/z.c')


def test_clean_collection_has_no_recovered_files_and_no_warning():
    structures = _structures('a.py', 'b.py')
    assert recovered_files(structures) == ()
    assert recovered_files_warning(()) is None
    assert parse_recovered_warning(structures) is None


def test_warning_names_up_to_five_then_counts_the_rest():
    paths = [f'd/f{i}.c' for i in (6, 2, 4, 1, 5, 3, 7)]
    assert recovered_files_warning(paths) == {
        'type': 'parse_recovered',
        'count': 7,
        'files': ['d/f1.c', 'd/f2.c', 'd/f3.c', 'd/f4.c', 'd/f5.c'],
        'message': '7 file(s) contain syntax tree-sitter could not read; their elements may be '
                   'incomplete or wrong: d/f1.c, d/f2.c, d/f3.c, d/f4.c, d/f5.c and 2 more',
    }


def test_structure_form_is_the_paths_form():
    structures = _structures('x/b.ts', 'x/a.ts', 'x/c.ts', recovered=('x/b.ts', 'x/c.ts'))
    assert parse_recovered_warning(structures) == recovered_files_warning(recovered_files(structures))
    assert parse_recovered_warning(structures)['files'] == ['x/b.ts', 'x/c.ts']
