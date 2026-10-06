"""BACK-1384: codex ?search= keeps 3 snippets per session; ?matches=N widens it and a cut names it."""

import json
import sqlite3

import pytest

from reveal.adapters.codex.adapter import CodexAdapter
from reveal.utils.results import truncations_of

pytestmark = pytest.mark.component


@pytest.fixture
def codex_db(tmp_path, monkeypatch):
    rollout = tmp_path / "rollout.jsonl"
    lines = [
        json.dumps({"timestamp": f"2026-01-01T00:00:0{i}Z",
                    "payload": {"type": "user_message", "message": f"needle number {i}"}})
        for i in range(6)
    ]
    rollout.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE threads (id TEXT, rollout_path TEXT, title TEXT, "
                 "first_user_message TEXT, model TEXT, updated_at INTEGER, "
                 "thread_source TEXT, archived INTEGER)")
    conn.execute("INSERT INTO threads VALUES ('s1', ?, 'one', 'x', 'm', 5, NULL, 0)",
                 (str(rollout),))
    conn.commit()
    conn.close()
    monkeypatch.setattr(CodexAdapter, "CODEX_DB", db)
    return db


def _search(query):
    return CodexAdapter("sessions/", query).get_structure()


def test_codex_default_keeps_three_and_names_the_knob(codex_db):
    result = _search("search=needle")
    assert len(result["sessions"][0]["matches"]) == 3
    (note,) = truncations_of(result)
    assert (note["shown"], note["total"]) == (3, 6)
    assert "?matches=" in note["message"]


def test_codex_matches_param_widens_and_zero_keeps_all(codex_db):
    wide = _search("search=needle&matches=5")
    assert len(wide["sessions"][0]["matches"]) == 5
    assert len(truncations_of(wide)) == 1  # still a cut, 5 of 6
    full = _search("search=needle&matches=0")
    assert len(full["sessions"][0]["matches"]) == 6
    assert truncations_of(full) == []  # nothing cut, nothing claimed


def test_codex_matches_param_rejects_bad_values(codex_db):
    for bad in ("matches=-1", "matches=x"):
        with pytest.raises(ValueError, match="matches"):
            _search(f"search=needle&{bad}")
