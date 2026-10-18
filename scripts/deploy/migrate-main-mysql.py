#!/usr/bin/env python3
"""Run on ECS using an interactive password or a local mysql_config_editor login path."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description='Safely migrate the running SQLite platform into a NEW local MySQL database')
    parser.add_argument('--apply', action='store_true', help='Required to create a dedicated database/user and switch the backend')
    parser.add_argument('--with-demo', action='store_true', help='Create two NEW synthetic demo scenes after a successful migration')
    parser.add_argument('--database', default='ontology_platform_' + time.strftime('%Y%m%d'))
    parser.add_argument('--reuse-empty-database', action='store_true',
                        help='Reuse an existing target only if the migration verifies every existing table is empty')
    parser.add_argument('--admin-user', default='remote_root')
    parser.add_argument('--admin-login-path', help='ECS-local mysql_config_editor login path; avoids exposing a password')
    parser.add_argument('--mysql-host', default='172.22.22.19', help='MySQL address reachable from the backend container (ECS private IP)')
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--web-port', type=int, default=8088)
    args = parser.parse_args()
    if not args.apply:
        parser.error('Read docs first, then pass --apply; this script never clears an existing database')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,50}', args.database):
        parser.error('Database name must contain only ASCII letters, digits and underscores')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.mysql_host) or not 1 <= args.port <= 65535:
        parser.error('Invalid MySQL host or port')
    if args.admin_login_path and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', args.admin_login_path):
        parser.error('Invalid MySQL login path name')
    if not shutil.which('mysql'):
        parser.error('Install the MySQL command-line client on ECS first')
    os.chdir(ROOT)
    lock = open(ROOT / '.deploy.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('Another deployment holds the lock. Wait for it to finish; do not delete the lock file')
    compose = ['docker', 'compose']
    run([*compose, 'version'], stdout=subprocess.DEVNULL)
    info_code = ('from pathlib import Path; import json; from app.config import settings; '
                 'from app.db_engine import database_url; u=database_url(settings); '
                 'print(json.dumps({"backend":u.get_backend_name(), "path":str(Path(u.database).resolve())}))')
    info = json.loads(subprocess.check_output(['docker', 'exec', 'ontology-backend', 'python', '-c', info_code], text=True))
    if info['backend'] != 'sqlite' or not info['path'].startswith('/app/backend/data/'):
        parser.error('Expected a running SQLite backend with its main database in the persistent data volume')
    password = None if args.admin_login_path else getpass.getpass(
        'MySQL administrator password (entered only on ECS, not printed): ')
    admin_env = {**os.environ, 'MYSQL_HISTFILE': '/dev/null'}
    if password is not None:
        admin_env['MYSQL_PWD'] = password
    admin_command = ['mysql']
    if args.admin_login_path:
        admin_command.append(f'--login-path={args.admin_login_path}')
    else:
        admin_command.append(f'--user={args.admin_user}')
    def sql(statement):
        result = run([*admin_command, '--protocol=tcp', '--host=127.0.0.1', f'--port={args.port}',
                      '--batch', '--skip-column-names'],
                     input=statement, capture_output=True, env=admin_env)
        return result.stdout.strip()
    try:
        version = sql('SELECT VERSION();')
        if not version.startswith('8.'):
            parser.error('This migration has been verified with MySQL 8; detected another major version')
        database_exists = sql(
            f"SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{args.database}';") != '0'
        if database_exists and not args.reuse_empty_database:
            parser.error('Target database already exists. Choose a NEW name or explicitly reuse an empty target')
        app_user = 'ontology_' + secrets.token_hex(5)
        app_password = secrets.token_urlsafe(32)
        create_database = (f"CREATE DATABASE `{args.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n"
                           if not database_exists else "")
        sql(create_database + f"CREATE USER '{app_user}'@'%' IDENTIFIED BY '{app_password}';\n"
            f"GRANT ALL PRIVILEGES ON `{args.database}`.* TO '{app_user}'@'%';")
    except subprocess.CalledProcessError:
        print('MySQL administration failed. Backend was not stopped. Check username, password and database/user creation permissions locally.')
        return 1
    finally:
        admin_env.pop('MYSQL_PWD', None)
        password = None
    backups = ROOT / 'data' / 'mysql-migration'
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = ROOT / '.env'
    original_bytes = original.read_bytes() if original.exists() else None
    backup = backups / ('config-before-' + time.strftime('%Y%m%dT%H%M%S') + '.env')
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(original_bytes or b'')
    descriptor, temp_name = tempfile.mkstemp(prefix='mysql-config-', suffix='.env', dir=backups)
    prepared = Path(temp_name)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(original_bytes or b'')
        stream.write(('\nDATABASE_BACKEND=mysql\nMYSQL_HOST=' + args.mysql_host + '\nMYSQL_PORT=' + str(args.port)
                      + '\nMYSQL_DATABASE=' + args.database + '\nMYSQL_USER=' + app_user
                      + '\nMYSQL_PASSWORD=' + app_password + '\nMYSQL_SSL_CA=\n').encode())
    target = [*compose, '--env-file', str(prepared)]
    stopped = False
    switched = False
    try:
        # Test container-to-MySQL connectivity before stopping any service.
        run([*target, 'run', '--rm', '--no-deps', '--entrypoint', 'python', 'backend',
             '-m', 'scripts.migrate_platform_mysql', '--check'])
        print('MySQL preflight passed. Stopping only ontology backend for a consistent migration.', flush=True)
        run([*compose, 'stop', 'backend']); stopped = True
        run([*target, 'run', '--rm', '--no-deps', '--entrypoint', 'python', 'backend',
             '-m', 'scripts.migrate_platform_mysql', '--source', info['path'], '--apply'])
        os.replace(prepared, original)
        switched = True
        run([*compose, 'up', '-d', '--no-deps', '--no-build', 'backend'])
        # Nginx resolves the backend container address at configuration load time.
        run([*compose, 'exec', '-T', 'web', 'nginx', '-s', 'reload'])
        health = f'http://127.0.0.1:{args.web_port}/api/v1/scene-registry'
        for attempt in range(60):
            try:
                with urllib.request.urlopen(health, timeout=3) as response:
                    if response.status == 200:
                        break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Backend health check failed')
        check = ('from sqlalchemy import text; from app.database import engine; '
                 'assert engine.dialect.name=="mysql"; '
                 'c=engine.connect(); print("Verified MySQL database:", c.scalar(text("SELECT DATABASE()"))); c.close()')
        run(['docker', 'exec', 'ontology-backend', 'python', '-c', check])
        if args.with_demo:
            run(['docker', 'exec', 'ontology-backend', 'python', '-m', 'scripts.seed_scene_demo'])
        print('SUCCESS: MySQL main storage is active. Original SQLite and configuration backup are retained.')
        print('Configuration backup:', backup)
        return 0
    except Exception as exc:
        print('Migration/switch failed:', type(exc).__name__, '. Restoring the previous backend configuration.')
        if switched:
            if original_bytes is None:
                original.unlink(missing_ok=True)
            else:
                original.write_bytes(original_bytes); original.chmod(0o600)
        if stopped:
            run([*compose, 'up', '-d', '--no-deps', '--no-build', 'backend'])
            run([*compose, 'exec', '-T', 'web', 'nginx', '-s', 'reload'])
        print('New MySQL database/user retained for inspection; no existing database was deleted.')
        return 1
    finally:
        prepared.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
