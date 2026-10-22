"""
桌面环境诊断 + 兜底
====================
pywebview 启动前先检查系统库，给出清晰错误。
"""
import os
import sys
import subprocess
import platform
from pathlib import Path

# Windows GBK 兜底
for _name in ('stdout', 'stderr'):
    _stream = getattr(sys, _name, None)
    if _stream is not None:
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


# ============= 各平台必检库 =============
DESKTOP_DEPS = {
    'linux': {
        'gtk3': ['libgtk-3.so.0', 'libgdk-3.so.0'],
        'webkit': ['libwebkit2gtk-4.1.so.0', 'libwebkit2gtk-4.0.so.37'],
        'soup': ['libsoup-3.0.so.0', 'libsoup-2.4.so.1'],
        'glib': ['libglib-2.0.so.0', 'libgobject-2.0.so.0', 'libgio-2.0.so.0'],
        'graphics': ['libcairo.so.2', 'libpango-1.0.so.0', 'libpangocairo-1.0.so.0'],
    },
    'darwin': {
        # macOS 自带
        'cocoa': ['/System/Library/Frameworks/Cocoa.framework'],
    },
    'windows': {
        # Windows 自带（理论上）
        'webview2': [],
    },
}


def find_lib(libname: str) -> str:
    """查找系统库"""
    # ldconfig
    try:
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if libname in line and '=>' in line:
                return line.split('=>')[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 常见路径
    paths = [
        '/usr/lib/x86_64-linux-gnu',
        '/usr/lib/aarch64-linux-gnu',
        '/usr/lib64',
        '/usr/lib',
    ]
    base = libname.split('.so')[0]
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            for f in os.listdir(p):
                if f.startswith(base) and '.so' in f:
                    return os.path.join(p, f)
        except PermissionError:
            continue
    return None


def check_desktop_env() -> dict:
    """检查桌面环境

    Returns:
        {
            'ok': True/False,
            'platform': 'linux' / 'darwin' / 'windows',
            'missing': {'category': [libname, ...]},
            'hints': str,
        }
    """
    system = platform.system().lower()
    result = {
        'ok': True,
        'platform': system,
        'missing': {},
        'hints': '',
    }

    if system not in DESKTOP_DEPS:
        result['hints'] = f'未知平台: {system}'
        return result

    deps = DESKTOP_DEPS[system]
    for category, libs in deps.items():
        if not libs:
            continue
        missing = []
        for lib in libs:
            if lib.startswith('/'):  # 绝对路径（macOS framework）
                if not os.path.exists(lib):
                    missing.append(lib)
            else:
                if not find_lib(lib):
                    missing.append(lib)
        if missing:
            result['ok'] = False
            result['missing'][category] = missing

    # 生成建议
    if not result['ok']:
        result['hints'] = generate_hints(system, result['missing'])

    return result


def generate_hints(system: str, missing: dict) -> str:
    """生成安装建议"""
    if system == 'linux':
        # 识别发行版
        try:
            with open('/etc/os-release') as f:
                os_info = dict(
                    line.strip().split('=', 1)
                    for line in f if '=' in line
                )
            distro = os_info.get('ID', '').strip('"').lower()
        except FileNotFoundError:
            distro = 'unknown'

        if distro in ('ubuntu', 'debian', 'deepin', 'uos', 'kylin'):
            return (
                '系统缺少桌面依赖。请以 root 运行：\n'
                '  sudo apt install -y libgtk-3-0 libwebkit2gtk-4.1-0 libsoup-3.0-0 '
                'libglib2.0-0 libcairo2 libpango-1.0-0 fonts-wqy-microhei\n\n'
                '或运行本目录的 install_deps.sh 一键安装。'
            )
        elif distro in ('centos', 'rhel', 'rocky', 'almalinux'):
            return (
                '系统缺少桌面依赖。请以 root 运行：\n'
                '  sudo dnf install -y gtk3 webkit2gtk4.1 libsoup3 glib2 cairo pango\n\n'
                '或运行本目录的 install_deps.sh 一键安装。'
            )
        else:
            return (
                f'系统缺少桌面依赖（{distro}）。请安装：\n'
                '  - GTK 3 (libgtk-3)\n'
                '  - WebKitGTK 4.1 (libwebkit2gtk-4.1)\n'
                '  - libsoup 3.0\n'
                '  - Cairo + Pango\n\n'
                '或运行本目录的 install_deps.sh。'
            )
    elif system == 'darwin':
        return 'macOS 应自带 Cocoa。检查是否系统损坏。'
    elif system == 'windows':
        return (
            'Windows 需要安装 WebView2 Runtime：\n'
            '  https://developer.microsoft.com/microsoft-edge/webview2/\n'
            '或运行 install_deps.bat（如有）'
        )
    return '未知问题'


def show_diagnostic(result: dict):
    """打印诊断结果"""
    print('=' * 60)
    print('桌面环境诊断')
    print('=' * 60)
    print(f'平台: {result["platform"]}')

    if result['ok']:
        print('✅ 桌面依赖完整')
        return

    print('❌ 检测到缺失：')
    for cat, libs in result['missing'].items():
        print(f'  [{cat}]')
        for lib in libs:
            print(f'    - {lib}')

    print('\n' + '=' * 60)
    print(result['hints'])
    print('=' * 60)


def show_error_popup(result: dict):
    """弹窗显示（pywebview 失败后调用）"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            '报销稽核系统 - 桌面依赖缺失',
            f'系统缺少必要的桌面库：\n\n{result["hints"]}\n\n'
            f'详细缺失：\n' +
            '\n'.join(f'  • {cat}: {", ".join(libs)}'
                     for cat, libs in result['missing'].items())
        )
    except Exception:
        # tkinter 也失败就只能打印到 stderr
        pass


def preflight_check() -> bool:
    """启动前预检 — 桌面环境 + Python 解释器"""
    result = check_desktop_env()
    if not result['ok']:
        show_diagnostic(result)
        show_error_popup(result)
        return False
    return True


if __name__ == '__main__':
    result = check_desktop_env()
    show_diagnostic(result)
    sys.exit(0 if result['ok'] else 1)
