"""BACK-1550: a text list cut below what the result holds says how many it left out."""
from pathlib import Path

from reveal.adapters import architecture, deps, overview
from reveal.adapters.git.renderer import GitRenderer
from reveal.utils.query_control import omitted_line

BASE = Path('/p')


def _out(capsys):
    return capsys.readouterr().out


def test_omitted_line():
    assert omitted_line(10, 10) == '' and omitted_line(3, 5) == ''
    assert omitted_line(10, 5) == '  ... and 5 more (--format json lists all)'
    assert omitted_line(10, 5, '    ').startswith('    ... and 5 more')


def test_architecture_core_abstractions_entry_points_and_components(capsys):
    core = [{'file': f'/p/m{i}.py', 'fan_in': 9 - i % 3} for i in range(12)]
    architecture._render_core_abstractions(core, 5, BASE)
    assert '... and 7 more' in _out(capsys)
    architecture._render_core_abstractions(core, 12, BASE)
    assert 'more' not in _out(capsys)
    eps = [{'file': f'/p/e{i}.py', 'fan_out': 2} for i in range(8)]
    architecture._render_entry_points(eps, 3, BASE)
    assert '... and 5 more' in _out(capsys)
    comps = [{'component': f'/p/c{i}', 'cohesion': 0.5, 'files': 3} for i in range(6)]
    architecture._render_components(comps, 4, BASE)
    assert '... and 2 more' in _out(capsys)


def test_deps_top_importers(capsys):
    importers = [{'file': f'f{i}.py', 'count': 20 - i} for i in range(9)]
    deps._render_top_importers({'top_importers': importers}, 4)
    assert '... and 5 more' in _out(capsys)
    deps._render_top_importers({'top_importers': importers}, 9)
    assert 'more' not in _out(capsys)


def test_git_blame_key_hunks(capsys):
    hunks = [{'lines': {'start': i * 10, 'count': 10 - i},
              'commit': {'hash': f'h{i}', 'date': '2026-10-07', 'author': 'a', 'message': 'm'}}
             for i in range(8)]
    GitRenderer._render_key_hunks(hunks)
    assert '... and 3 more' in _out(capsys)
    GitRenderer._render_key_hunks(hunks[:5])
    assert 'more' not in _out(capsys)
