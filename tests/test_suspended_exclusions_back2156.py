"""BACK-2156: ``exclusions.suspended_exclusions`` lifts the active --exclude scope for one block.

I002 builds its import graph through the analysis service, whose discovery walk honors the scope;
the rule's evidence must not shrink with the report (BACK-1259), so it builds inside this block.
"""

from pathlib import Path

from reveal.utils import exclusions


def test_the_scope_is_off_inside_and_restored_after(tmp_path):
    root = Path(tmp_path)
    with exclusions.exclusion_scope(root, ['b.py']):
        assert exclusions.path_is_excluded(root / 'b.py')
        consulted = exclusions.exclusions_consulted()
        with exclusions.suspended_exclusions():
            assert exclusions.active_exclusions() == (None, ())
            assert not exclusions.path_is_excluded(root / 'b.py')
        assert exclusions.active_exclusions() == (root, ('b.py',))
        assert exclusions.exclusions_consulted() is consulted
        assert exclusions.path_is_excluded(root / 'b.py')
    assert exclusions.active_exclusions() == (None, ())


def test_restored_after_an_exception(tmp_path):
    root = Path(tmp_path)
    with exclusions.exclusion_scope(root, ['b.py']):
        try:
            with exclusions.suspended_exclusions():
                raise ValueError('boom')
        except ValueError:
            pass
        assert exclusions.active_exclusions() == (root, ('b.py',))


def test_the_consulted_flag_survives_a_suspension(tmp_path):
    """The flag ledger counts --exclude as used once a walk consulted it; a suspended block in
    between (I002's graph build inside a check) must not reset that."""
    root = Path(tmp_path)
    with exclusions.exclusion_scope(root, ['b.py']):
        exclusions.set_active_exclusions(root, ['b.py'])
        assert exclusions.exclusions_consulted() is False
        exclusions.path_is_excluded(root / 'a.py')
        assert exclusions.exclusions_consulted() is True
        with exclusions.suspended_exclusions():
            pass
        assert exclusions.exclusions_consulted() is True
