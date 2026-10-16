# Gitee 与 GitHub 同步

公司使用 Gitee，GPT 云工作空间使用 GitHub。只同步 GitHub `main` 与 Gitee 默认分支，不同步其他分支、标签、Issue、PR 或附件。

## 首次设置

1. 登录 Gitee，打开 https://gitee.com/profile/personal_access_tokens ，生成仅用于本项目同步的私人令牌，授予仓库读写所需的 `projects` 权限。令牌代表账号权限，请按平台支持选择最小权限，不要发到聊天或提交代码。
2. 打开 https://github.com/amoeba1989/ontology/settings/secrets/actions ，点击 **New repository secret**。Name 填 `GITEE_TOKEN`，Secret 粘贴令牌并保存。
3. 打开 https://github.com/amoeba1989/ontology/actions/workflows/sync-gitee.yml ，点击 **Run workflow**，选择 `main` 后运行。首次运行成功才表示配置完成。

无需设置 GitHub Token，工作流使用内置 `GITHUB_TOKEN`。无需将云工作空间私钥上传到 GitHub。若 Gitee 不返回默认分支，在 GitHub Actions Variables 中添加 `GITEE_SYNC_BRANCH`，填实际分支名（如 `main` 或 `master`）。

## 日常开发

- 公司：开始前拉取 Gitee；完成后提交并推送 Gitee。
- GPT 云端/家里：开始前确认同步任务成功，再拉取 GitHub `main`；完成后推送 GitHub `main`。
- GitHub 主分支推送后触发同步；另每约 15 分钟检查 Gitee，GitHub 调度可能延迟。可手动 Run workflow 提前同步。长期无活动的公开仓库可能被 GitHub 暂停定时任务。
- 若云端使用 `work` 或功能分支，需要合入/推送 `main` 后才会同步。

## 安全与限制

只做快进推送，不使用 force 或 mirror，也不删除分支。两边产生独立提交时任务失败并保持两边分支不变，需要先合并历史、解决冲突再运行。如果有并发提交，普通推送会拒绝覆盖，稍后重试即可。

首次配置时 GitHub 新增的同步配置可能与 Gitee 新提交形成分叉，此时需人工合并一次。分支保护规则也可能要求通过 PR 更新。

Gitee 提交如果修改 `.github/workflows/`，GitHub 内置 Token 可能拒绝导入，需要由有相应权限的用户通过本地 Git 合并推送。由 `GITHUB_TOKEN` 导入的提交不会再触发其他 push 工作流，因此不会自动触发项目现有部署；需要时手动运行部署工作流。

定时同步只运行固定的 Git 命令，不执行 Gitee 代码。认证只供 Gitee HTTPS 请求使用，令牌不会写入仓库 URL 或项目文件。令牌失效后需更新 Secret。
