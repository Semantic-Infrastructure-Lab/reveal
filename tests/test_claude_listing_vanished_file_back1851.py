"""claude:// plans/agents/memory listings survive a file that vanishes mid-listing (BACK-1851).

The newest-first sort stat()ed each file outside any handler, so a file removed between the
glob and the sort was an uncaught FileNotFoundError that ended the whole listing.
"""
from pathlib import Path

import pytest

from reveal.adapters.claude.handlers import workspace

pytestmark = pytest.mark.component


def _vanish(monkeypatch, name):
    real = Path.stat

    def stat(self, *args, **kwargs):
        if self.name == name:
            raise FileNotFoundError(2, 'vanished', str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', stat)


def test_mtime_of_a_vanished_file_is_zero(tmp_path, monkeypatch):
    gone = tmp_path / 'gone.md'
    gone.write_text('x', encoding='utf-8')
    assert workspace._mtime(gone) > 0
    _vanish(monkeypatch, 'gone.md')
    assert workspace._mtime(gone) == 0.0


@pytest.mark.parametrize('call, body', [
    (lambda d: workspace.get_plans(d, 'plans', {}), '# plan\n'),
    (lambda d: workspace.get_agents(d, 'agents', {}), '---\ndescription: d\n---\n'),
])
def test_listing_survives_a_file_that_vanishes_before_the_sort(tmp_path, monkeypatch, call, body):
    (tmp_path / 'good.md').write_text(body, encoding='utf-8')
    (tmp_path / 'gone.md').write_text(body, encoding='utf-8')
    _vanish(monkeypatch, 'gone.md')
    result = call(tmp_path)  # raised FileNotFoundError before the fix
    assert result.get('error') is None
    assert 'good' in str(result)


def test_memory_listing_survives_a_file_that_vanishes_before_the_sort(tmp_path, monkeypatch):
    mem = tmp_path / 'proj' / 'memory'
    mem.mkdir(parents=True)
    (mem / 'good.md').write_text('---\ntype: user\n---\n', encoding='utf-8')
    (mem / 'gone.md').write_text('---\ntype: user\n---\n', encoding='utf-8')
    _vanish(monkeypatch, 'gone.md')
    assert workspace.get_memory(tmp_path, 'memory', {}).get('error') is None
