#!/bin/sh
# Docker 部署脚本（流水线 deploy@agent 在仓库根目录内调用）
# 前置：ECS 已安装 docker + compose 插件；/opt/ontology 已 clone（凭据与镜像无关）
set -eu

cd "$(dirname "$0")/../.."
log() { echo "[deploy] $*"; }
# 与 docker-compose.yml 的默认前端端口保持一致。
WEB_PORT="${WEB_PORT:-8088}"
APP_BUILD_REVISION="$(cat .deployment-revision 2>/dev/null || echo unknown)"
export APP_BUILD_REVISION

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[deploy] 错误：缺少 docker compose 插件"; exit 1
fi

if [ "${DEPLOY_PREBUILT_FRONTEND:-0}" = "1" ]; then
  DC="$DC -f docker-compose.yml -f compose.prebuilt.yml"
fi

sh "$(dirname "$0")/docker-build.sh"
# Use SQLite's backup API so live WAL transactions are included. Keep snapshots
# in the existing persistent data volume before recreating any running backend.
if [ -n "$($DC ps -q backend)" ]; then
  log "更新前备份现有 SQLite 数据（快照保存在持久化 data/deployment-backups）"
  $DC exec -T backend python - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

root = Path('/app/backend')
backup = root / 'data' / 'deployment-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
sources = [p for p in root.glob('*') if p.is_file() and p.suffix in ('.db', '.sqlite', '.sqlite3')]
data = root / 'data'
if data.exists():
    sources += [p for p in data.rglob('*') if p.is_file()
                and p.suffix in ('.db', '.sqlite', '.sqlite3')
                and 'deployment-backups' not in p.relative_to(data).parts]
for path in sources:
    target = backup / path.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.touch(mode=0o600, exist_ok=False)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(target) as destination:
            source.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup integrity check failed')
print('SQLite snapshots verified:', len(sources))
PY
fi
log "启动/更新容器"
$DC up -d
log "等待后端就绪（经 nginx:$WEB_PORT 探测）"
i=0
until curl -sf "http://127.0.0.1:$WEB_PORT/api/v1/scene-registry" >/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    log "健康检查超时，输出后端日志："
    $DC logs --tail 50 backend
    exit 1
  fi
  sleep 2
done
# 日常部署只更新应用，不重置业务记录或覆盖已有场景配置。
# 初次搭建演示环境时可显式设置 SEED_DEMO_DATA=1。
if [ "${SEED_DEMO_DATA:-0}" = "1" ]; then
  log "按显式配置初始化演示数据"
  $DC exec -T backend python scripts/seed_mil_demo.py
  $DC exec -T backend python scripts/seed_drone_demo.py
fi
log "初始化独立客户演示并验证数据库技能（保留原有业务数据和模型密钥）"
DEMO_ARGS="--install"
if [ "${CHECK_AI:-0}" = "1" ]; then
  log "CHECK_AI=1：同时强制验证 DeepSeek/兼容模型的工具调用闭环"
  DEMO_ARGS="$DEMO_ARGS --check-ai"
else
  log "未启用 CHECK_AI；未配置模型时仍允许完成基础部署，AI 状态写入演示报告"
fi
$DC exec -T -e DEMO_DEPLOY_REVISION="$(cat .deployment-revision 2>/dev/null || echo local)" backend python scripts/customer_demo.py $DEMO_ARGS
log "部署完成：http://<ECS-IP>:$WEB_PORT （数据持久化在 /opt/ontology/data/）"
