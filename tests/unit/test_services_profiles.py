from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.profiles import list_profiles_service


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


class TestListProfilesService:
    def test_default_limit_is_50(self, session):
        list_profiles_service(session)
        assert "LIMIT 50" in _sql(session)

    def test_limit_clamped_to_max_500(self, session):
        list_profiles_service(session, limit=99_999)
        assert "LIMIT 500" in _sql(session)

    def test_limit_clamped_to_min_1(self, session):
        list_profiles_service(session, limit=0)
        assert "LIMIT 1" in _sql(session)

    def test_orders_by_risk_score_desc(self, session):
        list_profiles_service(session)
        assert "ORDER BY profiles.risk_score DESC" in _sql(session)

    def test_returns_what_session_returns(self, session):
        sentinel = [object(), object()]
        session.execute.return_value.scalars.return_value.all.return_value = sentinel

        result = list_profiles_service(session)
        assert result is sentinel
