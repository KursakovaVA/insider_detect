from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import sensors.ftp_server as ftp_server
from sensors.ftp_server import HoneyFTPHandler


@pytest.fixture
def log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "logs" / "ftp_events.jsonl"
    monkeypatch.setattr(ftp_server, "LOG_PATH", str(p))
    monkeypatch.setattr(ftp_server, "TRAP_ID", "test-ftp-trap")
    return p


@pytest.fixture
def handler() -> HoneyFTPHandler:
    h = HoneyFTPHandler.__new__(HoneyFTPHandler)
    h.remote_ip = "10.0.0.42"
    h.username = "ftp"
    return h


def _read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line]


class TestNowIso:
    def test_returns_iso_8601_with_tz(self):
        s = ftp_server.now_iso()
        assert "T" in s
        assert s.endswith("+00:00") or s.endswith("Z")


class TestAppendEvent:
    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b" / "c" / "events.jsonl"
        monkeypatch.setattr(ftp_server, "LOG_PATH", str(deep))

        ftp_server.append_event({"foo": "bar"})

        assert deep.exists()
        assert json.loads(deep.read_text()) == {"foo": "bar"}

    def test_appends_one_jsonl_line_per_call(self, log_path):
        ftp_server.append_event({"event": 1})
        ftp_server.append_event({"event": 2})

        lines = log_path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"event": 1}
        assert json.loads(lines[1]) == {"event": 2}

    def test_unicode_is_preserved_not_escaped(self, log_path):
        ftp_server.append_event({"user": "иванов"})
        line = log_path.read_text().splitlines()[0]

        assert "иванов" in line
        assert "\\u" not in line


class TestOnConnect:
    def test_records_connect_event(self, handler, log_path):
        handler.on_connect()
        events = _read_log(log_path)

        assert len(events) == 1
        e = events[0]
        assert e["action"] == "connect"
        assert e["source"] == "ftp"
        assert e["src_ip"] == "10.0.0.42"
        assert e["trap_id"] == "test-ftp-trap"
        assert e["user"] is None
        assert e["object"] is None


class TestOnLogin:
    def test_records_login_success_with_username(self, handler, log_path):
        handler.on_login("admin")
        e = _read_log(log_path)[-1]

        assert e["action"] == "login_success"
        assert e["user"] == "admin"
        assert e["src_ip"] == "10.0.0.42"

    def test_anonymous_login_recorded(self, handler, log_path):
        handler.on_login("anonymous")
        e = _read_log(log_path)[-1]

        assert e["action"] == "login_success"
        assert e["user"] == "anonymous"


class TestOnLoginFailed:
    def test_records_login_failed_with_user_and_password(
        self, handler, log_path
    ):
        handler.on_login_failed("root", "toor")
        e = _read_log(log_path)[-1]

        assert e["action"] == "login_failed"
        assert e["user"] == "root"
        assert e["raw"]["password"] == "toor"
        assert e["src_ip"] == "10.0.0.42"

    def test_empty_password_recorded(self, handler, log_path):
        handler.on_login_failed("root", "")
        e = _read_log(log_path)[-1]

        assert e["raw"]["password"] == ""


class TestOnFileSent:
    def test_records_file_download_with_basename_only(
        self, handler, log_path
    ):
        handler.on_file_sent("/bait/vpn_passwords.txt")
        e = _read_log(log_path)[-1]

        assert e["action"] == "file_download"
        assert e["object"] == "vpn_passwords.txt"
        assert e["raw"]["path"] == "/bait/vpn_passwords.txt"
        assert e["user"] == "ftp"

    def test_unknown_user_when_attribute_missing(self, log_path):
        h = HoneyFTPHandler.__new__(HoneyFTPHandler)
        h.remote_ip = "10.0.0.99"
        h.on_file_sent("/bait/employees.csv")

        e = _read_log(log_path)[-1]
        assert e["user"] is None


class TestOnIncompleteFileSent:
    def test_records_file_download_action(self, handler, log_path):
        handler.on_incomplete_file_sent("/bait/salary_report_2025.txt")
        e = _read_log(log_path)[-1]

        assert e["action"] == "file_download"
        assert e["object"] == "salary_report_2025.txt"
        assert e["raw"]["event"] == "file_sent_incomplete"


class TestEventContractCompatibility:
    def test_connect_event_matches_event_in(self, handler, log_path):
        from app.schemas.event import EventIn

        handler.on_connect()
        evt = EventIn(**_read_log(log_path)[-1])
        assert evt.source == "ftp"
        assert evt.action == "connect"

    def test_file_download_event_matches_event_in(self, handler, log_path):
        from app.schemas.event import EventIn

        handler.on_file_sent("/bait/employees.csv")
        evt = EventIn(**_read_log(log_path)[-1])
        assert evt.action == "file_download"
        assert evt.object == "employees.csv"

    @pytest.mark.parametrize(
        "method_name,args",
        [
            ("on_connect", ()),
            ("on_login", ("u",)),
            ("on_login_failed", ("u", "p")),
            ("on_file_sent", ("/bait/x",)),
            ("on_incomplete_file_sent", ("/bait/x",)),
        ],
    )
    def test_all_events_have_required_fields(
        self, handler, log_path, method_name, args
    ):
        getattr(handler, method_name)(*args)
        e = _read_log(log_path)[-1]
        for key in ("ts", "trap_id", "source", "src_ip", "action", "raw"):
            assert key in e, f"{method_name}: missing {key!r}"
