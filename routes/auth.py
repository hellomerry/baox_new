"""
认证路由（T2）
- /api/auth/login  登录
- /api/auth/logout 登出
- /api/auth/me     当前用户
- /api/auth/change-password 改密码
"""
import hashlib
import re
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, session, current_app
from utils.ratelimit import limit_login, limit_global

from models import db
from models.models import SysUser, AuditLog, SysConfig

auth_bp = Blueprint('auth', __name__)


# ============= 工具函数 =============

def get_config(key: str, default: str = None) -> str:
    """读系统配置"""
    cfg = SysConfig.query.filter_by(config_key=key).first()
    return cfg.config_value if cfg else default


def validate_password_strength(password: str) -> tuple:
    """校验密码强度"""
    min_length = int(get_config('password_min_length', '10'))
    if len(password) < min_length:
        return False, f'密码长度至少 {min_length} 位'
    if not re.search(r'[A-Z]', password):
        return False, '密码需包含大写字母'
    if not re.search(r'[a-z]', password):
        return False, '密码需包含小写字母'
    if not re.search(r'[0-9]', password):
        return False, '密码需包含数字'
    if not re.search(r'[^A-Za-z0-9]', password):
        return False, '密码需包含特殊字符'
    return True, ''


# 角色到客户端类型的映射（T2 决策：客户端类型与账号角色绑定）
ROLE_TO_CLIENT = {
    'finance': 'finance',
    'auditor': 'auditor',
    'reimburser': 'reimburser',
}


# ============= 登录 =============

@auth_bp.route('/login', methods=['POST'])
@limit_login  # O2: 登录端点 10 次/分钟
def login():
    """登录"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'code': 1, 'message': '用户名和密码必填'}), 400

    # 1. 客户端类型与账号角色校验（测试模式跳过 client_type='*'）
    # v2.10.0e 新增：web 模式下根据 WEB_ALLOWED_ROLES 白名单校验，跳过 O12 绑定
    client_type = current_app.config.get('CLIENT_TYPE')
    web_allowed_roles = current_app.config.get('WEB_ALLOWED_ROLES', [])
    user_by_name = SysUser.query.filter_by(username=username).first()

    if client_type == 'web':
        # Web 模式：按白名单校验（空列表 = 全部禁止）
        if web_allowed_roles and user_by_name and user_by_name.role not in web_allowed_roles:
            try:
                log = AuditLog(
                    actor_id=user_by_name.id,
                    actor_role=user_by_name.role,
                    action='LOGIN_WEB_ROLE_NOT_ALLOWED',
                    detail=json.dumps({
                        'client_type': client_type,
                        'user_role': user_by_name.role,
                        'allowed_roles': web_allowed_roles,
                    }, ensure_ascii=False),
                    ip_address=request.remote_addr,
                )
                db.session.add(log)
                db.session.commit()
            except Exception:
                db.session.rollback()
            return jsonify({
                'code': 1,
                'message': f'Web 访问不允许该角色登录（{user_by_name.role}）'
            }), 403
    elif client_type != '*' and user_by_name and ROLE_TO_CLIENT.get(user_by_name.role) != client_type:
        # 桌面客户端：保留 O12 客户端-角色绑定
        try:
            log = AuditLog(
                actor_id=user_by_name.id,
                actor_role=user_by_name.role,
                action='LOGIN_ROLE_MISMATCH',
                detail=json.dumps({
                    'client_type': client_type,
                    'user_role': user_by_name.role,
                }, ensure_ascii=False),
                ip_address=request.remote_addr,
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({
            'code': 1,
            'message': f'此客户端是{client_type}版，无法登录{user_by_name.role}账号'
        }), 403

    user = user_by_name
    if not user:
        return jsonify({'code': 1, 'message': '用户名或密码错误'}), 401

    # 2. 账号状态检查
    if user.account_status == 'inactive':
        return jsonify({'code': 1, 'message': '账号已停用'}), 403

    # 3. 锁定检查
    if user.account_status == 'locked' and user.locked_until:
        if datetime.now() < user.locked_until:
            remaining = int((user.locked_until - datetime.now()).total_seconds() / 60)
            return jsonify({
                'code': 1,
                'message': f'账号已锁定，请 {remaining} 分钟后重试'
            }), 423
        else:
            # 锁定过期，重置
            user.account_status = 'normal'
            user.failure_count = 0
            user.locked_until = None
            db.session.commit()

    # 4. 验证密码（兼容首次 MD5）
    password_valid = False
    if len(user.password_hash) == 32:  # 旧 MD5
        if user.password_hash == hashlib.md5(password.encode()).hexdigest():
            password_valid = True
            # 自动升级为 pbkdf2
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(password)
            db.session.commit()
    else:  # 新 pbkdf2
        from werkzeug.security import check_password_hash
        password_valid = check_password_hash(user.password_hash, password)

    if not password_valid:
        # 失败计数
        user.failure_count = (user.failure_count or 0) + 1
        max_failures = int(get_config('login_max_failures', '5'))

        if user.failure_count >= max_failures:
            lockout_minutes = int(get_config('lockout_minutes', '30'))
            user.account_status = 'locked'
            user.locked_until = datetime.now() + timedelta(minutes=lockout_minutes)
            db.session.commit()
            return jsonify({
                'code': 1,
                'message': f'连续失败 {max_failures} 次，账号已锁定 {lockout_minutes} 分钟'
            }), 423

        db.session.commit()
        return jsonify({'code': 1, 'message': '用户名或密码错误'}), 401

    # 5. 成功：重置失败计数 + 写会话
    user.failure_count = 0
    user.locked_until = None
    db.session.commit()

    session.permanent = True
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['real_name'] = user.real_name

    # 6. 写操作日志
    try:
        log = AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            action='LOGIN',
            detail=json.dumps({'username': user.username}, ensure_ascii=False),
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'code': 0,
        'data': {
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'real_name': user.real_name,
            'must_change_password': (len(user.password_hash) == 32),  # MD5 引导密码需改
        }
    })


# ============= 登出 =============

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """登出"""
    user_id = session.get('user_id')
    if user_id:
        try:
            log = AuditLog(
                actor_id=user_id,
                actor_role=session.get('role', ''),
                action='LOGOUT',
                ip_address=request.remote_addr,
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()

    session.clear()
    return jsonify({'code': 0})


# ============= 当前用户 =============

@auth_bp.route('/me')
def me():
    """当前用户信息"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'code': 401, 'message': '未登录'}), 401

    user = SysUser.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({'code': 401, 'message': '用户不存在'}), 401

    return jsonify({
        'code': 0,
        'data': {
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'real_name': user.real_name,
            'department': user.department,
            'phone': user.phone,
        }
    })


# ============= 修改密码 =============

@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """修改密码"""
    from werkzeug.security import check_password_hash, generate_password_hash

    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'code': 401, 'message': '未登录'}), 401

    user = SysUser.query.get(user_id)
    if not user:
        return jsonify({'code': 1, 'message': '用户不存在'}), 400

    # 校验旧密码（兼容 MD5）
    old_valid = False
    if len(user.password_hash) == 32:
        old_valid = (user.password_hash == hashlib.md5(old_password.encode()).hexdigest())
    else:
        old_valid = check_password_hash(user.password_hash, old_password)

    if not old_valid:
        return jsonify({'code': 1, 'message': '原密码错误'}), 400

    # 校验新密码强度
    valid, msg = validate_password_strength(new_password)
    if not valid:
        return jsonify({'code': 1, 'message': msg}), 400

    if old_password == new_password:
        return jsonify({'code': 1, 'message': '新密码不能与原密码相同'}), 400

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({'code': 0, 'message': '密码修改成功'})


# ============= 占位（保持兼容）============
@auth_bp.route('/ping')
def ping():
    return jsonify({'msg': 'auth blueprint ready'})
