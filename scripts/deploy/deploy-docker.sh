#!/bin/sh
# Docker 部署脚本（流水线 deploy@agent 在仓库根目录内调用）
# 前置：ECS 已安装 docker + compose 插件；/opt/ontology 已 clone（凭据与镜像无关）
set -eu

cd "$(dirname "$0")/../.."
log() { echo "[deploy] $*"; }
# 与 docker-compose.yml 的默认前端端口保持一致。
WEB_PORT="${WEB_PORT:-8088}"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[deploy] 错误：缺少 docker compose 插件"; exit 1
fi

sh "$(dirname "$0")/docker-build.sh"
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
log "初始化独立客户演示并验证数据库技能与真实模型问答（保留原有业务数据和模型密钥）"
$DC exec -T -e DEMO_DEPLOY_REVISION="$(cat .deployment-revision 2>/dev/null || echo local)" backend python scripts/customer_demo.py --install --check-ai
log "部署完成：http://<ECS-IP>:$WEB_PORT （数据持久化在 /opt/ontology/data/）"
