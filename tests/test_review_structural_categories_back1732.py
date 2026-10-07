"""review's structural summary names every category diff:// compares (BACK-1732)."""

from reveal.cli.commands.review import _render_structural_summary


def test_structural_summary_names_a_category_beyond_functions_classes_imports(capsys):
    _render_structural_summary({
        'functions': {'added': 0, 'removed': 0, 'modified': 0},
        'classes': {'added': 0, 'removed': 0, 'modified': 0},
        'imports': {'added': 0, 'removed': 0},
        'interfaces': {'added': 1, 'removed': 0, 'modified': 0},
    })
    assert capsys.readouterr().out.strip() == 'Structural changes: interfaces +1'


def test_structural_summary_keeps_its_order_and_says_none_when_nothing_changed(capsys):
    _render_structural_summary({
        'functions': {'added': 2, 'removed': 0, 'modified': 1},
        'imports': {'added': 0, 'removed': 1},
    })
    _render_structural_summary({'functions': {'added': 0, 'removed': 0, 'modified': 0}})
    assert capsys.readouterr().out.split('\n')[1:4:2] == [
        'Structural changes: functions +2 ~1, imports -1', 'Structural changes: none']
