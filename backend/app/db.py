import json

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        if "sqlite" in settings.database_url:
            await conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
        # `create_all` only creates missing *tables*; it never alters existing
        # ones. When new columns are added to a model, a database created by an
        # older version of the app is left without them, and every query that
        # selects the model fails with "no such column" (a 500 that surfaces in
        # the UI as empty/blank data). Backfill any missing columns here.
        await conn.run_sync(_add_missing_columns)


def _sql_literal(value) -> str:
    """Render a Python value as a SQL literal usable in a DEFAULT clause."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return "'" + json.dumps(value).replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _column_default_literal(column) -> str | None:
    """Best-effort SQL literal for a column's default, for ALTER TABLE backfill.

    Returns ``None`` when no constant default can be derived (the column is then
    added as nullable so existing rows simply get ``NULL``).
    """
    default = column.default
    if default is None:
        return None
    if getattr(default, "is_scalar", False):
        return _sql_literal(default.arg)
    if getattr(default, "is_callable", False):
        fn = default.arg
        for args in ((), (None,)):
            try:
                return _sql_literal(fn(*args))
            except TypeError:
                continue
    return None


def _add_missing_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    dialect = sync_conn.dialect
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            col_type = column.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            default_sql = _column_default_literal(column)
            if default_sql is not None:
                ddl += f" DEFAULT {default_sql}"
            # SQLite (and good practice generally) only allows NOT NULL on a new
            # column when a default backfills existing rows.
            if not column.nullable and default_sql is not None:
                ddl += " NOT NULL"
            sync_conn.execute(text(ddl))


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
