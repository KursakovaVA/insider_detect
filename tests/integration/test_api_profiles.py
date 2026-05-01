from __future__ import annotations

from tests.integration.conftest import BAIT_FILE_PATH


class TestProfilesList:
    def test_returns_empty_list_when_no_events(self, client):
        resp = client.get("/api/v1/profiles")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_profile_created_after_first_event(self, client, ingest):
        ingest(src_ip="10.0.0.7", trap_id="sensor_a")

        profiles = client.get("/api/v1/profiles").json()
        assert len(profiles) == 1
        p = profiles[0]
        assert p["src_ip"] == "10.0.0.7"
        assert p["trap_id"] == "sensor_a"
        assert p["risk_score"] >= 0.0
        assert p["last_seen"] is not None

    def test_profiles_sorted_by_risk_score_desc(self, client, ingest):
        ingest(src_ip="10.0.0.1", action="login_success")
        ingest(
            src_ip="10.0.0.2",
            action="file_download",
            object=BAIT_FILE_PATH,
        )

        profiles = client.get("/api/v1/profiles").json()
        assert len(profiles) == 2
        assert profiles[0]["src_ip"] == "10.0.0.2"
        assert profiles[0]["risk_score"] > profiles[1]["risk_score"]

    def test_limit_caps_number_of_returned_profiles(self, client, ingest):
        for i in range(5):
            ingest(src_ip=f"10.0.0.{i+1}")

        profiles = client.get("/api/v1/profiles", params={"limit": 2}).json()
        assert len(profiles) == 2

    def test_repeated_events_dont_duplicate_profile(self, client, ingest):
        for _ in range(4):
            ingest(src_ip="10.0.0.99", trap_id="sensor_a")

        profiles = client.get("/api/v1/profiles").json()
        assert len(profiles) == 1

    def test_different_trap_ids_create_separate_profiles(
        self, client, ingest
    ):
        ingest(src_ip="10.0.0.1", trap_id="sensor_a")
        ingest(src_ip="10.0.0.1", trap_id="sensor_b")

        profiles = client.get("/api/v1/profiles").json()
        assert len(profiles) == 2
        traps = {p["trap_id"] for p in profiles}
        assert traps == {"sensor_a", "sensor_b"}
