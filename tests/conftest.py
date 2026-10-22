"""
pytest 配置 + fixture
- 每个测试用临时数据库
- 自动创建表
- 提供基础测试夹具
"""
import os
import sys
import tempfile

# 把项目根加到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask

from config import Config
from models import db


@pytest.fixture
def test_db_path(tmp_path):
    """每个测试独立的临时数据库"""
    db_path = tmp_path / 'test.db'
    return str(db_path)


@pytest.fixture
def app(test_db_path, monkeypatch, tmp_path):
    """创建测试 app - 使用 * 客户端以跳过客户端类型检查"""
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{test_db_path}')

    from pathlib import Path
    # 强制 BASE_DIR 指向真实项目目录（sandbox 路径不一致问题）
    real_base = Path('/workspace/reimbursement-app').resolve()
    monkeypatch.setattr(Config, 'BASE_DIR', real_base)
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', real_base / 'uploads')
    monkeypatch.setattr(Config, 'RBAG_TEMP_DIR', real_base / 'rbag_temp')
    monkeypatch.setattr(Config, 'LOG_DIR', real_base / 'logs')

    from app import create_app
    flask_app = create_app('*')  # 测试模式：跳过客户端类型校验
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        db.create_all()
        from init_db import init_base_data
        init_base_data()
        # 初始化 schema_migration 表（v2.4.0 测试需要）
        from sqlalchemy import text as sa_text
        from datetime import date, datetime
        # 检查是否已有表
        sm_exists = db.session.execute(sa_text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migration'"
        )).fetchone()
        if not sm_exists:
            # 用真实字段建表
            db.session.execute(sa_text("""
                CREATE TABLE schema_migration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version VARCHAR(50) NOT NULL UNIQUE,
                    description TEXT,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    execution_time_ms INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'applied',
                    down_revision VARCHAR(50)
                )
            """))
            db.session.execute(sa_text(
                "INSERT INTO schema_migration (version, description, status, down_revision) VALUES ('v1.0.0', 'base', 'applied', NULL)"
            ))
            db.session.commit()
        # 初始化通知模板（v2.2.0）
        # + app_version 数据（v2.4.0）
        from models.models import NotificationTemplate, AppVersion
        existing = {r[1] for r in db.session.execute(sa_text("PRAGMA table_info(app_version)")).fetchall()}
        if 'version' in existing and AppVersion.query.count() == 0:
            versions = [
                ('v1.0.0', date(2026, 8, 20), None, '报销稽核系统首发', '# 报销稽核系统 v1.0.0\n\n## ✨ 核心功能\n- T0-T5 全链路', 0),
                ('v1.1.0', date(2026, 8, 21), 'v1.0.0', '附件上传', '# v1.1.0\n\n## ✨ 新增\n- 附件', 0),
                ('v2.0.0', date(2026, 8, 22), 'v1.3.0', 'D3 决策：终审独立审计', '# v2.0.0\n\n## 🔍 审计', 0),
                ('v2.1.0', date(2026, 8, 23), 'v2.0.0', 'D3 决策：真双签', '# v2.1.0\n\n## 🤝 双签', 0),
                ('v2.2.0', date(2026, 8, 24), 'v2.1.0', '公告/通知系统', '# v2.2.0\n\n## 🔔 通知', 0),
                ('v2.3.0', date(2026, 8, 25), 'v2.2.0', '数据导入向导', '# v2.3.0\n\n## 📥 导入', 0),
                ('v2.4.0', date(2026, 8, 25), 'v2.3.0', 'D3 UI 加强：决策链', '# v2.4.0\n\n## 🔍 D3 加强', 0),
            ]
            for ver, d, min_req, title, log, mand in versions:
                db.session.add(AppVersion(
                    version=ver, release_date=d,
                    min_required_version=min_req, title=title,
                    changelog=log, mandatory=bool(mand),
                ))
            db.session.commit()
        from models.models import NotificationTemplate
        from sqlalchemy import text
        existing = {r[1] for r in db.session.execute(text("PRAGMA table_info(notification_template)")).fetchall()}
        if 'type' in existing and NotificationTemplate.query.count() == 0:
            templates = [
                ('bill_approved', '报销单已批准', '您的报销单 {bill_no}（¥{amount}）已通过财务终审，等待归档。', 'normal'),
                ('bill_rejected', '报销单被驳回', '您的报销单 {bill_no} 被{operator}驳回：{reason}。请修改后重新提交。', 'high'),
                ('bill_auditor_rejected', '报销单初审未通过', '您的报销单 {bill_no} 被稽核员驳回：{reason}。请修改后重新提交。', 'high'),
                ('bill_pending_dual', '大额报销待双签', '报销单 {bill_no}（¥{amount}）主财务已通过，等待您作为第二签人批准。', 'high'),
                ('bill_overridden', '报销单状态被强制修改', '您的报销单 {bill_no} 状态由财务强制修改为 {new_status}。原因：{reason}。', 'urgent'),
                ('bill_dual_rejected', '双签被拒绝', '您作为主财务的报销单 {bill_no} 被第二签人拒绝：{reason}。', 'urgent'),
                ('system', '系统通知', '{content}', 'normal'),
            ]
            for t_type, title, content, prio in templates:
                db.session.add(NotificationTemplate(
                    type=t_type, title_template=title, content_template=content,
                    default_priority=prio, enabled=True, description=f'预置模板：{t_type}',
                ))
            db.session.commit()
        from utils.ratelimit import _limiter
        _limiter.clear()
        # 重置 admin 密码为 NewP@ss123（init_base_data 默认是 MD5('admin@2026')）
        from models.models import SysUser
        from werkzeug.security import generate_password_hash
        admin = SysUser.query.filter_by(username='admin').first()
        if admin:
            admin.password_hash = generate_password_hash('NewP@ss123')
            admin.failure_count = 0
            admin.locked_until = None
            db.session.commit()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Flask 测试客户端"""
    return app.test_client()


@pytest.fixture
def admin_user(app):
    """财务管理员（重置 init_base_data 创建的 admin 密码为 NewP@ss123）- 返回 dict"""
    from models.models import SysUser
    from werkzeug.security import generate_password_hash
    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        if admin:
            admin.password_hash = generate_password_hash('NewP@ss123')
            admin.failure_count = 0
            admin.locked_until = None
            db.session.commit()
            return {'id': admin.id, 'username': 'admin'}
        return {'id': 1, 'username': 'admin'}


@pytest.fixture
def admin_client(client, admin_user):
    """已登录财务的测试客户端"""
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'NewP@ss123'})
    assert r.json['code'] == 0, f'登录失败: {r.json}'
    return client


@pytest.fixture
def project(app, admin_user):
    """测试项目 - 返回 dict"""
    from models.models import ExpenseProject
    from datetime import date
    with app.app_context():
        p = ExpenseProject(
            project_code='TEST01',
            project_name='测试项目',
            project_type='普通',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status='active',
            finance_auditor_id=1,
            created_by=1,
        )
        db.session.add(p)
        db.session.commit()
        return {'id': p.id, 'code': 'TEST01'}


@pytest.fixture
def live_url(app):
    """启动 live server 给 requests 用 - 名字避开 pytest-flask 的 live_server"""
    from threading import Thread
    import time
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, app)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    yield f'http://127.0.0.1:{port}'
    server.shutdown()


@pytest.fixture
def auditor(app, admin_user):
    """测试稽核员 - 返回 dict"""
    from models.models import SysUser, PositionLevel, UserPosition
    from werkzeug.security import generate_password_hash
    from datetime import date
    with app.app_context():
        u = SysUser(
            username='audit001',
            real_name='稽核员A',
            role='auditor',
            staff_type='在编',
            account_status='normal',
            password_hash=generate_password_hash('Audit@001!'),
            failure_count=0,
        )
        db.session.add(u)
        db.session.flush()
        pos = PositionLevel.query.filter_by(level_code='BUREAU').first()
        if pos:
            db.session.add(UserPosition(user_id=u.id, position_id=pos.id, effective_date=date.today()))
        db.session.commit()
        return {'id': u.id, 'username': 'audit001', 'password': 'Audit@001!'}


@pytest.fixture
def reimburser(app, admin_user, project, auditor):
    """测试报销人 - 返回 dict"""
    from models.models import SysUser, AgentAuth, UserProject, PositionLevel, UserPosition
    from werkzeug.security import generate_password_hash
    from datetime import date
    with app.app_context():
        u = SysUser(
            username='reimb001',
            real_name='张三',
            role='reimburser',
            staff_type='在编',
            account_status='normal',
            password_hash=generate_password_hash('Reimb@001!'),
            failure_count=0,
        )
        db.session.add(u)
        db.session.flush()
        # 绑定项目
        db.session.add(UserProject(
            user_id=u.id, project_id=project['id'],
            status='active', created_by=admin_user['id'],
        ))
        # 代理关系
        db.session.add(AgentAuth(
            agent_id=auditor['id'], be_agent_id=u.id, project_id=project['id'],
            auth_start_date=date.today(), status='active',
            created_by=admin_user['id'],
        ))
        # 职务
        pos = PositionLevel.query.filter_by(level_code='DIVISION').first()
        if pos:
            db.session.add(UserPosition(user_id=u.id, position_id=pos.id, effective_date=date.today()))
        db.session.commit()
        return {'id': u.id, 'username': 'reimb001', 'password': 'Reimb@001!'}
