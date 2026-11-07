"""Движок и фабрика сессий."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(db_url: str, echo: bool = False, serverless: bool = False) -> AsyncEngine:
    if serverless:
        # Функция может «заснуть» между запросами вместе с открытыми соединениями, а пулер
        # Neon (pgbouncer) не поддерживает подготовленные запросы — поэтому без пула и кэша.
        kwargs: dict = {"poolclass": NullPool}
        if db_url.startswith("postgresql"):
            kwargs["connect_args"] = {"statement_cache_size": 0}
        engine = create_async_engine(db_url, echo=echo, **kwargs)
    else:
        engine = create_async_engine(db_url, echo=echo, pool_pre_ping=True)

    if db_url.startswith("sqlite"):
        # SQLite по умолчанию не проверяет внешние ключи — включаем, иначе ON DELETE CASCADE
        # молча не сработает и в базе останутся висячие строки.
        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - тонкий слой над драйвером
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
