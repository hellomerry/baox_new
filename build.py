"""
PyInstaller 打包脚本（P 决策）
- 三个 launcher 各自打包成独立 .exe
- 包含 Python 解释器 + 依赖 + 应用代码
- 不打包数据库（运行时生成）

用法：
    python build.py finance
    python build.py auditor
    python build.py reimburser
    python build.py all
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# Windows GBK 兜底
try:
    from utils.setup_stdout import setup_safe_stdout
    setup_safe_stdout()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / 'dist'
BUILD_DIR = BASE_DIR / 'build'


CLIENTS = {
    'finance': 'launcher_finance.py',
    'auditor': 'launcher_auditor.py',
    'reimburser': 'launcher_reimburser.py',
}


def build_one(client_type: str):
    """打包一个客户端"""
    launcher = CLIENTS.get(client_type)
    if not launcher:
        print(f'未知客户端类型: {client_type}')
        return False

    launcher_path = BASE_DIR / launcher
    if not launcher_path.exists():
        print(f'启动器不存在: {launcher_path}')
        return False

    print(f'\n{"=" * 50}')
    print(f'打包 {client_type} 客户端')
    print(f'{"=" * 50}\n')

    # 1. 收集数据文件
    datas = [
        ('templates', 'templates'),
        ('static', 'static'),
    ]
    # PyInstaller 隐藏导入（动态加载的）
    hiddenimports = [
        'flask',
        'flask_sqlalchemy',
        'sqlalchemy',
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'webview.platforms.gtk',
        'webview.platforms.qt',
        'webview.platforms.cocoa',
        'webview.platforms.linux',
        'webview.platforms.mshtml',
        'webview.platforms.android',
        'webview.platforms.android.base',
        'webview.platforms.android.event',
        'webview.platforms.android.app',
        'clr_loader',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.backends.openssl',
        'reportlab',
        'reportlab.pdfbase.cidfonts',
        'reportlab.pdfbase._fontdata',
        'reportlab.platypus',
        'docx',
        'bottle',
        'bottle_websocket',
        'pyparsing',
        'loguru',
        'gi',
        'gi.repository',
        'gi.repository.Gtk',
        'gi.repository.WebKit2',
        'gi.repository.Gdk',
        'gi.repository.GObject',
        'gi.repository.Gio',
        'gi.repository.GLib',
        'gi.repository.Pango',
        'gi.repository.cairo',
    ]

    # 2. 构造 pyinstaller 命令
    # 跨平台：name 用英文避免 Windows 中文路径 bug；Windows 上 PyInstaller 自动加 .exe
    name_en = f'reimbursement_{client_type}'

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        f'--name={name_en}',
        '--onedir',  # 单目录模式：启动快，调试方便
        '--windowed',  # 不显示控制台（Windows 上 = 隐藏 GUI 程序的 cmd 窗口）
        '--add-data', f'templates{os.pathsep}templates',
        '--add-data', f'static{os.pathsep}static',
    ]
    for hi in hiddenimports:
        cmd.extend(['--hidden-import', hi])

    # SSL 证书
    ssl_dir = BASE_DIR / 'ssl'
    if ssl_dir.exists():
        cmd.extend(['--add-data', f'ssl{os.pathsep}ssl'])

    # 图标（可选）：resources/<client>.ico（Windows）/ .icns（macOS）
    icon_path = BASE_DIR / 'resources' / f'{client_type}.ico'
    if icon_path.exists():
        cmd.extend([f'--icon={icon_path}'])

    # Windows 版本信息（可选）：resources/<client>_version.txt
    version_file = BASE_DIR / 'resources' / f'{client_type}_version.txt'
    if version_file.exists():
        cmd.extend([f'--version-file={version_file}'])

    # 收集 webview 资源（js/lib/platforms）
    try:
        import webview as _wv
        webview_root = Path(_wv.__file__).parent
        # 整个 platforms 子目录（lazy import 必须显式包含）
        platforms_dir = webview_root / 'platforms'
        if platforms_dir.exists():
            cmd.extend(['--add-data', f'{platforms_dir}{os.pathsep}webview/platforms'])
        # js 资源（前端 HTML 桥接）
        js_dir = webview_root / 'js'
        if js_dir.exists():
            cmd.extend(['--add-data', f'{js_dir}{os.pathsep}webview/js'])
        # lib 资源（Windows 上的 edge webview2 native lib）
        lib_dir = webview_root / 'lib'
        if lib_dir.exists():
            cmd.extend(['--add-data', f'{lib_dir}{os.pathsep}webview/lib'])
        print(f'  ✓ 已添加 webview 资源（platforms + js + lib）')
    except Exception as e:
        print(f'⚠️ 收集 webview 资源失败: {e}')

    cmd.append(launcher)
    print(f'命令: {" ".join(cmd[:5])}...')

    # 3. 执行打包
    try:
        result = subprocess.run(cmd, cwd=str(BASE_DIR), timeout=600)
        if result.returncode != 0:
            print(f'❌ {client_type} 打包失败')
            return False
    except subprocess.TimeoutExpired:
        print(f'❌ {client_type} 打包超时')
        return False
    except FileNotFoundError:
        print('❌ PyInstaller 未安装，请先运行: pip install pyinstaller')
        return False

    # 4. PyInstaller 6 onedir 直接输出到 dist/
    # name 用英文（reimbursement_<client>），跨平台：Linux 无后缀 / Windows .exe
    name_en = f'reimbursement_{client_type}'
    final_dir = DIST_DIR / name_en

    if not final_dir.exists():
        print(f'❌ {client_type} 打包产物未找到: {final_dir}')
        return False

    # 跨平台：先找 .exe（Windows），再找无后缀（Linux/macOS）
    exe_path = final_dir / f'{name_en}.exe'
    if not exe_path.exists():
        exe_path = final_dir / name_en

    if not exe_path.exists():
        print(f'⚠️ {client_type} 打包目录存在但找不到 ELF/EXE')
        return False

    # 计算总大小
    total = sum(f.stat().st_size for f in final_dir.rglob('*') if f.is_file())
    size_mb = total / 1024 / 1024
    exe_size_mb = exe_path.stat().st_size / 1024 / 1024
    # 平台标识
    import platform as _p
    plat = _p.system()
    print(f'✅ {client_type} 打包成功（{plat}, onedir）: {final_dir}/ ({size_mb:.1f} MB)')
    print(f'   可执行: {exe_path.name} ({exe_size_mb:.1f} MB)')
    return True


def build_all():
    """打包所有客户端"""
    results = {}
    for client in CLIENTS.keys():
        results[client] = build_one(client)

    print(f'\n{"=" * 50}')
    print('打包汇总')
    print(f'{"=" * 50}')
    for c, ok in results.items():
        status = '✅ 成功' if ok else '❌ 失败'
        print(f'  {c}: {status}')


def clean():
    """清理打包临时文件"""
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            shutil.rmtree(str(d))
            print(f'已删除: {d}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法:')
        print('  python build.py finance      # 打包财务版')
        print('  python build.py auditor      # 打包稽核员版')
        print('  python build.py reimburser   # 打包报销人版')
        print('  python build.py all          # 打包所有')
        print('  python build.py clean        # 清理打包产物')
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'all':
        build_all()
    elif cmd == 'clean':
        clean()
    else:
        build_one(cmd)
