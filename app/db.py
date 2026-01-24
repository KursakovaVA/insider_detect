from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.settings import settings

class Base(DeclarativeBase):
    pass

class Database:
    def __init__(self, url: str | None = None):
        self.url = url or self._build_postgres_url()

        self.engine = create_engine(
            self.url,
            echo=settings.APP_DEBUG,
            future=True,
            pool_pre_ping=True,
        )

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def _build_postgres_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{settings.POSTGRES_USER}:"
            f"{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_HOST}:"
            f"{settings.POSTGRES_PORT}/"
            f"{settings.POSTGRES_DB}"
        )

    def get_session(self) -> Session:
        return self.SessionLocal()

db = Database()

