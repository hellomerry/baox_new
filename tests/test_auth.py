"""
T2 认证授权测试
"""
import hashlib
import pytest
from models import db
from models.models import SysUser, AuditLog


def test_login_success(client, admin_user):
    """登录成功"""
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'NewP@ss123'})
    assert r.json['code'] == 0
    assert r.json['data']['role'] == 'finance'


def test_login_wrong_password(client, admin_user):
    """错误密码"""
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong'})
    assert r.json['code'] == 1
    assert '密码' in r.json['message']


def test_login_lock_after_5_failures(client, admin_user):
    """5 次失败后锁定"""
    for _ in range(5):
        r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong'})
    # 第 6 次应被锁定
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'NewP@ss123'})
    assert r.json['code'] == 1
    assert '锁定' in r.json['message']


def test_login_empty(client, admin_user):
    """空账号密码"""
    r = client.post('/api/auth/login', json={'username': '', 'password': ''})
    assert r.json['code'] == 1


def test_md5_to_pbkdf2_upgrade(app, client, admin_user):
    """MD5 密码自动升级到 pbkdf2"""
    # 把 admin 密码设回 MD5
    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = hashlib.md5(b'NewP@ss123').hexdigest()  # 32 字符
        db.session.commit()

    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'NewP@ss123'})
    assert r.json['code'] == 0

    # 检查 hash 已被升级
    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        assert len(admin.password_hash) > 50  # pbkdf2 格式
        assert admin.password_hash != hashlib.md5(b'NewP@ss123').hexdigest()


def test_me_unauthenticated(client):
    """未登录调 me"""
    r = client.get('/api/auth/me')
    assert r.json['code'] == 401


def test_me_authenticated(admin_client, admin_user):
    """已登录调 me"""
    r = admin_client.get('/api/auth/me')
    assert r.json['code'] == 0
    assert r.json['data']['username'] == 'admin'


def test_change_password_weak(admin_client):
    """弱密码被拒"""
    r = admin_client.post('/api/auth/change-password',
                          json={'old_password': 'NewP@ss123', 'new_password': '123'})
    assert r.json['code'] == 1


def test_change_password_wrong_old(admin_client):
    """原密码错误"""
    r = admin_client.post('/api/auth/change-password',
                          json={'old_password': 'wrong', 'new_password': 'NewP@ss2026!'})
    assert r.json['code'] == 1


def test_change_password_success(admin_client):
    """改密成功"""
    r = admin_client.post('/api/auth/change-password',
                          json={'old_password': 'NewP@ss123', 'new_password': 'NewP@ss2026!'})
    assert r.json['code'] == 0


def test_logout(admin_client):
    """登出"""
    r = admin_client.get('/api/auth/logout')
    assert r.json['code'] == 0
    # 登出后 me 应失败
    r = admin_client.get('/api/auth/me')
    assert r.json['code'] == 401


def test_login_rate_limit(client, admin_user):
    """O2 决策：登录限速 10 次/分钟"""
    # 11 次错误登录
    for i in range(12):
        r = client.post('/api/auth/login', json={'username': 'admin', 'password': f'wrong{i}'})
        if r.status_code == 429:
            return  # 限速拦截成功
    pytest.fail('限速未触发')


def test_role_client_binding(app):
    """C 决策：客户端类型与角色严格绑定"""
    from threading import Thread
    import time
    from werkzeug.serving import make_server
    from utils.ratelimit import _limiter

    # 创建财务版 app（finance 客户端）
    from app import create_app
    from config import Config
    finance_app = create_app('finance')
    server = make_server('127.0.0.1', 0, finance_app)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    # 在 app context 里创建报销人 + 重置 admin + 清限速
    with app.app_context():
        from models.models import SysUser
        from werkzeug.security import generate_password_hash
        # 清限速
        _limiter.clear()
        # 重置 admin
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = generate_password_hash('NewP@ss123')
        admin.failure_count = 0
        admin.locked_until = None
        # 创建报销人
        u = SysUser(
            username='reimb_test',
            real_name='测试',
            role='reimburser',
            staff_type='在编',
            account_status='normal',
            password_hash=generate_password_hash('Test@001!'),
        )
        from models import db
        db.session.add(u)
        db.session.commit()

    # 用 finance 客户端登录报销人 → 应被拒
    import requests
    r = requests.post(f'http://127.0.0.1:{port}/api/auth/login',
                      json={'username': 'reimb_test', 'password': 'Test@001!'})
    assert r.json()['code'] == 1
    assert '客户端' in r.json()['message'] or '财务版' in r.json()['message']

    server.shutdown()


def test_client_type_wildcard(client, admin_user):
    """client_type='*' 跳过客户端类型检查（测试模式）"""
    # admin_client 用的就是 finance 客户端
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'NewP@ss123'})
    # admin 是 finance 角色，与 finance 客户端匹配 → 成功
    assert r.json['code'] == 0
