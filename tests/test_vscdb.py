"""Tests for the read-only Workspace_DB accessor (vscdb.py)."""

import sqlite3
from pathlib import Path

from kiro_cleaner.vscdb import (
    folder_from_state_db,
    folder_from_workspace_json,
    read_item,
    workspace_folder,
)


def _make_db(path: Path, items: dict[str, str]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)", list(items.items())
    )
    con.commit()
    con.close()


class TestReadItem:
    def test_reads_existing_key(self, tmp_path):
        db = tmp_path / "state.vscdb"
        _make_db(db, {"foo": "bar"})
        assert read_item(db, "foo") == "bar"

    def test_missing_key_returns_none(self, tmp_path):
        db = tmp_path / "state.vscdb"
        _make_db(db, {"foo": "bar"})
        assert read_item(db, "absent") is None

    def test_missing_file_returns_none(self, tmp_path):
        assert read_item(tmp_path / "nope.vscdb", "foo") is None

    def test_corrupt_db_returns_none(self, tmp_path):
        db = tmp_path / "state.vscdb"
        db.write_text("this is not sqlite")
        assert read_item(db, "foo") is None


class TestWorkspaceFolder:
    def test_folder_from_workspace_json(self, tmp_path):
        (tmp_path / "workspace.json").write_text(
            '{"folder": "file:///Users/tester/projects/MXP%20Agent"}'
        )
        assert folder_from_workspace_json(tmp_path) == "/Users/tester/projects/MXP Agent"

    def test_workspace_json_missing_returns_none(self, tmp_path):
        assert folder_from_workspace_json(tmp_path) is None

    def test_folder_from_state_db(self, tmp_path):
        db = tmp_path / "state.vscdb"
        _make_db(
            db,
            {
                "history.entries": (
                    '[{"editor":{"resource":"file:///Users/tester/proj/a.py"}},'
                    '{"editor":{"resource":"file:///Users/tester/proj/b.py"}}]'
                )
            },
        )
        assert folder_from_state_db(tmp_path) == "/Users/tester/proj"

    def test_workspace_folder_prefers_json(self, tmp_path):
        (tmp_path / "workspace.json").write_text(
            '{"folder": "file:///Users/tester/fromjson"}'
        )
        _make_db(
            tmp_path / "state.vscdb",
            {"history.entries": '"file:///Users/tester/fromdb/x.py"'},
        )
        assert workspace_folder(tmp_path) == "/Users/tester/fromjson"

    def test_read_only_does_not_modify_db(self, tmp_path):
        db = tmp_path / "state.vscdb"
        _make_db(db, {"history.entries": '"file:///Users/tester/proj/x.py"'})
        before = db.stat().st_mtime_ns
        folder_from_state_db(tmp_path)
        read_item(db, "history.entries")
        after = db.stat().st_mtime_ns
        assert before == after
