"""
权限装饰器（T2 决策）
- @login_required
- @role_required(*roles)
- 便捷装饰器
"""
from functools import wraps
from flask import session, jsonify, request

from models.models import SysUser


def get_current_user() -> SysUser:
    """获取当前登录用户"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return SysUser.query.get(user_id)


def login_required(f):
    """要求登录"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'code': 401, 'message': '未登录'}), 401
        return f(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    """要求特定角色"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get('user_id'):
                return jsonify({'code': 401, 'message': '未登录'}), 401
            role = session.get('role')
            if role not in allowed_roles:
                return jsonify({
                    'code': 403,
                    'message': f'权限不足，需要角色: {", ".join(allowed_roles)}'
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# 便捷装饰器
finance_required = role_required('finance')
auditor_required = role_required('auditor')
reimburser_required = role_required('reimburser')
finance_or_auditor_required = role_required('finance', 'auditor')
all_roles_required = role_required('finance', 'auditor', 'reimburser')
