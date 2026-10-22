# 推送到远程仓库指南

> 把本仓库推到两个远程仓库：
> - **GitHub 公开**: https://github.com/hellomerry/baox_new
> - **LAN Gitea**: http://192.168.2.188:3000/marc/bx_new

---

## 一键双推

```bash
cd /workspace/reimbursement-app
bash scripts/push-all.sh
```

会依次问：
1. `确认推送到两个仓库的 main 分支? [y/N]` — 输入 `y`
2. GitHub Username: `hellomerry` + Personal Access Token
3. Gitea Username: `marc` + 密码

---

## 三个 remote 说明

| Remote | URL | 用途 |
|--------|-----|------|
| `origin` | `https://github.com/hellomerry/baox_new.git` | 公开仓库（CI/CD + Release） |
| `lan` | `http://192.168.2.188:3000/marc/bx_new.git` | 内网仓库（团队协作） |
| `all` | 两个 URL 合并 | 一条命令推两个 |

### 单独推某个仓库

```bash
git push origin main    # 只推 GitHub
git push lan main       # 只推 LAN
```

### 一条命令推两个

```bash
git push all main
```

这会同时推到 `origin`（GitHub）和 `lan`（Gitea）。

---

## 推送流程

`scripts/push-all.sh` 自动做：

1. 检查 + 配置 `origin` 和 `lan` 两个 remote
2. 切换到指定分支
3. add + commit（如果有未提交改动）
4. 先推 GitHub（origin）
5. 再推 LAN（lan）
6. 任一失败都给清晰的错误提示

---

## 首次认证

### GitHub origin

需要 **Personal Access Token**（不是 GitHub 密码）：

1. 打开 https://github.com/settings/tokens/new
2. 勾选 `repo` 权限
3. Generate token，复制 `ghp_xxxxx`
4. 粘贴到推送时的 Password 提示

认证信息会缓存在 `~/.git-credentials`（明文）或系统 keyring，下次不用再输。

### LAN Gitea

需要 `marc` 用户的 **Gitea 密码** 或 **Personal Access Token**：

1. 打开 http://192.168.2.188:3000/user/settings/applications
2. Generate New Token，复制
3. 粘贴到推送时的 Password 提示

---

## 推送后的 CI/CD

### GitHub Actions（自动）

`.github/workflows/ci.yml` 在每次 push 时跑：
- 86 个 pytest 用例
- 代码 lint

`.github/workflows/build-windows.yml` 在 push tag 时跑：
- PyInstaller 打包 3 客户端
- 创建 GitHub Release

### Gitea Actions（可选）

Gitea 也支持类似 GitHub Actions 的 CI。配置 `.gitea/workflows/*.yaml` 即可。

---

## 推送命令速查

```bash
# 1. 首次推送（双仓库）
bash scripts/push-all.sh

# 2. 推送更新
git push all main

# 3. 推送新分支
git checkout -b feature-xxx
git push all feature-xxx

# 4. 打 tag 触发自动打包
git tag v1.0.0
git push all --tags

# 5. 拉取（双 remote 拉取）
git pull all main
```

---

## 推送前验证

```bash
# 跑测试
cd /workspace/reimbursement-app
python3 -m pytest tests/ -q

# 检查 git 状态
git status
git remote -v   # 确认 3 个 remote 配置正确
```

---

## 故障排查

### Q: GitHub 推送被拒 (403)

- Token 过期或权限不足 → 重新生成
- 仓库设了 push 限制 → 检查 Settings → Branches

### Q: Gitea 推送 401 Unauthorized

- 用户名/密码错 → 重试
- 仓库没给你 push 权限 → 联系 Gitea 管理员
- Gitea 启用了 2FA → 必须用 Personal Access Token

### Q: 提示 "could not read Username"

终端没正确读取 stdin。多半是 `GIT_TERMINAL_PROMPT=0`。unset 或：
```bash
GIT_TERMINAL_PROMPT=1 git push origin main
```

### Q: SSL 错误（沙箱环境）

沙箱通常缺 CA 证书。临时方案：
```bash
git -c http.sslVerify=false push origin main
```

生产环境正确做法：在沙箱装 CA cert，或用 SSH 协议。

---

## 切到 SSH（可选，永久免认证）

```bash
# 1. 生成 SSH key
ssh-keygen -t ed25519 -C "your@email.com"

# 2. 复制公钥
cat ~/.ssh/id_ed25519.pub

# 3. 加到 GitHub: https://github.com/settings/keys
# 4. 加到 Gitea: http://192.168.2.188:3000/user/settings/keys

# 5. 改 remote URL
cd /workspace/reimbursement-app
git remote set-url origin git@github.com:hellomerry/baox_new.git
git remote set-url lan git@192.168.2.188:marc/bx_new.git

# 6. 推送（免认证）
git push all main
```
