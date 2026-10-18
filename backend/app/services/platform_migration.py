"""Copy a stopped platform database into an empty target without overwriting rows."""
import hashlib
import json
import os
import sqlite3
import math
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import JSON, MetaData, func, select


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
    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        # MySQL JSON may normalize 1.0 to 1. These values compare equal in JSON
        # semantics and in Python, so the migration verifier should do the same.
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return int(value)
        return value
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, bytes):
            return {"bytes_hex": value.hex()}
        raise TypeError("Unsupported migration value type")
    for row in connection.execute(statement).yield_per(500):
        value = json.dumps(canonical(list(row)), ensure_ascii=False, sort_keys=True,
                           default=encode, separators=(",", ":")).encode()
        checksum = (checksum + int.from_bytes(hashlib.sha256(value).digest())) % (1 << 256)
    return f"{checksum:064x}"


def _values_equivalent(left, right, depth=0):
    if depth >= 20:
        return left == right
    if isinstance(left, (int, float)) and not isinstance(left, bool) \
            and isinstance(right, (int, float)) and not isinstance(right, bool):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _values_equivalent(left[key], right[key], depth + 1) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _values_equivalent(litem, ritem, depth + 1) for litem, ritem in zip(left, right))
    return left == right


def _difference_kind(left, right, depth=0):
    """Describe structure/type of a difference without returning either value."""
    if _values_equivalent(left, right):
        return None
    if depth >= 8:
        return "nested value"
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return "object keys"
        for key in sorted(left):
            if kind := _difference_kind(left[key], right[key], depth + 1):
                return "object child > " + kind
        return "object value"
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return "array length"
        for litem, ritem in zip(left, right):
            if kind := _difference_kind(litem, ritem, depth + 1):
                return "array item > " + kind
        return "array value"
    if isinstance(left, (int, float)) and not isinstance(left, bool) \
            and isinstance(right, (int, float)) and not isinstance(right, bool):
        return "numeric value"
    if type(left) is not type(right):
        return f"type {type(left).__name__}/{type(right).__name__}"
    return type(left).__name__ + " value"


def _column_difference_summary(source_conn, source_table, target_conn, target_table, column):
    primary_keys = [c.name for c in source_table.primary_key.columns]
    if not primary_keys:
        return "unkeyed values"
    names = [*primary_keys, column]
    source_rows = source_conn.execute(select(*(source_table.c[n] for n in names))).all()
    target_rows = target_conn.execute(select(*(target_table.c[n] for n in names))).all()
    source_map = {tuple(row[:-1]): row[-1] for row in source_rows}
    target_map = {tuple(row[:-1]): row[-1] for row in target_rows}
    if set(source_map) != set(target_map):
        return "primary-key membership"
    kinds = []
    for key in source_map:
        kind = _difference_kind(source_map[key], target_map[key])
        if kind and kind not in kinds:
            kinds.append(kind)
    return ", ".join(kinds[:5]) or "serialized representation"


def _json_column_equivalent(source_conn, source_table, target_conn, target_table, column):
    primary_keys = [c.name for c in source_table.primary_key.columns]
    if not primary_keys:
        return False
    names = [*primary_keys, column]
    source_rows = source_conn.execute(select(*(source_table.c[n] for n in names))).all()
    target_rows = target_conn.execute(select(*(target_table.c[n] for n in names))).all()
    source_map = {tuple(row[:-1]): row[-1] for row in source_rows}
    target_map = {tuple(row[:-1]): row[-1] for row in target_rows}
    return set(source_map) == set(target_map) and all(
        _values_equivalent(source_map[key], target_map[key]) for key in source_map)


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
            if count != plan[table.name]:
                raise MigrationValidationError("Row count mismatch in " + table.name)
            if _digest(src, old, names) != _digest(dst, table, names):
                differing = []
                for name in names:
                    if _digest(src, old, [name]) == _digest(dst, table, [name]):
                        continue
                    if isinstance(table.c[name].type, JSON) and _json_column_equivalent(
                            src, old, dst, table, name):
                        continue
                    differing.append(name)
                if not differing:
                    continue
                details = [name + " (" + _column_difference_summary(src, old, dst, table, name) + ")"
                           for name in differing]
                raise MigrationValidationError(
                    "Content mismatch in " + table.name + " columns: " + ", ".join(details))
    return {"applied": True, "rows": plan}
