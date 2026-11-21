import sqlite3

import pytest

from app.storage import Store


def test_pair_and_prompt_rollback_and_reopen(tmp_path):
    store = Store(tmp_path / "app.db")
    store.initialize()
    store.commit_turn("s", "original", "first", "ok", {"latency_ms": 1})
    before = store.load("s")
    with store.connect() as db:
        db.execute("""CREATE TRIGGER fail_assistant BEFORE INSERT ON messages
                      WHEN NEW.role = 'assistant' BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.commit_turn("s", "changed", "second", "broken", {"latency_ms": 2})
    assert Store(store.path).load("s") == before
