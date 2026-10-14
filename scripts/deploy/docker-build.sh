#!/bin/sh
# Docker 镜像构建（编译检查即在此完成；构建失败则中止，旧容器不受影响）
set -eu
cd "$(dirname "$0")/../.."

if ! command -v docker >/dev/null 2>&1; then
  echo "[build] 错误：docker 未安装"; exit 1
fi
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[build] 错误：缺少 docker compose 插件"; exit 1
fi

echo "[build] 构建镜像（含前端 vite build 编译检查）"
attempt=1
while ! $DC build; do
  if [ "$attempt" -ge 3 ]; then
    echo "[build] 镜像构建连续失败 3 次；请检查 ECS 的 Docker 镜像源和网络（最近一次可能是 registry 502）"
    exit 1
  fi
  echo "[build] 镜像源暂时不可用，60 秒后重试（第 $((attempt + 1))/3 次）"
  attempt=$((attempt + 1))
  sleep 60
done
echo "[build] 镜像构建通过"
