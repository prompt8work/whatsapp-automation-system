"""Database engine and sessions (ADR-008).

On Vercel every function instance is short-lived, so we do NOT keep our own pool:
`NullPool` opens a connection per Unit of Work and the external pooler
(Neon / Supabase, transaction mode) does the real pooling.
`prepare_threshold=None` disables server-side prepared statements, which transaction-mode
poolers cannot route correctly.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
        echo=echo,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
