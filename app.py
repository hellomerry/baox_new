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
    :param client_type: finance / auditor / reimburser / web
        - finance/auditor/reimburser：桌面客户端（PyWebView），受 O12 决策约束
        - web：浏览器访问（同网段任意客户端），跳过客户端-角色绑定
    :param config_class: 配置类（生产环境用 ProductionConfig）
    """
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['CLIENT_TYPE'] = client_type

    # Web 模式：cookie 强制 secure + HTTPS-only
    if client_type == 'web':
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 不能 None，会被 CSRF 利用

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

    # Web 模式：注册 CORS
    if client_type == 'web':
        from utils.cors import register_cors
        register_cors(app)

    # 错误处理（N4 决策）
    from utils.error_handler import register_error_handlers
    register_error_handlers(app)

    # 根路由
    @app.route('/')
    def index():
        if not session.get('user_id'):
            # 未登录：显示登录页或欢迎页
            return render_template(
                'dashboard.html',
                client_type=client_type,
                access_mode='web' if client_type == 'web' else 'desktop',
            )
        return render_template(
            'dashboard.html',
            client_type=client_type,
            access_mode='web' if client_type == 'web' else 'desktop',
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
        info = {
            'status': 'ok',
            'client_type': client_type,
            'access_mode': 'web' if client_type == 'web' else 'desktop',
            'version': '1.0.0',
        }
        if client_type == 'web':
            # Web 模式额外返回绑定信息
            info.update({
                'host': Config.WEB_HOST,
                'port': Config.WEB_PORT,
                'https_required': Config.WEB_REQUIRE_HTTPS,
                'allowed_roles': Config.WEB_ALLOWED_ROLES,
            })
        return jsonify(info)

    # Web 模式访问信息页（直接显示服务器地址，方便用户复制）
    @app.route('/web-info')
    def web_info():
        if client_type != 'web':
            return jsonify({'code': 1, 'message': '非 web 模式'}), 404
        return jsonify({
            'code': 0,
            'data': {
                'server': '报销稽核系统',
                'version': '1.0.0',
                'host': Config.WEB_HOST,
                'port': Config.WEB_PORT,
                'allowed_roles': Config.WEB_ALLOWED_ROLES,
                'cors_origins': Config.WEB_CORS_ORIGINS,
                'require_https': Config.WEB_REQUIRE_HTTPS,
                'login_endpoint': '/api/auth/login',
                'docs': 'https://...',
            }
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


def run_flask_in_thread(app: Flask, port: int, host: str = '127.0.0.1', ssl_context=None) -> threading.Thread:
    """
    在后台线程跑 Flask

    :param app: Flask 应用
    :param port: 端口
    :param host: 绑定地址（默认 127.0.0.1，Web 模式用 0.0.0.0）
    :param ssl_context: (cert, key) 元组，O1 决策 TLS
    """
    def _run():
        app.run(
            host=host,
            port=port,
            debug=False,
            use_reloader=False,
            ssl_context=ssl_context,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
