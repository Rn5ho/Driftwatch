from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.db_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Columns added after the initial release. create_all never ALTERs existing
# tables, so existing SQLite files get them via ADD COLUMN at startup.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "forecasts": [
        ("stage", "VARCHAR NOT NULL DEFAULT 'analysis'"),
        ("shadow", "BOOLEAN NOT NULL DEFAULT 0"),
        ("regime", "VARCHAR NOT NULL DEFAULT ''"),
    ],
    "events": [
        ("triage_relevant", "BOOLEAN"),
        ("attempts", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


async def _migrate(conn) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {
            row[1]
            for row in (await conn.exec_driver_sql(f"PRAGMA table_info({table})")).fetchall()
        }
        for name, ddl in columns:
            if name not in existing:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


async def init_db() -> None:
    from app import models  # noqa: F401  (register tables before create_all)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)


@asynccontextmanager
async def session_scope():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
