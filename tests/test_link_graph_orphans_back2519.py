"""BACK-2519: ?link-graph reports orphans (no inbound link), as its help says.

The help promised "forward links + backlinks + orphans", but the answer listed only isolated
docs (no link either way): a doc that links out while nothing links to it was named nowhere.
"""
import json
from io import StringIO
from pathlib import Path

from conftest import _run_reveal_direct
from reveal.adapters.markdown.operations import build_link_graph


def _tree(tmp_path: Path) -> Path:
    (tmp_path / 'index.md').write_text('[a](a.md)\n', encoding='utf-8')     # orphan: links out only
    (tmp_path / 'a.md').write_text('[b](b.md)\n', encoding='utf-8')         # linked by index
    (tmp_path / 'b.md').write_text('end\n', encoding='utf-8')               # linked by a
    (tmp_path / 'alone.md').write_text('no links\n', encoding='utf-8')      # isolated (also an orphan)
    return tmp_path


def test_orphans_are_docs_nothing_links_to(tmp_path):
    graph = build_link_graph(_tree(tmp_path))
    assert graph['orphans'] == ['alone.md', 'index.md']
    assert graph['isolated'] == ['alone.md']  # unchanged: no link in or out


def test_text_names_an_orphan_that_links_out(tmp_path):
    root = _tree(tmp_path)
    result = _run_reveal_direct(f'markdown://{root.as_posix()}/?link-graph')
    assert result.returncode == 0, result.stderr
    assert '2 orphans' in result.stdout and '1 isolated' in result.stdout
    orphans_section = result.stdout.split('Orphans', 1)[1].split('Isolated', 1)[0]
    assert 'index.md' in orphans_section
    assert 'alone.md' not in orphans_section  # listed once, under Isolated


def test_json_carries_orphans(tmp_path):
    root = _tree(tmp_path)
    payload = json.loads(_run_reveal_direct(f'markdown://{root.as_posix()}/?link-graph', '--format', 'json').stdout)
    assert payload['orphans'] == ['alone.md', 'index.md']
