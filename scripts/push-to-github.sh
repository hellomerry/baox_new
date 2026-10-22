#!/bin/bash
# 一键推送到 GitHub 仓库
# 用法: bash scripts/push-to-github.sh [branch]
# 仓库: https://github.com/hellomerry/baox_new

set -e

REPO_URL="https://github.com/hellomerry/baox_new.git"
BRANCH="${1:-main}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} 报销稽核系统 - GitHub 推送工具${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "目标仓库: ${YELLOW}${REPO_URL}${NC}"
echo -e "目标分支: ${YELLOW}${BRANCH}${NC}"
echo ""

# 检查 git
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ 缺少 git${NC}"
    exit 1
fi

# 检查 remote
if ! git remote get-url origin &> /dev/null; then
    echo "添加 remote origin..."
    git remote add origin "${REPO_URL}"
fi

# 检查当前状态
echo "=== 当前 git 状态 ==="
git status -s
echo ""

# 询问是否推送
read -p "$(echo -e ${YELLOW}确认推送到 ${BRANCH}? [y/N]${NC}) " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 拉取远端
echo ""
echo -e "${GREEN}→ 拉取远端${NC}"
git fetch origin 2>&1 | head -5 || true

# 创建/切换分支
echo -e "${GREEN}→ 切换到 ${BRANCH} 分支${NC}"
git checkout -B "${BRANCH}" 2>/dev/null

# 提交
echo -e "${GREEN}→ 添加所有文件${NC}"
git add -A

if git diff --cached --quiet; then
    echo -e "${YELLOW}⚠️ 无新文件可提交${NC}"
else
    echo -e "${GREEN}→ 提交${NC}"
    git commit -m "feat: 报销稽核系统 v1.0

- T0-T5 完整业务链路（数据库 / 认证 / 单据 / 审核 / 三客户端前端）
- 等保二级合规（AES-256 字段加密 / TLS 1.2+ / 限速 / 审计日志）
- 信创环境兼容（麒麟 V10 / UOS 1050）
- PyInstaller 打包（Linux / Windows）
- 86 个 pytest 测试全过
- 迁移系统（migrations/runner.py）
- D3 决策：终审独立审计 + PDF 报告
- 报表 Excel 导出（xlsxwriter）
- 裸机部署检查工具（check_deps.py + install_deps.sh）

包含：
- 后端: Flask 3.1 + SQLAlchemy 2 + SQLite + 12 个 service + 11 个蓝图
- 前端: 原生 HTML/JS/CSS（不用 Vue/React）
- 桌面壳: PyWebView 6.2
- 文档: README + 信创部署 + Windows 打包 + 迁移系统 + 裸机运行
- 工具: build.py / generate_ssl.py / center_node.py / migrate.py / check_deps.py" || {
        echo -e "${RED}❌ 提交失败${NC}"
        exit 1
    }
fi

# 推送
echo -e "${GREEN}→ 推送到 ${REPO_URL}:${BRANCH}${NC}"
git push -u origin "${BRANCH}" --force-with-lease 2>&1

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} ✓ 推送完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "接下来："
echo "  1. 访问 https://github.com/hellomerry/baox_new 查看"
echo "  2. 在 Settings → Actions → General 启用 workflows"
echo "  3. 创建 tag 触发自动打包: git tag v1.0.0 && git push --tags"
echo "  4. 4-5 分钟后去 Actions 页面查看 CI / Windows 打包结果"
echo ""
