"""Regression tests for the lightweight column auto-migration in init_db.

A database created by an older version of the app is missing columns that were
later added to the models. `create_all` never alters existing tables, so without
a migration step every query that selects the model raises "no such column",
returning a 500 and leaving the UI empty. `_add_missing_columns` backfills them.
"""
import sqlite3
import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db import Base, _add_missing_columns
from app.models import Lead

# An intentionally outdated `leads` table: it predates fit_score / intent_score /
# priority_score / summary / fit_reasons and the lead_contacts LinkedIn columns.
_OLD_LEADS_DDL = """
CREATE TABLE leads (
  id VARCHAR(64) PRIMARY KEY, place_id VARCHAR(128), name VARCHAR(256) NOT NULL,
  address TEXT, city VARCHAR(128), state VARCHAR(64), country VARCHAR(64),
  phone VARCHAR(32), phone_normalized VARCHAR(32), phone_type VARCHAR(32),
  website TEXT, place_types JSON NOT NULL, employee_count_min BIGINT,
  employee_count_max BIGINT, revenue_range VARCHAR(64), location_count BIGINT,
  status VARCHAR(16) NOT NULL, notes TEXT, source VARCHAR(32) NOT NULL,
  enrichment_source VARCHAR(64), scraped_at BIGINT, assigned_to_user_id VARCHAR(64),
  last_touched_at BIGINT, last_touched_by_user_id VARCHAR(64), score BIGINT,
  score_breakdown JSON NOT NULL, matched_segment_ids JSON NOT NULL,
  created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
)
"""


@pytest.mark.asyncio
async def test_migration_backfills_missing_columns(tmp_path):
    db_path = tmp_path / "old.db"

    con = sqlite3.connect(db_path)
    con.execute(_OLD_LEADS_DDL)
    now = int(time.time())
    con.execute(
        "INSERT INTO leads (id, name, place_types, status, source, "
        "score_breakdown, matched_segment_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "Acme", "[]", "new", "test", "{}", "[]", now, now),
    )
    con.commit()
    con.close()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        # Before the migration, selecting the model fails on the missing column.
        async with engine.begin() as conn:
            with pytest.raises(Exception):
                await conn.exec_driver_sql("SELECT fit_score FROM leads")

        # Mirror init_db: create_all adds genuinely new tables, then the
        # migration backfills missing columns on pre-existing tables.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)

        session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
        async with session_factory() as session:
            lead = (
                await session.execute(
                    select(Lead).options(
                        selectinload(Lead.emails),
                        selectinload(Lead.contacts),
                        selectinload(Lead.signals),
                    )
                )
            ).scalars().one()
            # Nullable additions default to NULL; NOT NULL JSON columns are
            # backfilled to their model default so serialization succeeds.
            assert lead.fit_score is None
            assert lead.intent_score is None
            assert lead.priority_score is None
            assert lead.fit_reasons == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "old.db"
    con = sqlite3.connect(db_path)
    con.execute(_OLD_LEADS_DDL)
    con.commit()
    con.close()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)
        # Running again must be a no-op (no duplicate-column errors).
        async with engine.begin() as conn:
            await conn.run_sync(_add_missing_columns)
    finally:
        await engine.dispose()
