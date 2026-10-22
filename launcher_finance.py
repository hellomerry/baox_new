"""
财务版启动器
T1：项目结构 + PyWebView 三客户端骨架
集成：进程锁（C1）+ 启动检查（N5）+ TLS（O1）+ 备份（M3）+ 自动迁移
"""
import sys
import time
import os
from pathlib import Path
# 绿色版修复：把脚本所在目录加进 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
# GBK 编码 + PyInstaller --windowed 兜底
from utils.setup_stdout import setup_safe_stdout
setup_safe_stdout()

import webview

from app import create_app, find_free_port, run_flask_in_thread
from config import Config, ProductionConfig
from utils.single_instance import acquire_client_lock
from utils.integrity import check_database_integrity
from utils.error_handler import log_client_error


CLIENT_DIR = Path(__file__).resolve().parent
CLIENT_TYPE = 'finance'


def run_migrations():
    """自动跑迁移到最新版本（启动时）"""
    try:
        from migrations.runner import MigrationManager
        mgr = MigrationManager()
        current = mgr.get_applied_versions()
        current_ver = current[-1] if current else 'none'

        # 计算待执行
        pending = mgr._topological_sort()
        if not pending:
            print(f'[1/6] 数据库迁移: 已是最新（v{current_ver}）')
            return True

        print(f'[1/6] 数据库迁移: v{current_ver} → v{pending[-1]}（共 {len(pending)} 个版本）')
        mgr.upgrade()
        return True
    except Exception as e:
        print(f'[1/6] 迁移失败: {e}')
        import traceback
        traceback.print_exc()
        return False


def main():
    # 0. 启动时自动迁移（v2.x 升级不需要手动跑 migrate.py）
    if not run_migrations():
        print('⚠️ 迁移失败，继续启动可能出错')
        # 不退出 — 让旧版本数据库也能跑（向后兼容）

    # 1. C1 决策：进程锁
    if not acquire_client_lock(str(CLIENT_DIR)):
        print('❌ 财务版客户端已在运行！')
        print('   请检查任务栏/系统托盘是否已打开。')
        print('   如确认未运行，请删除 .client.lock 文件后重试。')
        sys.exit(1)
    print('[2/6] 进程锁获取成功')

    # 2. N5 决策：启动时数据库完整性检查
    ok, msg = check_database_integrity()
    if not ok:
        print(f'[ERROR] 数据库完整性检查失败: {msg}')
        print('提示：可从最近的备份恢复。')
        # T2 后续会加弹窗恢复 UI
        sys.exit(1)
    print(f'[3/6] 数据库完整性: {msg}')

    # 2.1 M3 决策：启动时自动备份
    try:
        from utils.backup import backup_database
        ok, msg, _ = backup_database()
        if ok:
            print(f'[3.1/6] 自动备份: {msg[:60]}')
        else:
            print(f'[3.1/6] 备份跳过: {msg}')
    except Exception as e:
        print(f'[3.1/6] 备份异常: {e}')

    # 3. O12 决策：使用生产配置
    app = create_app(CLIENT_TYPE, config_class=ProductionConfig)
    print('[4/6] Flask 应用创建成功')

    # 4. O1 决策：TLS 强制
    ssl_context = None
    if Config.SSL_CERT.exists() and Config.SSL_KEY.exists():
        ssl_context = (str(Config.SSL_CERT), str(Config.SSL_KEY))
        print(f'[5/6] TLS 启用: {Config.SSL_CERT}')
    else:
        print(f'[5/6] TLS 未启用（证书不存在，使用 HTTP）— 首次启动正常')

    # 5. 启动 Flask + PyWebView（桌面端）
    port = find_free_port()
    run_flask_in_thread(app, port, ssl_context=ssl_context)
    time.sleep(1)  # 等 Flask 就绪
    print(f'[6/6] 桌面 Flask 启动: 127.0.0.1:{port}')

    # === v2.10.0e 新增：Web 模式（财务端默认同时启桌面 + Web）===
    web_url = None
    web_app = None
    if Config.WEB_ENABLED:
        web_app = create_app('web', config_class=ProductionConfig)
        web_ssl = ssl_context if Config.WEB_REQUIRE_HTTPS else None
        try:
            run_flask_in_thread(
                web_app,
                Config.WEB_PORT,
                host=Config.WEB_HOST,
                ssl_context=web_ssl,
            )
            time.sleep(1)
            proto = 'https' if web_ssl else 'http'
            web_url = f'{proto}://0.0.0.0:{Config.WEB_PORT}'
            print(f'[WEB] Web 模式已启用: {web_url}')
            print(f'[WEB]   同网段浏览器访问: {proto}://<本机IP>:{Config.WEB_PORT}')
            print(f'[WEB]   允许登录角色: {Config.WEB_ALLOWED_ROLES}')
        except Exception as e:
            print(f'[WEB] Web 模式启动失败: {e}（不影响桌面端使用）')
            web_app = None

    # 6. 桌面环境预检（缺 GTK/WebKit 给清晰错误）
    try:
        from utils.diagnostics import preflight_check
        if not preflight_check():
            print('❌ 桌面依赖缺失，请按提示安装后重试')
            sys.exit(2)
    except ImportError:
        pass  # diagnostics 模块不存在（旧版兼容）

    window = webview.create_window(
        title='报销稽核系统 - 财务版',
        url=f'http://127.0.0.1:{port}' if not ssl_context else f'https://127.0.0.1:{port}',
        width=1400,
        height=900,
        resizable=True,
        text_select=True,
    )

    try:
        # 默认内核（pywebview ≥5.4 自动选 WebView2/Edge Chromium）
        webview.start()
    except Exception as e:
        log_client_error('finance-launcher', 'CLIENT_CRASH', str(e))
        print(f'[CRASH] 客户端崩溃: {e}')
        sys.exit(1)
    except SystemExit as e:
        # pythonnet 0xE0434352 / .NET 异常退出
        code = e.code if isinstance(e.code, int) else 1
        if code == 0xE0434352 or code == -532462766:
            print('=' * 60)
            print('[CRASH] PyWebView failed to start: .NET Runtime not found')
            print('=' * 60)
            print()
            print('PyWebView on Windows uses pythonnet which requires')
            print('.NET 6.0+ Desktop Runtime to be installed.')
            print()
            print('Fix:')
            print('  1. Download .NET 6.0 Desktop Runtime (x64)')
            print('     https://dotnet.microsoft.com/download/dotnet/6.0')
            print('  2. Run the installer (admin)')
            print('  3. Restart this app')
            print()
            print('Or run check_dotnet.bat to verify .NET installation')
        raise


if __name__ == '__main__':
    main()
