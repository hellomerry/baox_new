"""
报销人版启动器
集成：进程锁 + 启动检查 + TLS + 备份 + 自动迁移
"""
import sys
import os
import time
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
CLIENT_TYPE = 'reimburser'


def run_migrations():
    """自动跑迁移到最新版本（启动时）"""
    try:
        from migrations.runner import MigrationManager
        mgr = MigrationManager()
        current = mgr.get_applied_versions()
        current_ver = current[-1] if current else 'none'
        pending = mgr._topological_sort()
        if not pending:
            print(f'[1/6] 数据库迁移: 已是最新（v{current_ver}）')
            return True
        print(f'[1/6] 数据库迁移: v{current_ver} → v{pending[-1]}（共 {len(pending)} 个版本）')
        mgr.upgrade()
        return True
    except Exception as e:
        print(f'[1/6] 迁移失败: {e}')
        return False


def main():
    # 0. 自动迁移
    if not run_migrations():
        print('⚠️ 迁移失败，继续启动可能出错')

    # 1. 进程锁
    if not acquire_client_lock(str(CLIENT_DIR)):
        print('❌ 报销人版客户端已在运行！')
        sys.exit(1)
    print('[2/6] 进程锁获取成功')

    # 2. 数据库完整性
    ok, msg = check_database_integrity()
    if not ok:
        print(f'[ERROR] 数据库完整性检查失败: {msg}')
        sys.exit(1)
    print(f'[3/6] 数据库完整性: {msg}')

    # 3. Flask
    app = create_app(CLIENT_TYPE, config_class=ProductionConfig)
    print('[4/6] Flask 应用创建成功')

    # 4. TLS
    ssl_context = None
    if Config.SSL_CERT.exists() and Config.SSL_KEY.exists():
        ssl_context = (str(Config.SSL_CERT), str(Config.SSL_KEY))
        print(f'[5/6] TLS 启用')
    else:
        print(f'[5/6] TLS 未启用（证书不存在）')

    # 5. 启动
    port = find_free_port()
    run_flask_in_thread(app, port, ssl_context=ssl_context)
    time.sleep(1)
    print(f'[6/6] Flask 启动: 127.0.0.1:{port}')

    # 6. 桌面环境预检
    try:
        from utils.diagnostics import preflight_check
        if not preflight_check():
            print('❌ 桌面依赖缺失')
            sys.exit(2)
    except ImportError:
        pass

    window = webview.create_window(
        title='报销稽核系统 - 报销人版',
        url=f'http://127.0.0.1:{port}' if not ssl_context else f'https://127.0.0.1:{port}',
        width=1100,
        height=750,
        resizable=True,
    )

    try:
        # 默认内核（pywebview ≥5.4 自动选 WebView2/Edge Chromium）
        webview.start()
    except Exception as e:
        log_client_error('reimburser-launcher', 'CLIENT_CRASH', str(e))
        print(f'[CRASH] 客户端崩溃: {e}')
        sys.exit(1)

    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if code == 0xE0434352 or code == -532462766:
            print('=' * 60)
            print('[CRASH] PyWebView failed to start: .NET Runtime not found')
            print('=' * 60)
            print('Install .NET 6.0+ Desktop Runtime:')
            print('  https://dotnet.microsoft.com/download/dotnet/6.0')
        raise


if __name__ == '__main__':
    main()
