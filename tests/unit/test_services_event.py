from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.event import list_events_service


def _sql(session: MagicMock) -> str:
    stmt = session.execute.call_args[0][0]
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


class TestPagination:
    def test_default_limit_50_offset_0(self, session):
        list_events_service(session)
        sql = _sql(session)
        assert "LIMIT 50" in sql
        assert "OFFSET 0" in sql

    def test_limit_clamped_max_500(self, session):
        list_events_service(session, limit=10_000)
        assert "LIMIT 500" in _sql(session)

    def test_limit_clamped_min_1(self, session):
        list_events_service(session, limit=0)
        assert "LIMIT 1" in _sql(session)

    def test_negative_offset_clamped_zero(self, session):
        list_events_service(session, offset=-5)
        assert "OFFSET 0" in _sql(session)


class TestFilters:
    def test_no_filters_by_default(self, session):
        list_events_service(session)
        sql = _sql(session)

        where = sql.split("WHERE", 1)
        assert len(where) == 1, "не должно быть WHERE без фильтров"

    def test_src_ip_filter(self, session):
        list_events_service(session, src_ip="10.0.0.7")
        assert "events.src_ip = '10.0.0.7'" in _sql(session)

    def test_user_filter(self, session):
        list_events_service(session, user="ivanov")
        assert "events.\"user\" = 'ivanov'" in _sql(session)

    def test_action_filter(self, session):
        list_events_service(session, action="login_failed")
        assert "events.action = 'login_failed'" in _sql(session)

    def test_combined_filters(self, session):
        list_events_service(
            session, src_ip="10.0.0.5", user="root", action="command_exec"
        )
        sql = _sql(session)
        assert "events.src_ip = '10.0.0.5'" in sql
        assert "events.\"user\" = 'root'" in sql
        assert "events.action = 'command_exec'" in sql


class TestOrdering:
    def test_orders_by_ts_desc(self, session):
        list_events_service(session)
        assert "ORDER BY events.ts DESC" in _sql(session)
