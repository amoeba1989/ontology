# syntax=docker/dockerfile:1

# ── 阶段 1：前端构建（编译检查也在此步完成，失败则整个构建中止） ──
FROM node:20-alpine AS frontend-build
WORKDIR /src/frontend
# 国内构建机直连 npm registry 极慢，统一走 npmmirror
ENV npm_config_registry=https://registry.npmmirror.com
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
# 固定 pnpm 主版本，并把依赖层放在构建版本之前。这样每次提交只重新编译，
# 只有 package/lock 文件变化时才重新下载全部依赖。
RUN npm install -g pnpm@10 && pnpm install --frozen-lockfile
COPY frontend/ ./
ARG APP_BUILD_REVISION=unknown
ENV GITHUB_SHA=$APP_BUILD_REVISION
RUN pnpm exec vite build

# ── 阶段 2：nginx 托管前端静态资源并转发 API ──
FROM nginx:1.27-alpine AS web
COPY --from=frontend-build /src/frontend/dist /usr/share/nginx/html
COPY scripts/deploy/nginx-container.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

# ── 阶段 3：后端 FastAPI + uvicorn ──
FROM python:3.11-slim AS backend
WORKDIR /app/backend
# 直连 pypi.org 只有 17kB/s，依赖回溯会多花十几分钟，改走阿里云镜像
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY VERSION /app/VERSION
COPY backend/ .
# SQLite 数据与演示库统一放 /app/backend/data（volume 持久化，镜像更新不丢）
ENV DATABASE_URL=sqlite:///./data/ontology.db \
    DEMO_DB_DIR=/app/backend/data
RUN mkdir -p /app/backend/data
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
