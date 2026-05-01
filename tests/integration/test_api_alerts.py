from __future__ import annotations

import uuid as _uuid

from tests.integration.conftest import BAIT_FILE_PATH


class TestAlertsList:
    def test_returns_empty_list_when_no_alerts(self, client):
        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_low_risk_event_does_not_create_alert(self, client, ingest):
        ingest(action="login_success")
        assert client.get("/api/v1/alerts").json() == []

    def test_bait_download_creates_medium_alert(self, client, ingest_bait):
        ingest_bait()

        alerts = client.get("/api/v1/alerts").json()
        assert len(alerts) == 1
        assert alerts[0]["src_ip"] == "10.0.0.99"
        assert alerts[0]["status"] == "open"
        assert alerts[0]["severity"] == "medium"
        assert alerts[0]["risk_score"] == 10.0


class TestAlertsFiltering:
    def test_default_status_is_open(self, client, ingest_bait):
        ingest_bait()

        alerts = client.get("/api/v1/alerts").json()
        assert all(a["status"] == "open" for a in alerts)

    def test_filter_status_closed_returns_empty_until_closed(
        self, client, ingest_bait
    ):
        ingest_bait()
        assert client.get("/api/v1/alerts", params={"status": "closed"}).json() == []

    def test_filter_by_src_ip(self, client, ingest_bait):
        ingest_bait(src_ip="10.0.0.1")
        ingest_bait(src_ip="10.0.0.2")

        alerts = client.get(
            "/api/v1/alerts", params={"src_ip": "10.0.0.1"}
        ).json()
        assert len(alerts) == 1
        assert alerts[0]["src_ip"] == "10.0.0.1"

    def test_filter_by_trap_id(self, client, ingest_bait):
        ingest_bait(trap_id="sensor_a")
        ingest_bait(trap_id="sensor_b")

        alerts = client.get(
            "/api/v1/alerts", params={"trap_id": "sensor_a"}
        ).json()
        assert len(alerts) == 1


class TestAlertsPagination:
    def test_limit_caps_response(self, client, ingest_bait):
        for i in range(4):
            ingest_bait(src_ip=f"10.0.0.{i+1}")

        alerts = client.get("/api/v1/alerts", params={"limit": 2}).json()
        assert len(alerts) == 2

    def test_oversize_limit_clamped_to_500(self, client, ingest_bait):
        ingest_bait()

        resp = client.get("/api/v1/alerts", params={"limit": 99_999})
        assert resp.status_code == 200
        assert len(resp.json()) <= 500


class TestAlertDetail:
    def test_returns_alert_with_details_payload(self, client, ingest_bait):
        ingest_bait()
        alert_id = client.get("/api/v1/alerts").json()[0]["alert_id"]

        resp = client.get(f"/api/v1/alerts/{alert_id}")
        assert resp.status_code == 200
        body = resp.json()

        assert body["alert_id"] == alert_id
        assert "details" in body
        assert body["details"]["delta"] == 10.0
        assert "matched_rules" in body["details"]
        assert any(
            r.get("rule_id") == "bait_file_download"
            for r in body["details"]["matched_rules"]
        )

    def test_details_contain_recent_events(self, client, ingest_bait):
        ingest_bait()
        ingest_bait()

        alerts = client.get("/api/v1/alerts").json()
        last_alert_id = alerts[0]["alert_id"]

        body = client.get(f"/api/v1/alerts/{last_alert_id}").json()
        recent = body["details"]["recent_events"]
        assert len(recent) == 2

    def test_recent_events_includes_triggering_event(
        self, client, ingest_bait
    ):
        ingest_bait(src_ip="10.0.0.55")

        alerts = client.get("/api/v1/alerts", params={"src_ip": "10.0.0.55"}).json()
        body = client.get(f"/api/v1/alerts/{alerts[0]['alert_id']}").json()

        triggering_event_id = body["details"]["event"]["event_id"]
        recent_ids = {e["event_id"] for e in body["details"]["recent_events"]}
        assert triggering_event_id in recent_ids

    def test_returns_404_for_missing_alert(self, client):
        random_uuid = str(_uuid.uuid4())
        resp = client.get(f"/api/v1/alerts/{random_uuid}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "alert not found"

    def test_returns_422_for_invalid_uuid(self, client):
        resp = client.get("/api/v1/alerts/not-a-uuid")
        assert resp.status_code == 422


class TestAlertClose:
    def test_close_changes_status(self, client, ingest_bait):
        ingest_bait()
        alert_id = client.get("/api/v1/alerts").json()[0]["alert_id"]

        resp = client.post(f"/api/v1/alerts/{alert_id}/close")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"

    def test_closed_alert_not_in_default_list(self, client, ingest_bait):
        ingest_bait()
        alert_id = client.get("/api/v1/alerts").json()[0]["alert_id"]

        client.post(f"/api/v1/alerts/{alert_id}/close")

        assert client.get("/api/v1/alerts").json() == []

        closed = client.get("/api/v1/alerts", params={"status": "closed"}).json()
        assert len(closed) == 1
        assert closed[0]["alert_id"] == alert_id

    def test_close_returns_404_for_missing_alert(self, client):
        random_uuid = str(_uuid.uuid4())
        resp = client.post(f"/api/v1/alerts/{random_uuid}/close")
        assert resp.status_code == 404

    def test_close_is_idempotent_in_status(self, client, ingest_bait):
        ingest_bait()
        alert_id = client.get("/api/v1/alerts").json()[0]["alert_id"]

        first = client.post(f"/api/v1/alerts/{alert_id}/close")
        second = client.post(f"/api/v1/alerts/{alert_id}/close")

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "closed"
