from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

import sensors.http_service as http_service


@pytest.fixture
def bait_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bait"
    d.mkdir()
    (d / "salary_report_2025.txt").write_text("zarplata", encoding="utf-8")
    (d / "vpn_passwords.txt").write_text("supersecret", encoding="utf-8")
    (d / "employees.csv").write_text("id,name\n1,ivanov", encoding="utf-8")
    return d


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "http_events.jsonl"


@pytest.fixture
def http_client(
    monkeypatch: pytest.MonkeyPatch, bait_dir: Path, log_path: Path
) -> Iterator[TestClient]:
    monkeypatch.setattr(http_service, "LOG_PATH", str(log_path))
    monkeypatch.setattr(http_service, "BAIT_DIR", bait_dir)
    monkeypatch.setattr(http_service, "TRAP_ID", "test-http-trap")

    with TestClient(http_service.app) as client:
        yield client


def _read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line]


class TestNowIso:
    def test_returns_iso_8601_string_with_tz(self):
        s = http_service.now_iso()
        assert "T" in s
        assert s.endswith("+00:00") or s.endswith("Z")
        assert len(s) > 19


class TestRootRoute:
    def test_get_root_returns_html_with_links(self, http_client, log_path):
        r = http_client.get("/")
        assert r.status_code == 200
        assert "/login" in r.text
        assert "/admin" in r.text
        assert "/files/" in r.text

    def test_get_root_logs_honeypot_hit(self, http_client, log_path):
        http_client.get("/")
        events = _read_log(log_path)
        assert len(events) == 1
        e = events[0]
        assert e["action"] == "honeypot_hit"
        assert e["object"] == "/"
        assert e["source"] == "http"
        assert e["trap_id"] == "test-http-trap"


class TestLoginRoute:
    def test_get_login_renders_form_and_logs_hit(self, http_client, log_path):
        r = http_client.get("/login")
        assert r.status_code == 200
        assert "<form" in r.text

        events = _read_log(log_path)
        assert events[-1]["action"] == "honeypot_hit"
        assert events[-1]["object"] == "/login"

    def test_post_login_returns_401(self, http_client):
        r = http_client.post(
            "/login", data={"username": "root", "password": "toor"}
        )
        assert r.status_code == 401
        assert "Invalid credentials" in r.text

    def test_post_login_logs_failed_with_user_and_password_len(
        self, http_client, log_path
    ):
        http_client.post(
            "/login", data={"username": "admin", "password": "12345"}
        )
        events = _read_log(log_path)
        e = events[-1]

        assert e["action"] == "login_failed"
        assert e["object"] == "http_login"
        assert e["user"] == "admin"
        assert e["raw"]["password_len"] == 5
        assert e["raw"]["method"] == "POST"
        assert e["raw"]["path"] == "/login"

    def test_post_login_truncates_username_at_128(self, http_client, log_path):
        long_user = "a" * 500
        http_client.post(
            "/login", data={"username": long_user, "password": "x"}
        )
        events = _read_log(log_path)

        assert events[-1]["user"] == "a" * 128
        assert len(events[-1]["user"]) == 128

    def test_post_login_empty_username_logs_none(self, http_client, log_path):
        http_client.post("/login", data={"username": "", "password": ""})
        events = _read_log(log_path)
        assert events[-1]["user"] is None
        assert events[-1]["raw"]["password_len"] == 0


class TestAdminRoute:
    def test_admin_returns_404(self, http_client):
        r = http_client.get("/admin")
        assert r.status_code == 404

    def test_admin_logs_honeypot_hit_with_status(self, http_client, log_path):
        http_client.get("/admin")
        events = _read_log(log_path)

        e = events[-1]
        assert e["action"] == "honeypot_hit"
        assert e["object"] == "/admin"
        assert e["raw"]["status"] == 404


class TestFilesIndex:
    def test_files_index_lists_bait_files(self, http_client, log_path):
        r = http_client.get("/files/")
        assert r.status_code == 200
        assert "salary_report_2025.txt" in r.text
        assert "vpn_passwords.txt" in r.text
        assert "employees.csv" in r.text

    def test_files_index_logs_honeypot_hit(self, http_client, log_path):
        http_client.get("/files/")
        events = _read_log(log_path)
        assert events[-1]["action"] == "honeypot_hit"
        assert events[-1]["object"] == "/files/"


class TestFileDownload:
    def test_existing_bait_file_returns_content(self, http_client, bait_dir):
        r = http_client.get("/files/vpn_passwords.txt")
        assert r.status_code == 200
        assert r.text == "supersecret"

    def test_existing_bait_file_logs_file_download(
        self, http_client, log_path
    ):
        http_client.get("/files/employees.csv")
        events = _read_log(log_path)

        e = events[-1]
        assert e["action"] == "file_download"
        assert e["object"] == "employees.csv"

    def test_missing_file_returns_404(self, http_client):
        r = http_client.get("/files/nonexistent.pdf")
        assert r.status_code == 404

    def test_missing_file_logs_honeypot_hit_404(self, http_client, log_path):
        http_client.get("/files/nonexistent.pdf")
        events = _read_log(log_path)

        e = events[-1]
        assert e["action"] == "honeypot_hit"
        assert e["object"] == "/files/nonexistent.pdf"
        assert e["raw"]["status"] == 404


class TestCatchAllRoute:
    @pytest.mark.parametrize(
        "path",
        [
            "/wp-login.php",
            "/phpmyadmin/index.php",
            "/.env",
            "/api/v1/users",
            "/cgi-bin/test.cgi",
        ],
    )
    def test_arbitrary_path_logs_honeypot_hit(
        self, http_client, log_path, path
    ):
        r = http_client.get(path)
        assert r.status_code == 404

        events = _read_log(log_path)
        e = events[-1]
        assert e["action"] == "honeypot_hit"
        assert e["object"] == path
        assert e["raw"]["status"] == 404


class TestEventContractCompatibility:
    def test_logged_event_matches_event_in_schema(
        self, http_client, log_path
    ):
        from app.schemas.event import EventIn

        http_client.post(
            "/login", data={"username": "u", "password": "p"}
        )
        events = _read_log(log_path)
        evt = EventIn(**events[-1])

        assert evt.source == "http"
        assert evt.action == "login_failed"

    def test_all_required_event_fields_present(self, http_client, log_path):
        http_client.get("/")
        e = _read_log(log_path)[-1]
        for key in ("ts", "trap_id", "source", "src_ip", "action", "raw"):
            assert key in e, f"sensor payload missing required key {key!r}"


class TestRequestMetadataInRaw:
    def test_method_and_path_recorded_in_raw(self, http_client, log_path):
        http_client.get("/admin")
        e = _read_log(log_path)[-1]
        assert e["raw"]["method"] == "GET"
        assert e["raw"]["path"] == "/admin"

    def test_query_string_recorded_in_raw(self, http_client, log_path):
        http_client.get("/admin?id=1&debug=true")
        e = _read_log(log_path)[-1]
        assert "id=1" in e["raw"]["query"]
        assert "debug=true" in e["raw"]["query"]

    def test_user_agent_captured(self, http_client, log_path):
        http_client.get("/", headers={"User-Agent": "sqlmap/1.0"})
        e = _read_log(log_path)[-1]
        assert e["raw"]["user_agent"] == "sqlmap/1.0"
