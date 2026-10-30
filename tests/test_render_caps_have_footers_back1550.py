"""BACK-1550: a text list cut below what the result holds says how many it left out."""
from pathlib import Path

from reveal.adapters import overview
from reveal.rendering.adapters import architecture, deps
from reveal.adapters.git.renderer import GitRenderer
from reveal.utils.query_control import omitted_line

BASE = Path('/p')


def _out(capsys):
    return capsys.readouterr().out


def test_omitted_line():
    assert omitted_line(10, 10) == '' and omitted_line(3, 5) == ''
    assert omitted_line(10, 5) == '  ... and 5 more (--format json lists all)'
    assert omitted_line(10, 5, '    ').startswith('    ... and 5 more')


def test_architecture_alias_discloses_canonical_graph_bounds(tmp_path, capsys):
    from reveal.adapters.architecture import ArchitectureAdapter
    for index in range(6):
        folder = tmp_path / f'part{index}'
        folder.mkdir()
        (folder / 'entry.py').write_text('from .leaf import VALUE\n', encoding='utf-8')
        (folder / 'leaf.py').write_text('VALUE=1\n', encoding='utf-8')
    result = ArchitectureAdapter(str(tmp_path), 'top=2').get_structure()
    body = architecture.ArchitectureRenderer.render_structure(result)
    assert body.count('Most imported files  (showing 2 of 6 observed)') == 1
    assert body.count('Active entrypoint candidates  (showing 2 of 6 observed)') == 1
    assert body.count('Major components  (showing 2 of 6 observed)') == 1
    full = ArchitectureAdapter(str(tmp_path), 'top=20').get_structure()
    assert 'showing 6 of 6 observed' in architecture.ArchitectureRenderer.render_structure(full)
    assert not _out(capsys)


def test_deps_top_importers(capsys):
    importers = [{'file': f'f{i}.py', 'count': 20 - i} for i in range(9)]
    assert '... and 5 more' in '\n'.join(deps._render_top_importers({'top_importers': importers}, 4))
    assert 'more' not in '\n'.join(deps._render_top_importers({'top_importers': importers}, 9))
    assert not _out(capsys)


def test_git_blame_key_hunks(capsys):
    hunks = [{'lines': {'start': i * 10, 'count': 10 - i},
              'commit': {'hash': f'h{i}', 'date': '2026-10-07', 'author': 'a', 'message': 'm'}}
             for i in range(8)]
    GitRenderer._render_key_hunks(hunks)
    assert '... and 3 more' in _out(capsys)
    GitRenderer._render_key_hunks(hunks[:5])
    assert 'more' not in _out(capsys)
