#!/usr/bin/env python3
"""
打包产物的裸机环境检查脚本
===========================
目标机器上运行这个脚本，能告诉你：
- 系统基础库是否齐全
- 桌面依赖（GTK / WebKit）是否齐全
- 还缺什么

用法：
    python check_deps.py                 # 全部检查
    python check_deps.py --client finance  # 检查特定客户端

设计：纯 Python 3 标准库 + subprocess，不依赖打包产物
"""
import sys
# Windows GBK 兜底（避免 ✓/⚠/❌ 触发 UnicodeEncodeError）
for _name in ('stdout', 'stderr'):
    _stream = getattr(sys, _name, None)
    if _stream is not None:
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

import os
import subprocess
import platform
from pathlib import Path


# ============= 必需的系统库（ELF 直接 NEEDED）============
# 任何 glibc 系统都自带
GLIBC_BASE = ['libc.so.6', 'libdl.so.2', 'libpthread.so.0', 'libz.so.1']

# ============= 桌面依赖（pywebview 在 Linux 上需要）============
GTK_REQUIRED = [
    'libgtk-3.so.0',          # GTK 3 核心
    'libgobject-2.0.so.0',    # GLib 对象系统
    'libgio-2.0.so.0',        # GLib I/O
    'libglib-2.0.so.0',       # GLib
    'libgmodule-2.0.so.0',    # GLib 动态加载
    'libgdk_pixbuf-2.0.so.0', # GDK 图片缓冲
    'libcairo.so.2',          # Cairo 图形
    'libpango-1.0.so.0',      # Pango 文字
    'libpangocairo-1.0.so.0', # Pango Cairo
]

WEBKIT_REQUIRED = [
    'libwebkit2gtk-4.1.so.0',  # WebKitGTK 4.1（pywebview 6.x 默认）
    'libsoup-3.0.so.0',        # libsoup HTTP
    'libjavascriptcoregtk-4.1.so.0',
]


def find_lib(libname: str) -> str:
    """在系统库路径找 .so"""
    result = subprocess.run(
        ['ldconfig', '-p'],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if libname in line:
            # 格式: libfoo.so.X => /path/libfoo.so.X
            parts = line.split('=>')
            if len(parts) == 2:
                return parts[1].strip()
    return None


def find_lib_via_paths(libname: str) -> str:
    """直接搜常见路径"""
    paths = [
        '/lib/x86_64-linux-gnu',
        '/usr/lib/x86_64-linux-gnu',
        '/lib64',
        '/usr/lib64',
        '/lib',
        '/usr/lib',
        '/usr/lib/aarch64-linux-gnu',
        '/usr/lib/arm-linux-gnueabihf',
    ]
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            for f in os.listdir(p):
                if f.startswith(libname.split('.so')[0]) and f.endswith('.so'):
                    return os.path.join(p, f)
        except PermissionError:
            continue
    return None


def check_lib(libname: str) -> dict:
    """检查一个库是否存在 + 路径"""
    path = find_lib(libname) or find_lib_via_paths(libname)
    return {
        'name': libname,
        'present': path is not None,
        'path': path or '(not found)',
    }


def check_distribution() -> dict:
    """识别 Linux 发行版"""
    info = {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()}

    # /etc/os-release 标准
    try:
        with open('/etc/os-release') as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    info[k] = v.strip('"')
    except FileNotFoundError:
        pass

    return info


def main():
    print('=' * 70)
    print('报销稽核系统 - 裸机环境检查')
    print('=' * 70)

    # 1. 系统信息
    print('\n[1/4] 系统信息')
    dist = check_distribution()
    print(f'  系统:     {dist.get("NAME", dist["system"])} {dist.get("VERSION", dist["release"])}')
    print(f'  架构:     {dist["machine"]}')
    print(f'  内核:     {dist["release"]}')

    # 2. ELF 基础库
    print('\n[2/4] ELF 基础库（必需）')
    base_ok = 0
    for lib in GLIBC_BASE:
        r = check_lib(lib)
        status = '✓' if r['present'] else '✗'
        print(f'  [{status}] {lib:<30} {r["path"]}')
        if r['present']:
            base_ok += 1
    print(f'\n  基础库: {base_ok}/{len(GLIBC_BASE)} OK')
    if base_ok < len(GLIBC_BASE):
        print('  ❌ 基础库不全！需要安装: glibc, zlib1g')
        print('     Ubuntu/Debian: sudo apt install libc6 zlib1g')
        print('     麒麟/UOS:    sudo dnf install glibc zlib')

    # 3. GTK 桌面依赖
    print('\n[3/4] GTK 桌面依赖（pywebview 需要）')
    gtk_ok = 0
    for lib in GTK_REQUIRED:
        r = check_lib(lib)
        status = '✓' if r['present'] else '✗'
        print(f'  [{status}] {lib:<30} {r["path"]}')
        if r['present']:
            gtk_ok += 1
    print(f'\n  GTK: {gtk_ok}/{len(GTK_REQUIRED)} OK')

    # 4. WebKit
    print('\n[4/4] WebKit 渲染（pywebview 6.x 用 WebKitGTK 4.1）')
    webkit_ok = 0
    for lib in WEBKIT_REQUIRED:
        r = check_lib(lib)
        status = '✓' if r['present'] else '✗'
        print(f'  [{status}] {lib:<30} {r["path"]}')
        if r['present']:
            webkit_ok += 1
    print(f'\n  WebKit: {webkit_ok}/{len(WEBKIT_REQUIRED)} OK')

    # 总结
    print('\n' + '=' * 70)
    print('汇总')
    print('=' * 70)
    print(f'基础库:  {base_ok}/{len(GLIBC_BASE)} {"✓ 可运行" if base_ok == len(GLIBC_BASE) else "✗ 不够"}')
    print(f'GTK:     {gtk_ok}/{len(GTK_REQUIRED)} {"✓ 可启动 GUI" if gtk_ok == len(GTK_REQUIRED) else "✗ 缺桌面"}')
    print(f'WebKit:  {webkit_ok}/{len(WEBKIT_REQUIRED)} {"✓ 可渲染 HTML" if webkit_ok == len(WEBKIT_REQUIRED) else "✗ 缺渲染"}')

    # 安装建议
    if gtk_ok < len(GTK_REQUIRED) or webkit_ok < len(WEBKIT_REQUIRED):
        print('\n' + '=' * 70)
        print('安装建议')
        print('=' * 70)

        # 识别发行版给建议
        distro_id = dist.get('ID', '').lower()
        if distro_id in ('ubuntu', 'debian', 'deepin', 'uos', 'kylin'):
            print('\n# Ubuntu / Debian / 麒麟 / UOS:')
            print('sudo apt update')
            print('sudo apt install -y \\')
            print('    libgtk-3-0 libgdk-pixbuf2.0-0 libcairo2 libpango-1.0-0 \\')
            print('    libpangocairo-1.0-0 libgobject-2.0-0 libglib2.0-0 \\')
            print('    libwebkit2gtk-4.1-0 libsoup-3.0-0 \\')
            print('    libnotify4 libxss1 libxtst6 libatspi2.0-0')
        elif distro_id in ('centos', 'rhel', 'rocky', 'almalinux', 'kylin', 'opencloudos'):
            print('\n# CentOS / RHEL / 麒麟 V10 (RPM):')
            print('sudo dnf install -y \\')
            print('    gtk3 gdk-pixbuf2 cairo pango \\')
            print('    glib2 gobject-introspection \\')
            print('    webkit2gtk4.1 libsoup3 \\')
            print('    libnotify libXScrnSaver libXtst at-spi2-atk')
        else:
            print('\n请根据你的 Linux 发行版安装：')
            print('- GTK 3 (libgtk-3-0 / gtk3)')
            print('- GDK Pixbuf (libgdk-pixbuf2.0-0 / gdk-pixbuf2)')
            print('- Cairo (libcairo2 / cairo)')
            print('- Pango (libpango-1.0-0 / pango)')
            print('- WebKitGTK 4.1 (libwebkit2gtk-4.1-0 / webkit2gtk4.1)')
            print('- libsoup 3.0 (libsoup-3.0-0 / libsoup3)')
        print()

    # 退出码
    sys.exit(0 if base_ok == len(GLIBC_BASE) else 1)


if __name__ == '__main__':
    main()
