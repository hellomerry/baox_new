"""
全局配置
T1 / O 决策落地
"""
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent


# 离线模式开关（环境变量 OFFLINE_MODE=true/false）
OFFLINE_MODE = os.environ.get('OFFLINE_MODE', 'true').lower() == 'true'
CENTER_NODE_HOST = os.environ.get('CENTER_NODE_HOST', '127.0.0.1')
CENTER_NODE_PORT = int(os.environ.get('CENTER_NODE_PORT', '5443'))


class Config:
    # 基础目录（供 service / utils 用）
    BASE_DIR = BASE_DIR

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-CHANGE-ME-IN-PROD'
    SESSION_COOKIE_NAME = 'rb_session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # 开发期关闭；O12 生产环境会强制 True
    SESSION_COOKIE_SAMESITE = 'Lax'  # O12
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # O5: 8 小时会话超时
    SESSION_REFRESH_EACH_REQUEST = True  # O5: 每次请求刷新过期时间

    # 数据库
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{BASE_DIR / "reimbursement.db"}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }

    # 文件上传
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

    # .rbag 包
    RBAG_TEMP_DIR = BASE_DIR / 'rbag_temp'

    # 日志
    LOG_DIR = BASE_DIR / 'logs'

    # O1: TLS 配置
    SSL_CERT = BASE_DIR / 'ssl' / 'cert.pem'
    SSL_KEY = BASE_DIR / 'ssl' / 'key.pem'

    # 客户端打包模板（财务/稽核员生成下级客户端时使用）
    # v2.10.0：包含 python 解释器 + site-packages + 启动脚本
    CLIENT_TEMPLATE_DIR = BASE_DIR / 'templates' / 'green_client_template'
    CLIENT_DIST_DIR = BASE_DIR / 'dist_clients'  # 生成的客户端包临时目录

    # O2: 限速配置
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = '60 per minute'
    RATELIMIT_LOCKOUT = '5 minutes'

    # 联网模式（默认离线）
    OFFLINE_MODE = os.environ.get('OFFLINE_MODE', 'true').lower() == 'true'
    CENTER_NODE_HOST = os.environ.get('CENTER_NODE_HOST', '127.0.0.1')
    CENTER_NODE_PORT = int(os.environ.get('CENTER_NODE_PORT', '5443'))

    # === Web 模式（v2.10.0e 新增）===
    # 财务端 launcher 默认同时启桌面 + Web，让同网段用户能用浏览器访问
    WEB_ENABLED = os.environ.get('WEB_ENABLED', 'true').lower() == 'true'
    WEB_HOST = os.environ.get('WEB_HOST', '0.0.0.0')  # 监听所有网卡
    WEB_PORT = int(os.environ.get('WEB_PORT', '5443'))
    WEB_REQUIRE_HTTPS = os.environ.get('WEB_REQUIRE_HTTPS', 'true').lower() == 'true'
    WEB_ALLOWED_ROLES = os.environ.get(
        'WEB_ALLOWED_ROLES', 'finance,auditor,reimburser'
    ).split(',')  # web 模式登录允许的角色（空列表 = 全部禁止）
    WEB_CORS_ORIGINS = os.environ.get('WEB_CORS_ORIGINS', '*')  # 跨域白名单


class ProductionConfig(Config):
    """O12 决策：生产环境配置加固"""
    DEBUG = False
    TESTING = False
    EXPLAIN_TEMPLATE_LOADING = False
    TRAP_HTTP_EXCEPTIONS = False
    PROPAGATE_EXCEPTIONS = False
