"""
错误日志（N4 决策）
Flask 全局错误处理 + 客户端错误日志
"""
import json
import traceback
from datetime import datetime

from flask import request, session, jsonify
from models import db
from models.models import ErrorLog, SysUser


def register_error_handlers(app):
    """注册 Flask 全局错误处理"""
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # 写 error_log
        try:
            user_id = session.get('user_id')
            ctx = {
                'user_id': user_id,
                'role': session.get('role'),
                'url': request.path if request else None,
                'method': request.method if request else None,
            }
            
            err = ErrorLog(
                type='PYTHON_EXCEPTION',
                message=str(e)[:500],
                stack_trace=traceback.format_exc(),
                context=json.dumps(ctx, ensure_ascii=False),
                user_id=user_id,
            )
            db.session.add(err)
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        # 返回给前端
        return jsonify({
            'code': 500,
            'message': f'系统错误: {type(e).__name__}',
        }), 500
    
    
    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({'code': 404, 'message': '接口不存在'}), 404


def log_client_error(client_id: str, error_type: str, message: str, stack_trace: str = ''):
    """客户端错误日志（PyWebView 崩溃时调用）"""
    try:
        err = ErrorLog(
            type=error_type,
            message=message[:500],
            stack_trace=stack_trace,
            context=json.dumps({'client_id': client_id}, ensure_ascii=False),
            client_id=client_id,
        )
        db.session.add(err)
        db.session.commit()
    except Exception:
        db.session.rollback()
