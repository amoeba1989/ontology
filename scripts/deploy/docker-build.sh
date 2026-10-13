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
$DC build
echo "[build] 镜像构建通过"
