"""Run from backend: python -m scripts.migrate_platform_mysql --help."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from app.config import settings
from app.db_engine import create_platform_engine
from app.database import Base
import app.models  # noqa: F401
from app.services.platform_migration import backup_sqlite, migrate_platform


def main():
    parser = argparse.ArgumentParser(description="MySQL read-only check or SQLite migration into an empty MySQL database")
    parser.add_argument("--check", action="store_true", help="Read-only connection/version/table-name check")
    parser.add_argument("--source", type=Path, help="Existing platform SQLite database; never the MQTT/demo database")
    parser.add_argument("--backup-dir", type=Path, default=Path("./data/migration-backups"))
    parser.add_argument("--apply", action="store_true", help="Import into an empty target; default is dry run")
    args = parser.parse_args()
    target = create_platform_engine(settings)
    if target.dialect.name != "mysql":
        parser.error("Configure DATABASE_BACKEND=mysql and MYSQL_* first")
    try:
        if args.check:
            if args.apply or args.source:
                parser.error("--check cannot be combined with --source or --apply")
            with target.connect() as conn:
                print(json.dumps({"version": conn.scalar(text("SELECT VERSION()")),
                                  "database": conn.scalar(text("SELECT DATABASE()")),
                                  "tables": inspect(conn).get_table_names()}, ensure_ascii=False))
            return
        if not args.source:
            parser.error("--source is required; stop platform writes before taking the snapshot")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = backup_sqlite(args.source, args.backup_dir / f"ontology-{stamp}.sqlite3")
        source = create_engine("sqlite:///" + str(snapshot))
        try:
            result = migrate_platform(source, target, Base.metadata, apply=args.apply)
            print(json.dumps({"backup": str(snapshot), **result}, ensure_ascii=False, indent=2))
        finally:
            source.dispose()
    except Exception as exc:
        # Drivers can include row values, credentials or database URLs in errors.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "message": "Migration/check failed; no automatic cutover. Source remains unchanged. Inspect securely on the server."}))
        raise SystemExit(1)
    finally:
        target.dispose()


if __name__ == "__main__":
    main()
