"""Exercise cutover/rollback without needing production credentials or a server."""
import importlib.util
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('fail_import', [False, True])
def test_cutover_preserves_config_and_rolls_back_on_failed_import(tmp_path, monkeypatch, capsys, fail_import):
    script = Path(__file__).resolve().parents[2] / 'scripts/deploy/migrate-main-mysql.py'
    spec = importlib.util.spec_from_file_location('mysql_switch_test', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / '.env').write_text('SECRET_KEY=keep-existing-key\n')
    monkeypatch.setattr('sys.argv', [str(script), '--apply', '--database', 'test_platform'])
    monkeypatch.setattr(module.getpass, 'getpass', lambda prompt: 'administrator-private-test')
    monkeypatch.setattr(module.shutil, 'which', lambda command: '/usr/bin/mysql')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k: json.dumps({'backend': 'sqlite', 'path': '/app/backend/data/ontology.db'}))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert 'administrator-private-test' not in ' '.join(command)
        if command[0] == 'mysql':
            assert kwargs['env']['MYSQL_PWD'] == 'administrator-private-test'
            sql = kwargs['input']
            return SimpleNamespace(stdout='8.4.0' if sql.startswith('SELECT VERSION') else '0' if sql.startswith('SELECT COUNT') else '')
        if fail_import and '--apply' in command:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(module, 'run', run)
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: nullcontext(SimpleNamespace(status=200)))
    assert module.main() == (1 if fail_import else 0)
    text = (tmp_path / '.env').read_text()
    assert 'SECRET_KEY=keep-existing-key' in text
    assert ('DATABASE_BACKEND=mysql' in text) is (not fail_import)
    assert 'administrator-private-test' not in capsys.readouterr().out
    assert all('administrator-private-test' not in p.read_text() for p in tmp_path.rglob('*.env'))
