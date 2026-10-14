"""Run inside the application container; credentials stay in its database.

python scripts/customer_demo.py --install --check-ai
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import engine, SessionLocal
from app.services.customer_demo import install_customer_demo, verify_customer_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--check-ai", action="store_true")
    args = parser.parse_args()
    if args.install and engine.url.get_backend_name() == "sqlite":
        source = Path(engine.url.database).resolve()
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / ("before-customer-demo-" + datetime.utcnow().strftime("%Y%m%dT%H%M%S%f") + ".db")
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        target.chmod(0o600)
    with SessionLocal() as db:
        if args.install:
            install_customer_demo(db)
        report = verify_customer_demo(db, check_ai=args.check_ai)
        report["revision"] = os.environ.get("DEMO_DEPLOY_REVISION", "local")
    output = Path("./data/customer-demo-report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # Only counts and sanitized model diagnostics; never log configuration objects.
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
