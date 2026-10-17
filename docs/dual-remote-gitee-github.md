# Gitee + GitHub 双远程管理

一台开发机把同一个仓库同时推到 Gitee 和 GitHub，两边各自跑自己的流水线：

| 远程 | 地址 | 流水线 | 适用场景 |
| --- | --- | --- | --- |
| `gitee` | `git@gitee.com:amoeba1989/ontology.git` | Gitee Go（`.workflow/流水线-202610131624.yml`） | 单位网络访问不到 GitHub 时的日常推送与部署 |
| `github` | `git@github.com:<你的用户名>/<仓库名>.git` | GitHub Actions（`.github/workflows/deploy.yml`） | 家里/能连 GitHub 的网络，带 pytest + 前端构建校验 |

两条流水线**都会部署同一台 ECS 的 `/opt/ontology`**，靠同一把文件锁串行执行。因为两边推的是同一份提交（SHA 相同），所以谁最后拿到锁谁收尾，最终线上状态一致。

## 1. 分支约定

统一使用 `master`。Gitee 仓库默认分支就是 `master`，GitHub 侧把 Actions 的触发分支也改成了 `master`（见 `.github/workflows/deploy.yml`）。新建 GitHub 仓库时如果默认分支是 `main`，不用管它——推送 `master` 后在 GitHub 的 Settings → Branches 里把默认分支改成 `master`，再删掉空的 `main`。

## 2. 一次性配置：SSH 密钥

在 Git Bash 里执行（本仓库当前机器无 `~/.ssh`，是全新创建）：

```sh
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C "ontology-wulin" -f ~/.ssh/id_ed25519 -N ''
cat ~/.ssh/id_ed25519.pub
```

`-N ''` 表示不带口令，好处是流水线式地一键推送，代价是这台电脑上拿到这把私钥就等于拿到你的 Gitee/GitHub 写权限。如果不能接受，去掉 `-N ''` 改用口令，并在 Windows 上启动 `ssh-agent` 服务后 `ssh-add ~/.ssh/id_ed25519`。

把 `cat` 出来的整行公钥（`ssh-ed25519 AAAA... ontology-wulin`）分别登记：

- Gitee：打开 <https://gitee.com/profile/sshkeys> → 新增公钥 → 粘贴 → 标题随意 → 确定。
- GitHub：打开 <https://github.com/settings/keys> → New SSH key → 粘贴 → Add SSH key。

逐边验证（通了会打印欢迎语，不会报错）：

```sh
ssh -T git@gitee.com
ssh -T git@github.com
```

首次连接会问 `Are you sure you want to continue connecting`，输入 `yes`。Gitee 若提示 `Permission denied (publickey)`，先确认账号邮箱已完成验证，公钥没有多余空格或换行。

## 3. 一次性配置：远程地址

本仓库已配好 `gitee`，`github` 待补：

```sh
cd D:/Front_Git/ontology-main
git remote set-url gitee git@gitee.com:amoeba1989/ontology.git
git remote add github git@github.com:<你的用户名>/<仓库名>.git
git remote -v
```

把 GitHub 设为 upstream 只是为了 `git push` 不带参数时不会误推，两条流水线都不依赖它：

```sh
git branch --set-upstream-to=gitee/master master
```

## 4. 日常操作

一条命令同时推两边，连不通的那边自动跳过且不报错中断：

```sh
sh scripts/git-push-both.sh            # 默认推 master
```

单位里只有 Gitee 通，就等价于 `git push gitee master`，Gitee Go 随即开始编译检查和部署；回到家里补一条 `git push github master`，Actions 会重新走一遍 pytest + 前端构建再部署同一版本。

只推一边也完全可以：

```sh
git push gitee master      # 单位
git push github master     # 家里
```

注意别在两边各自做出不同的提交，否则分叉后必须先合并再推。保持"Gitee 与 GitHub 的 `master` 指向同一个 SHA"是这套双部署不出乱子的前提。

## 5. 两条流水线怎么配合

Gitee Go（`.workflow/` 下的文件才是实际执行的那份，仓库根目录的 `gitee-pipeline.yml` 是同内容副本，改一个必须改两个）走的是主机部署：ECS 上已注册的 `PALANTIR` 主机组里的 agent，直接进 `/opt/ontology` 执行 `git fetch origin master` → `git checkout --force --detach` → 构建 → `scripts/deploy/deploy-docker.sh`。它要求：

- ECS 上那个 clone 的 `origin` 必须指向 Gitee（脚本第 2 阶段之前会显式校验并中止）；
- ECS 上要有能读该仓库的凭证，脚本用 `-c credential.helper=store`，即 `git config --global credential.helper store` 里已存好的 Gitee 账号凭证；
- agent 与 Gitee Go 控制面在线。

GitHub Actions 走的是文件同步：runner 用 `git archive` 打包本次提交，通过 SSH 落到 ECS 再 rsync 进 `/opt/ontology`（保留 `.git/`、`.env`、`data/`），然后在 ECS 构建并重启容器。

两边的部署脚本都持有 `/opt/ontology/.deploy.lock`（`flock -w 1800`），所以不会同时改同一目录。Gitee 侧现在也会写 `.deployment-revision`，这样 `deploy-docker.sh` 传给演示校验的版本号和 Actions 里比对 `GITHUB_SHA` 的逻辑对得上。

两个差异要知道：

- Actions 有 `verify` 前置（后端 pytest + 前端构建）和演示报告硬门禁；Gitee Go 只有编译检查（`docker compose build`），失败即中止，不跑 pytest。
- Actions 的部署受仓库变量 `DEPLOY_ENABLED` 控制，值为 `true` 才部署；Gitee Go 没有这个开关，推 `master` 就部署。若只想临时停掉自动上线，去 Gitee Go 控制台暂停流水线。

## 6. 首次启用要确认的几件事

1. Gitee Go 控制台里这条流水线的 YAML 是否与仓库一致（UI 上确认一次，并手动运行一次试跑）。
2. GitHub 仓库的 Secrets 与 `production` 环境按 [GitHub 自动部署到阿里云 ECS](./github-actions-deploy.md) 配好，变量 `DEPLOY_ENABLED=true`。
3. 两边的 ECS 主机指纹/端口、`WEB_PORT=8088` 保持一致。
4. Gitee Go 私有仓库有构建时长配额，超时会中断在阶段上，控制台可查具体阶段耗时。

## 7. 可选：让一边自动同步到另一边

如果不想手动补推，可以让 GitHub Actions 在部署成功后反向推送到 Gitee（Gitee 服务器方向访问 GitHub 不稳定，不建议做 Gitee→GitHub 的自动镜像）。做法是在 `.github/workflows/deploy.yml` 里追加一个 job，用 Gitee 私人令牌推送：

```yaml
  mirror_to_gitee:
    needs: deploy
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - run: |
          git remote add gitee https://oauth2:${GITEE_TOKEN}@gitee.com/amoeba1989/ontology.git
          git push gitee HEAD:master
        env:
          GITEE_TOKEN: ${{ secrets.GITEE_TOKEN }}
```

令牌在 Gitee 的 Settings → 私人令牌 生成，勾选 `projects` 权限，存为 GitHub Secret `GITEE_TOKEN`。这段配置默认没有启用——它引入了一个长期有效的令牌，只有你确认愿意承担这个风险时再加。
