"""
CORS 中间件（Web 模式专用）

浏览器跨域访问时需要返回正确的 CORS 头。
手写实现，避免依赖 flask-cors 等外部包。

关键头：
  Access-Control-Allow-Origin       允许的源（* 或特定 origin）
  Access-Control-Allow-Credentials  是否允许带 cookie（Flask session 必须 True）
  Access-Control-Allow-Methods      允许的方法
  Access-Control-Allow-Headers      允许的请求头
  Access-Control-Max-Age            预检请求缓存秒数

注意：
  - Allow-Credentials=True 时，Allow-Origin 不能是 *，必须是具体 origin
  - Web 模式默认 Allow-Credentials=True（因为 Flask session 用 cookie）
"""
from functools import wraps
from flask import request, current_app, make_response


def _resolve_allowed_origin():
    """根据配置解析允许的 Origin"""
    cfg = current_app.config.get('WEB_CORS_ORIGINS', '*')
    origin = request.headers.get('Origin')
    if cfg == '*':
        # 当 Allow-Credentials=True 时不能用 *，必须 echo Origin
        return origin if origin else '*'
    # 逗号分隔白名单
    allow_list = {o.strip() for o in cfg.split(',') if o.strip()}
    return origin if origin in allow_list else (allow_list[0] if allow_list else '')


def cors_after_request(response):
    """after_request hook：给每个响应加 CORS 头"""
    # 仅 Web 模式启用
    if not current_app.config.get('CLIENT_TYPE') == 'web':
        return response

    allowed_origin = _resolve_allowed_origin()
    response.headers['Access-Control-Allow-Origin'] = allowed_origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Max-Age'] = '86400'  # 24h 缓存预检
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    return response


def handle_preflight():
    """处理 OPTIONS 预检请求"""
    if request.method == 'OPTIONS':
        resp = make_response('', 204)
        allowed_origin = _resolve_allowed_origin()
        resp.headers['Access-Control-Allow-Origin'] = allowed_origin
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        resp.headers['Access-Control-Max-Age'] = '86400'
        return resp
    return None


def register_cors(app):
    """
    给 Flask app 注册 CORS 支持（仅 web 模式生效）

    用法：
        from utils.cors import register_cors
        app = create_app('web')
        register_cors(app)
    """
    @app.before_request
    def _preflight():
        return handle_preflight()

    app.after_request(cors_after_request)