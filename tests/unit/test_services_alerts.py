from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services.alerts import (
    close_alert_service,
    get_alert_service,
    list_alerts_service,
)


def _captured_sql(session_mock: MagicMock) -> str:
    stmt = session_mock.execute.call_args[0][0]
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.fixture
def session() -> MagicMock:
    s = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = []
    return s


class TestListAlertsServicePagination:
    def test_default_limit_is_50(self, session):
        list_alerts_service(session)
        assert "LIMIT 50" in _captured_sql(session)

    def test_default_offset_is_0(self, session):
        list_alerts_service(session)
        assert "OFFSET 0" in _captured_sql(session)

    def test_limit_clamped_to_max_500(self, session):
        list_alerts_service(session, limit=10_000)
        assert "LIMIT 500" in _captured_sql(session)

    def test_limit_zero_clamped_to_one(self, session):
        list_alerts_service(session, limit=0)
        assert "LIMIT 1" in _captured_sql(session)

    def test_negative_limit_clamped_to_one(self, session):
        list_alerts_service(session, limit=-10)
        assert "LIMIT 1" in _captured_sql(session)

    def test_negative_offset_clamped_to_zero(self, session):
        list_alerts_service(session, offset=-100)
        assert "OFFSET 0" in _captured_sql(session)

    def test_offset_passed_through(self, session):
        list_alerts_service(session, offset=42)
        assert "OFFSET 42" in _captured_sql(session)


class TestListAlertsServiceFilters:
    def test_default_status_is_open(self, session):
        list_alerts_service(session)
        sql = _captured_sql(session)
        assert "alerts.status = 'open'" in sql

    def test_status_can_be_overridden(self, session):
        list_alerts_service(session, status="closed")
        sql = _captured_sql(session)
        assert "alerts.status = 'closed'" in sql
        assert "alerts.status = 'open'" not in sql

    def test_src_ip_filter_added_when_provided(self, session):
        list_alerts_service(session, src_ip="10.0.0.5")
        sql = _captured_sql(session)
        assert "alerts.src_ip = '10.0.0.5'" in sql

    def test_src_ip_filter_omitted_when_none(self, session):
        list_alerts_service(session, src_ip=None)
        sql = _captured_sql(session)
        where_clause = sql.split("WHERE", 1)[1]
        assert "alerts.src_ip" not in where_clause

    def test_trap_id_filter_omitted_when_none(self, session):
        list_alerts_service(session, trap_id=None)
        sql = _captured_sql(session)
        where_clause = sql.split("WHERE", 1)[1]
        assert "alerts.trap_id" not in where_clause

    def test_trap_id_filter_added_when_provided(self, session):
        list_alerts_service(session, trap_id="ssh-1")
        sql = _captured_sql(session)
        assert "alerts.trap_id = 'ssh-1'" in sql

    def test_combined_filters(self, session):
        list_alerts_service(
            session, src_ip="10.0.0.5", trap_id="ssh-1", status="closed"
        )
        sql = _captured_sql(session)

        assert "alerts.src_ip = '10.0.0.5'" in sql
        assert "alerts.trap_id = 'ssh-1'" in sql
        assert "alerts.status = 'closed'" in sql


class TestListAlertsServiceOrdering:
    def test_orders_by_ts_updated_desc(self, session):
        list_alerts_service(session)
        sql = _captured_sql(session)
        assert "ORDER BY alerts.ts_updated DESC" in sql


class TestGetAlertService:
    def test_calls_session_get_with_alert_id(self, session):
        alert_id = uuid4()
        get_alert_service(session, alert_id)

        session.get.assert_called_once()
        args = session.get.call_args[0]
        assert args[1] == alert_id

    def test_returns_what_session_get_returns(self, session):
        sentinel = SimpleNamespace(id=uuid4(), severity="high")
        session.get.return_value = sentinel

        assert get_alert_service(session, sentinel.id) is sentinel

    def test_returns_none_for_missing_alert(self, session):
        session.get.return_value = None
        assert get_alert_service(session, uuid4()) is None


class TestCloseAlertService:
    def test_returns_none_for_missing_alert(self, session):
        session.get.return_value = None

        assert close_alert_service(session, uuid4()) is None
        session.commit.assert_not_called()

    def test_sets_status_to_closed(self, session):
        row = SimpleNamespace(
            id=uuid4(),
            status="open",
            ts_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.get.return_value = row

        result = close_alert_service(session, row.id)

        assert result is row
        assert row.status == "closed"

    def test_updates_ts_updated_to_now_utc(self, session):
        row = SimpleNamespace(
            id=uuid4(),
            status="open",
            ts_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.get.return_value = row

        close_alert_service(session, row.id)

        assert row.ts_updated.tzinfo is not None
        assert row.ts_updated > datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert row.ts_updated <= datetime.now(timezone.utc)

    def test_commits_and_refreshes(self, session):
        row = SimpleNamespace(
            id=uuid4(), status="open", ts_updated=datetime.now(timezone.utc)
        )
        session.get.return_value = row

        close_alert_service(session, row.id)

        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(row)
