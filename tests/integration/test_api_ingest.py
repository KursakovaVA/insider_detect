from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.main import app as fastapi_app
from app.settings import settings
from tests.integration.conftest import BAIT_FILE_PATH


VALID_UUID = "11111111-1111-1111-1111-111111111111"


class TestIngestSuccess:
    def test_returns_200_on_valid_payload(self, client, make_event_payload):
        resp = client.post("/api/v1/ingest", json=make_event_payload())
        assert resp.status_code == 200

    def test_response_has_expected_shape(self, client, make_event_payload):
        resp = client.post("/api/v1/ingest", json=make_event_payload())
        body = resp.json()
        assert set(body.keys()) >= {
            "status",
            "event_id",
            "src_ip",
            "risk_score",
            "delta",
            "matched_rules",
        }
        assert body["status"] == "ok"

    def test_event_persisted_and_visible_via_events_endpoint(
        self, client, make_event_payload
    ):
        payload = make_event_payload(action="login_success")
        client.post("/api/v1/ingest", json=payload)

        resp = client.get("/api/v1/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["src_ip"] == payload["src_ip"]
        assert events[0]["action"] == "login_success"

    def test_profile_created_and_visible_via_profiles_endpoint(
        self, client, make_event_payload
    ):
        client.post("/api/v1/ingest", json=make_event_payload(src_ip="10.0.0.42"))

        resp = client.get("/api/v1/profiles")
        assert resp.status_code == 200
        profiles = resp.json()
        assert any(p["src_ip"] == "10.0.0.42" for p in profiles)

    def test_bait_download_creates_medium_alert(self, client, make_event_payload):
        payload = make_event_payload(
            action="file_download",
            object=BAIT_FILE_PATH,
        )
        client.post("/api/v1/ingest", json=payload)

        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) == 1
        assert alerts[0]["src_ip"] == payload["src_ip"]
        assert alerts[0]["severity"] == "medium"


class TestIngestValidation:
    def test_missing_required_field_returns_422(self, client, make_event_payload):
        payload = make_event_payload()
        del payload["src_ip"]

        resp = client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 422

    def test_missing_ts_returns_422(self, client, make_event_payload):
        payload = make_event_payload()
        del payload["ts"]

        resp = client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 422

    def test_invalid_uuid_returns_422(self, client, make_event_payload):
        payload = make_event_payload(event_id="not-a-uuid")

        resp = client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 422

    def test_invalid_timestamp_returns_422(self, client, make_event_payload):
        payload = make_event_payload(ts="not-a-date")

        resp = client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client):
        resp = client.post("/api/v1/ingest", json={})
        assert resp.status_code == 422


class TestIngestAuthorization:
    def test_no_auth_required_by_default(self, client, make_event_payload):
        assert settings.INGEST_API_KEY is None
        resp = client.post("/api/v1/ingest", json=make_event_payload())
        assert resp.status_code == 200

    def test_correct_key_accepted(self, client, make_event_payload, monkeypatch):
        monkeypatch.setattr(settings, "INGEST_API_KEY", "s3cret")

        resp = client.post(
            "/api/v1/ingest",
            json=make_event_payload(),
            headers={"X-API-Key": "s3cret"},
        )
        assert resp.status_code == 200

    def test_wrong_key_returns_401(self, client, make_event_payload, monkeypatch):
        monkeypatch.setattr(settings, "INGEST_API_KEY", "s3cret")

        resp = client.post(
            "/api/v1/ingest",
            json=make_event_payload(),
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_missing_key_returns_401_when_required(
        self, client, make_event_payload, monkeypatch
    ):
        monkeypatch.setattr(settings, "INGEST_API_KEY", "s3cret")

        resp = client.post("/api/v1/ingest", json=make_event_payload())
        assert resp.status_code == 401

    def test_api_key_change_takes_effect_without_restart(
        self, client, make_event_payload, monkeypatch
    ):
        monkeypatch.setattr(settings, "INGEST_API_KEY", None)
        assert (
            client.post("/api/v1/ingest", json=make_event_payload()).status_code
            == 200
        )

        monkeypatch.setattr(settings, "INGEST_API_KEY", "rotated-key")
        assert (
            client.post("/api/v1/ingest", json=make_event_payload()).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/ingest",
                json=make_event_payload(),
                headers={"X-API-Key": "rotated-key"},
            ).status_code
            == 200
        )


class TestIngestRulesetUnavailable:
    def test_returns_503_when_ruleset_missing(
        self, client, make_event_payload
    ):
        original = fastapi_app.state.ruleset
        try:
            fastapi_app.state.ruleset = None

            resp = client.post("/api/v1/ingest", json=make_event_payload())
            assert resp.status_code == 503
            assert "ruleset not loaded" in resp.json()["detail"]
        finally:
            fastapi_app.state.ruleset = original


class TestIngestDuplicateEventId:
    def test_duplicate_event_id_raises_integrity_error(
        self, client, make_event_payload
    ):
        payload = make_event_payload(event_id=VALID_UUID)

        first = client.post("/api/v1/ingest", json=payload)
        assert first.status_code == 200

        with pytest.raises(IntegrityError):
            client.post("/api/v1/ingest", json=payload)
