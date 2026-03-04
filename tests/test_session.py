import time
from pathlib import Path

import pytest

from core.session import SessionManager


@pytest.fixture
def sm(tmp_path):
    return SessionManager(tmp_path / "sessions.db")


def test_no_session_initially(sm):
    assert sm.get_session(12345) is None


def test_store_and_retrieve_session(sm):
    sm.set_session(12345, "sess-abc")
    assert sm.get_session(12345) == "sess-abc"


def test_update_session(sm):
    sm.set_session(12345, "sess-old")
    sm.set_session(12345, "sess-new")
    assert sm.get_session(12345) == "sess-new"


def test_clear_session(sm):
    sm.set_session(12345, "sess-abc")
    sm.clear_session(12345)
    assert sm.get_session(12345) is None


def test_archive_stale_sessions(sm):
    sm.set_session(12345, "sess-abc")
    # Manually backdate the updated_at to simulate staleness
    sm._db.execute(
        "UPDATE sessions SET updated_at = updated_at - 90000 WHERE chat_id = ?",
        (12345,),
    )
    sm._db.commit()
    archived = sm.archive_stale(max_age_seconds=86400)
    assert archived == 1
    assert sm.get_session(12345) is None


def test_list_archived_sessions(sm):
    sm.set_session(12345, "sess-abc")
    sm._db.execute(
        "UPDATE sessions SET updated_at = updated_at - 90000 WHERE chat_id = ?",
        (12345,),
    )
    sm._db.commit()
    sm.archive_stale(max_age_seconds=86400)
    history = sm.get_history(12345)
    assert len(history) == 1
    assert history[0]["session_id"] == "sess-abc"
