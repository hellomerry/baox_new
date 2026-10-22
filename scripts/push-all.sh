#!/bin/bash
# 一键推送到两个远程仓库
# - origin: GitHub 公开仓库 (hellomerry/baox_new)
# - lan:    Gitea 私有仓库 (marc/bx_new @ 192.168.2.188:3000)
#
# 用法: bash scripts/push-all.sh [branch]
# 首次使用：每个 remote 会要求认证（见下方"认证方式"）

set -e

BRANCH="${1:-main}"
ORIGIN_URL="https://github.com/hellomerry/baox_new.git"
LAN_URL="http://192.168.2.188:3000/marc/bx_new.git"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} 报销稽核系统 - 多仓库推送工具${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}目标仓库 1 (origin):${NC} ${YELLOW}${ORIGIN_URL}${NC}"
echo -e "${CYAN}目标仓库 2 (lan):${NC}    ${YELLOW}${LAN_URL}${NC}"
echo -e "${CYAN}目标分支:${NC}           ${YELLOW}${BRANCH}${NC}"
echo ""

# 检查 git
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ 缺少 git${NC}"
    exit 1
fi

# 配置 remotes（不存在则加）
if ! git remote get-url origin &> /dev/null; then
    echo "添加 remote origin..."
    git remote add origin "${ORIGIN_URL}"
fi
if ! git remote get-url lan &> /dev/null; then
    echo "添加 remote lan..."
    git remote add lan "${LAN_URL}"
fi

echo -e "${CYAN}=== 当前 remote 配置 ===${NC}"
git remote -v
echo ""

# 当前状态
echo -e "${CYAN}=== git 状态 ===${NC}"
git status -s
echo ""

# 确认
read -p "$(echo -e ${YELLOW}确认推送到两个仓库的 ${BRANCH} 分支? [y/N]${NC}) " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 切换分支
echo ""
echo -e "${GREEN}→ 切换到 ${BRANCH} 分支${NC}"
git checkout -B "${BRANCH}" 2>/dev/null

# 提交（如有未提交）
echo -e "${GREEN}→ 添加所有改动${NC}"
git add -A
if ! git diff --cached --quiet; then
    echo -e "${GREEN}→ 提交${NC}"
    git commit -m "chore: 同步多仓库版本"
else
    echo -e "${YELLOW}  无新改动，跳过 commit${NC}"
fi

# 推送到 origin（GitHub）
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} [1/2] 推送到 GitHub (origin)${NC}"
echo -e "${GREEN}========================================${NC}"
if git push -u origin "${BRANCH}" --force-with-lease 2>&1; then
    echo -e "${GREEN}✓ GitHub 推送成功${NC}"
else
    echo -e "${RED}❌ GitHub 推送失败${NC}"
    echo "提示: origin 需要 Personal Access Token (https://github.com/settings/tokens)"
    echo "      凭据可能缓存在 ~/.git-credentials 或系统 keyring"
    LAN_PUSH_SKIP=1
fi

# 推送到 lan（Gitea）
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} [2/2] 推送到 LAN Gitea (lan)${NC}"
echo -e "${GREEN}========================================${NC}"
if [ -n "${LAN_PUSH_SKIP}" ]; then
    echo "跳过（GitHub 推送失败）"
    exit 1
fi
if git push -u lan "${BRANCH}" --force-with-lease 2>&1; then
    echo -e "${GREEN}✓ LAN 推送成功${NC}"
else
    echo -e "${RED}❌ LAN 推送失败${NC}"
    echo "提示: Gitea 需要用户名密码（或 Personal Access Token）"
    echo "      第一次会让你输入 marc 的 Gitea 密码"
    exit 1
fi

# 完成
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} ✓ 双仓库推送完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "查看："
echo "  GitHub: https://github.com/hellomerry/baox_new"
echo "  LAN:    http://192.168.2.188:3000/marc/bx_new"
echo ""
echo "后续 commit 用法："
echo "  bash scripts/push-all.sh        # 推送到 main"
echo "  bash scripts/push-all.sh dev    # 推送到 dev 分支"
echo ""

# 提示以后简化命令（可选配置 push 推所有）
cat << 'TIP'

💡 提示：可以让 git push 默认推送到所有 remote：
   git config --global push.default matching
   # 或在 .git/config 加：
   # [remote "all"]
   #     url = https://github.com/hellomerry/baox_new.git
   #     url = http://192.168.2.188:3000/marc/bx_new.git

TIP
