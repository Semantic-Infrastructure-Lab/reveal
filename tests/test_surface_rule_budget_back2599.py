"""BACK-2599: surface's test/support policy line. A selected project's default basis is behind the Rules pointer
(``test_scope.basis``); a basis that changes what counted stays visible, as patches and imports keep it."""

from reveal.rendering.adapters.surface import _test_policy_lines

DEFAULT = {'anchor': '.', 'source': 'project', 'include_anchor_name': False, 'rule': 'is_test_path',
           'basis': 'paths relative to the selected project'}


def test_default_basis_prints_no_policy_line():
    assert _test_policy_lines(DEFAULT) == []


def test_no_project_boundary_keeps_the_basis_visible():
    scope = dict(DEFAULT, include_anchor_name=True, source='scan_root_fallback',
                 basis='scan-root name and relative paths; project boundary unknown')
    assert _test_policy_lines(scope) == [
        'Test/support policy: scan-root name and relative paths; project boundary unknown '
        '(anchor .; scan_root_fallback)']


def test_declared_layout_keeps_the_basis_and_its_declaration_visible():
    scope = dict(DEFAULT, additional_paths=['helpers'], declaration={'layer': 'project', 'path': '.reveal.yaml'},
                 basis='paths relative to the selected project; conventional names plus declared additional paths')
    assert _test_policy_lines(scope) == [
        'Test/support policy: paths relative to the selected project; conventional names plus declared additional '
        'paths (anchor .; project)', 'Declaration: project .reveal.yaml']
