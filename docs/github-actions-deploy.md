# GitHub 自动部署到阿里云 ECS

当前流程：推送到 `main` → 同步代码到 ECS 的 `/opt/ontology` → 在 ECS 构建 Docker 镜像 → 更新容器 → 检查服务 → 执行现有演示数据初始化。
构建失败不会更新运行中的容器；更新后健康检查失败会报告失败，但暂不自动回滚。请在首次部署前备份数据库。

## 1. 在 Workbench 检查服务器

登录原来的 ECS，执行：

```sh
cd /opt/ontology
docker compose version
docker compose ps
command -v rsync
command -v curl
command -v flock
```

缺少 rsync、curl 或 flock 时需要安装对应系统软件包（flock 通常属于 util-linux）。部署账号必须能写入 `/opt/ontology` 并运行 Docker。保持原有目录与 Compose 项目名，避免切换到另一套数据目录。现有数据库位于 `/opt/ontology/data`。

## 2. 创建专用 SSH 密钥

在 Workbench 中使用将用于部署的 Linux 账号执行：

```sh
umask 077
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C ontology-github-actions -f ~/.ssh/ontology_actions -N ''
cat ~/.ssh/ontology_actions.pub >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

如果提示文件已存在，不要覆盖，先确认是否已经创建过这把密钥。
执行 `whoami` 查看登录账号，它就是下面的 `ECS_USER`。执行 `cat ~/.ssh/ontology_actions`，将完整输出直接保存到 GitHub 的 `ECS_SSH_KEY` Secret；不要发到聊天或提交到仓库。具有 Docker 权限的账号通常有很高的服务器权限，应使用专用部署账号和密钥。

## 3. 配置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions → Secrets → New repository secret**：

| 名称 | 内容 |
| --- | --- |
| `ECS_HOST` | ECS 公网 IP 或可从公网访问的域名 |
| `ECS_USER` | 上面 `whoami` 显示的 Linux 用户名 |
| `ECS_SSH_PORT` | SSH 端口，通常为 `22`，不填默认 22 |
| `ECS_SSH_KEY` | 专用私钥的完整内容，包括 BEGIN/END 行 |
| `ECS_KNOWN_HOSTS` | 服务器 SSH 主机公钥，格式见下文 |

在 Workbench 执行以下命令得到主机公钥（这是公钥，不是私钥）：

```sh
cat /etc/ssh/ssh_host_ed25519_key.pub
```

假设输出为 `ssh-ed25519 AAAA... root@host`，公网 IP 为 `1.2.3.4`，则 `ECS_KNOWN_HOSTS` 填写：

```text
1.2.3.4 ssh-ed25519 AAAA...
```

如果端口不是 22，第一项改成 `[1.2.3.4]:端口`。域名部署则第一项使用同一个域名。这样流水线会验证服务器身份。

ECS 安全组和系统防火墙需要允许 GitHub 托管运行器访问 SSH 端口。Workbench 能登录不代表 GitHub 能连接公网 SSH。托管运行器 IP 会变化；如不希望开放公网 SSH，可改为 ECS 自托管运行器方案，不能直接沿用本流水线。

## 4. 开启并试运行

1. 停止旧 Gitee Go 自动部署，避免两边同时覆盖 `/opt/ontology`。
2. 备份 `/opt/ontology/data`，确认已有 `.env` 的端口与当前服务一致。
3. GitHub **Settings → Environments** 创建 `production`，可将部署分支限制为 `main`。如果设置人工审批，每次发布会等待审批。
4. **Settings → Secrets and variables → Actions → Variables** 新增仓库变量 `DEPLOY_ENABLED`，值为 `true`。
5. 在 **Actions → Deploy to Alibaba Cloud ECS → Run workflow** 中选择 `main` 并执行。
6. 成功后访问生产网站确认；之后每次推送或合并到 `main` 都会部署。

尚未设置 `DEPLOY_ENABLED=true` 时，部署任务会跳过。设为 `false` 可停止后续自动部署，但不会停止已经开始的任务。

同步会删除生产目录中源码已经移除的文件，但保留 `.git`、`.env`、`.env.*`、数据库、上传目录和指定运行目录。服务器若有其他需要保留的本地文件，先补充流水线的 rsync 排除规则。
无需更改 ECS 现有 Git remote，也无需让 ECS 自行拉取 GitHub：源码由 Actions 传输。

## 常见失败

- `Connection timed out`：检查公网 IP、SSH 端口、安全组和防火墙。
- `Permission denied (publickey)`：检查用户名、私钥以及对应用户的 `authorized_keys`。
- `Host key verification failed`：检查 `ECS_KNOWN_HOSTS` 的 IP/域名、端口和公钥。
- Docker 权限错误：部署账号不能访问 Docker，需要在 ECS 配置权限。
- 构建失败：查看 Actions 输出；ECS 仍需要能访问 Docker 镜像、npm 和 Python 包镜像站。
- 健康检查失败：在 Workbench 执行 `cd /opt/ontology && docker compose logs --tail 100`。已有部署脚本默认检查 8088 端口；如 `.env` 配置其他端口，应确保脚本与 Compose 使用同一端口。
