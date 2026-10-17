"""Copy a stopped platform database into an empty target without overwriting rows."""
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import MetaData, func, select


class MigrationValidationError(ValueError):
    """Validation messages contain schema names only, never row values or credentials."""


def backup_sqlite(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise MigrationValidationError("Source SQLite file does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally replacing the source or a prior backup.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise MigrationValidationError("SQLite integrity check failed")
                if dst.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise MigrationValidationError("SQLite contains broken foreign key references")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _digest(connection, table, names):
    # Database collations can order primary keys differently; compare row multisets.
    checksum = 0
    statement = select(*(table.c[n] for n in names))
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, bytes):
            return {"bytes_hex": value.hex()}
        raise TypeError("Unsupported migration value type")
    for row in connection.execute(statement).yield_per(500):
        value = json.dumps(list(row), ensure_ascii=False, sort_keys=True,
                           default=encode, separators=(",", ":")).encode()
        checksum = (checksum + int.from_bytes(hashlib.sha256(value).digest())) % (1 << 256)
    return f"{checksum:064x}"


def migrate_platform(source, target, metadata, *, apply=False):
    if source.dialect.name != "sqlite":
        raise MigrationValidationError("Migration source must be SQLite")
    if source.url == target.url:
        raise MigrationValidationError("Source and target must be different databases")
    source_meta = MetaData()
    source_meta.reflect(bind=source)
    unknown = set(source_meta.tables) - set(metadata.tables) - {"alembic_version"}
    if unknown:
        raise MigrationValidationError("Unmapped source tables: " + ", ".join(sorted(unknown)))
    existing_meta = MetaData()
    existing_meta.reflect(bind=target)
    with target.connect() as conn:
        for table in existing_meta.tables.values():
            if conn.scalar(select(func.count()).select_from(table)):
                raise MigrationValidationError("Target must be empty; non-empty table: " + table.name)
    plan = {}
    with source.connect() as conn:
        for table in metadata.sorted_tables:
            if table.name not in source_meta.tables:
                continue
            old = source_meta.tables[table.name]
            extra = set(old.c.keys()) - set(table.c.keys())
            if extra:
                raise MigrationValidationError("Unmapped columns in " + table.name + ": " + ", ".join(sorted(extra)))
            # Decode SQLite values using the platform's declared JSON/date/bool types.
            for col in old.c:
                col.type = table.c[col.name].type
            plan[table.name] = conn.scalar(select(func.count()).select_from(old))
    if not apply:
        return {"applied": False, "rows": plan}
    # MySQL DDL commits implicitly. Failed imports may leave empty tables, never deleted data.
    metadata.create_all(target)
    with source.connect() as src, target.begin() as dst:
        for table in metadata.sorted_tables:
            if table.name not in plan:
                continue
            old = source_meta.tables[table.name]
            result = src.execute(select(old)).mappings()
            while batch := result.fetchmany(500):
                dst.execute(table.insert(), [dict(row) for row in batch])
            count = dst.scalar(select(func.count()).select_from(table))
            names = sorted(old.c.keys())
            if count != plan[table.name] or _digest(src, old, names) != _digest(dst, table, names):
                raise MigrationValidationError("Row count/content mismatch in " + table.name)
    return {"applied": True, "rows": plan}
