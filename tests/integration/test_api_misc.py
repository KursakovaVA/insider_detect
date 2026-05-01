from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.rules_engine import load_rules


class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_status_ok(self, client):
        body = client.get("/health").json()
        assert body == {"status": "ok"}


class TestRulesReload:
    def test_reload_returns_summary(self, client):
        resp = client.post("/api/v1/rules/reload")
        assert resp.status_code == 200

        body = resp.json()
        assert body["status"] == "ok"
        assert body["rules"] >= 1
        assert body["alert_threshold"] > 0.0

    def test_reload_count_matches_rules_yaml(self, client):
        body = client.post("/api/v1/rules/reload").json()
        expected = load_rules("rules/rules.yaml")
        assert body["rules"] == len(expected.rules)
        assert body["alert_threshold"] == expected.alert_threshold

    def test_reload_updates_app_state(self, client):
        from app.main import app as fastapi_app

        client.post("/api/v1/rules/reload")
        assert fastapi_app.state.ruleset is not None
        assert len(fastapi_app.state.ruleset.rules) >= 1

    def test_reload_actually_swaps_ruleset(
        self, client, make_event_payload, tmp_path: Path, monkeypatch
    ):
        from app.main import app as fastapi_app
        from app.services import rules as rules_module

        custom_yaml = tmp_path / "minimal_rules.yaml"
        custom_yaml.write_text(
            yaml.safe_dump(
                {
                    "thresholds": {
                        "alert": 9999.0,
                        "severity": {"medium": 1.0, "high": 2.0, "critical": 3.0},
                    },
                    "context": {
                        "off_hours": {"multiplier": 1.0, "actions": []},
                    },
                    "rules": [],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        original_ruleset = fastapi_app.state.ruleset
        monkeypatch.setattr(rules_module.settings, "RULES_PATH", str(custom_yaml))

        try:
            reload_resp = client.post("/api/v1/rules/reload")
            assert reload_resp.status_code == 200
            assert reload_resp.json()["rules"] == 0

            ingest_resp = client.post(
                "/api/v1/ingest",
                json=make_event_payload(
                    action="file_download",
                    object="/srv/ftp/bait/salary_report_2025.txt",
                ),
            )
            body = ingest_resp.json()
            assert body["delta"] == pytest.approx(0.5)
            assert [r["rule_id"] for r in body["matched_rules"]] == ["default"]
        finally:
            fastapi_app.state.ruleset = original_ruleset
