"""
通用 Flask 应用工厂（T1）
T2-T5 的蓝图在这里注册
"""
import os
import sys
# 绿色版修复：把脚本所在目录加进 sys.path
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
import socket
import threading
from flask import Flask, session, redirect, url_for, render_template, jsonify

from config import Config, ProductionConfig
from models import db
from routes.auth import auth_bp
from routes.bills import bills_bp
from routes.projects import projects_bp
from routes.users import users_bp
from routes.attendance import attendance_bp
from routes.packages import packages_bp
from routes.reports import reports_bp
from routes.audit import audit_bp
from routes.standards import standards_bp
from routes.attachments import attachments_bp
from routes.sync import sync_bp
from routes.notifications import notifications_bp
from routes.data_import import data_import_bp
from routes.upgrade import upgrade_bp
from routes.data_dict import data_dict_bp
from routes.data_export import data_export_bp
from routes.dashboard import dashboard_bp
from routes.ocr import ocr_bp
from routes.client_distribution import dist_bp
from routes.agents import agents_bp


def create_app(client_type: str, config_class=Config) -> Flask:
    """
    工厂函数
    :param client_type: finance / auditor / reimburser
    :param config_class: 配置类（生产环境用 ProductionConfig）
    """
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['CLIENT_TYPE'] = client_type

    # 初始化数据库
    db.init_app(app)

    # 注册路由
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(bills_bp, url_prefix='/api/bills')
    app.register_blueprint(projects_bp, url_prefix='/api/projects')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(packages_bp, url_prefix='/api/packages')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(audit_bp, url_prefix='/api/audit')
    app.register_blueprint(standards_bp, url_prefix='/api/standards')
    app.register_blueprint(attachments_bp, url_prefix='/api/attachments')
    app.register_blueprint(sync_bp, url_prefix='/api/sync')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(data_import_bp, url_prefix='/api/data-import')
    app.register_blueprint(upgrade_bp, url_prefix='/api/upgrade')
    app.register_blueprint(data_dict_bp, url_prefix='/api/data-dict')
    app.register_blueprint(data_export_bp, url_prefix='/api/data-export')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(ocr_bp, url_prefix='/api/ocr')
    app.register_blueprint(dist_bp, url_prefix='/api/distribution')
    app.register_blueprint(agents_bp, url_prefix='/api/agents')

    # 错误处理（N4 决策）
    from utils.error_handler import register_error_handlers
    register_error_handlers(app)

    # 根路由
    @app.route('/')
    def index():
        if not session.get('user_id'):
            # 未登录：显示登录页或欢迎页
            return render_template('dashboard.html', client_type=client_type)
        return render_template(
            'dashboard.html',
            client_type=client_type,
            current_user={
                'id': session['user_id'],
                'username': session['username'],
                'role': session['role'],
                'real_name': session.get('real_name', ''),
            }
        )

    # 健康检查
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'ok',
            'client_type': client_type,
            'version': '1.0.0',
        })

    # 帮助页（P5 决策）
    @app.route('/help')
    def help():
        return render_template('help.html')

    return app


def find_free_port() -> int:
    """找一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run_flask_in_thread(app: Flask, port: int, ssl_context=None) -> threading.Thread:
    """
    在后台线程跑 Flask
    
    :param app: Flask 应用
    :param port: 端口
    :param ssl_context: (cert, key) 元组，O1 决策 TLS
    """
    def _run():
        app.run(
            host='127.0.0.1',
            port=port,
            debug=False,
            use_reloader=False,
            ssl_context=ssl_context,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
