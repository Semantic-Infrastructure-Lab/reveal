"""claude://sessions: a session file deleted between the glob and the stat is skipped (BACK-1851).

The stat sat inside list_sessions' one try block, so FileNotFoundError ended the scan: the
listing carried an `error` and none of the sessions in the directories after it.
"""
from pathlib import Path

import pytest

from reveal.adapters.claude.handlers.sessions import list_sessions

pytestmark = pytest.mark.component


def test_a_vanished_session_file_does_not_end_the_listing(tmp_path, monkeypatch):
    for name in ('a-sessions-one', 'b-sessions-two', 'c-sessions-three'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'x.jsonl').write_text('{}\n', encoding='utf-8')
    real = Path.stat

    def stat(self, *args, **kwargs):
        if self.suffix == '.jsonl' and self.parent.name == 'b-sessions-two':
            raise FileNotFoundError(2, 'vanished', str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', stat)
    result = list_sessions(tmp_path, {})
    assert result.get('error') is None
    assert sorted(s['session'] for s in result['recent_sessions']) == ['one', 'three']
