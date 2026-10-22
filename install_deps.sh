#!/bin/bash
"""
一键安装报销稽核系统的桌面依赖（Linux）
==========================================

适用：Ubuntu / Debian / 麒麟 V10 / UOS / Deepin
用途：在裸机上准备运行打包产物的系统环境
"""
set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo " 报销稽核系统 - 桌面依赖一键安装"
echo "=========================================="
echo ""

# 检测发行版
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    echo -e "${RED}无法识别 Linux 发行版${NC}"
    exit 1
fi

echo "检测到: $PRETTY_NAME"
echo ""

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}需要 root 权限来安装系统包${NC}"
    SUDO="sudo"
else
    SUDO=""
fi

# Ubuntu / Debian 系
if [[ "$OS" == "ubuntu" || "$OS" == "debian" || "$OS" == "deepin" || "$OS" == "uos" ]]; then
    echo -e "${GREEN}使用 apt 包管理器...${NC}"
    $SUDO apt update
    $SUDO apt install -y \
        libgtk-3-0 \
        libgdk-pixbuf2.0-0 \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgobject-2.0-0 \
        libglib2.0-0 \
        libgmodule-2.0-0 \
        libwebkit2gtk-4.1-0 \
        libsoup-3.0-0 \
        libnotify4 \
        libxss1 \
        libxtst6 \
        libatspi2.0-0 \
        fonts-wqy-microhei \
        fonts-noto-cjk
    echo ""
    echo -e "${GREEN}✓ 安装完成${NC}"

# CentOS / RHEL / 麒麟 V10
elif [[ "$OS" == "centos" || "$OS" == "rhel" || "$OS" == "rocky" || "$OS" == "almalinux" || "$OS" == "opencloudos" || "$OS" == "kylin" ]]; then
    echo -e "${GREEN}使用 dnf 包管理器...${NC}"

    # 检查 dnf 是否可用
    if ! command -v dnf &> /dev/null; then
        echo -e "${RED}未找到 dnf，请先安装 dnf${NC}"
        exit 1
    fi

    $SUDO dnf install -y \
        gtk3 \
        gdk-pixbuf2 \
        cairo \
        pango \
        glib2 \
        gobject-introspection \
        webkit2gtk4.1 \
        libsoup3 \
        libnotify \
        libXScrnSaver \
        libXtst \
        at-spi2-atk \
        wqy-microhei-fonts \
        google-noto-sans-cjk-fonts || \
    $SUDO yum install -y \
        gtk3 \
        gdk-pixbuf2 \
        cairo \
        pango \
        glib2 \
        gobject-introspection \
        webkit2gtk4.1 \
        libsoup3 \
        libnotify \
        libXScrnSaver \
        libXtst \
        at-spi2-atk

    echo ""
    echo -e "${GREEN}✓ 安装完成${NC}"

# Arch
elif [[ "$OS" == "arch" || "$OS" == "manjaro" ]]; then
    echo -e "${GREEN}使用 pacman...${NC}"
    $SUDO pacman -S --noconfirm \
        gtk3 \
        gdk-pixbuf2 \
        cairo \
        pango \
        glib2 \
        webkit2gtk-4.1 \
        libsoup3 \
        libnotify \
        wqy-microhei \
        noto-fonts-cjk
    echo ""
    echo -e "${GREEN}✓ 安装完成${NC}"

else
    echo -e "${RED}不支持的发行版: $OS${NC}"
    echo ""
    echo "请手动安装："
    echo "  - GTK 3 (libgtk-3-0 / gtk3)"
    echo "  - GDK Pixbuf (libgdk-pixbuf2.0-0 / gdk-pixbuf2)"
    echo "  - Cairo (libcairo2 / cairo)"
    echo "  - Pango (libpango-1.0-0 / pango)"
    echo "  - WebKitGTK 4.1 (libwebkit2gtk-4.1-0 / webkit2gtk4.1)"
    echo "  - libsoup 3.0"
    exit 1
fi

echo ""
echo "=========================================="
echo " 验证安装"
echo "=========================================="
python3 check_deps.py 2>/dev/null || python3 "$(dirname "$0")/check_deps.py" 2>/dev/null || echo "(check_deps.py 未在 PATH 中)"

echo ""
echo -e "${GREEN}完成！现在可以运行打包产物了：${NC}"
echo "  cd /path/to/reimbursement_finance"
echo "  ./reimbursement_finance"
