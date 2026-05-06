from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, future=True, echo=False)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_scan_logs_columns(conn)


async def _ensure_scan_logs_columns(conn) -> None:
    required_columns = {
        "frame_width": "INTEGER DEFAULT 0",
        "frame_height": "INTEGER DEFAULT 0",
        "bbox_x1": "FLOAT",
        "bbox_y1": "FLOAT",
        "bbox_x2": "FLOAT",
        "bbox_y2": "FLOAT",
        "bbox_confidence": "FLOAT",
    }
    result = await conn.exec_driver_sql("PRAGMA table_info(scan_logs)")
    existing = {row[1] for row in result.fetchall()}
    for column_name, ddl in required_columns.items():
        if column_name in existing:
            continue
        await conn.exec_driver_sql(f"ALTER TABLE scan_logs ADD COLUMN {column_name} {ddl}")
