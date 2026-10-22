"""v2.4.0 应用升级向导测试"""
import pytest
import requests
from utils.ratelimit import _limiter


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def _clear():
    _limiter.clear()


# ============= 版本检查 =============

def test_current_version(live_url, app, project, auditor, reimburser):
    """UP-1: 当前版本"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/upgrade/current')
    assert r.json()['code'] == 0
    d = r.json()['data']
    # 在 conftest db 是 v1.0.0（db.create_all 没用迁移系统）
    # 但 app_version 表存在（v2.4.0 迁移）
    # 所以 current = None（schema_migration 是空的）
    # latest = v2.4.0
    assert d['latest'] == 'v2.4.0'


def test_check_update_already_latest(live_url, app, project, auditor, reimburser):
    """UP-2: 应用迁移后检查更新"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    # 先跑迁移到 v2.4.0
    from migrations.runner import MigrationManager
    with app.app_context():
        mgr = MigrationManager()
        mgr.upgrade('v2.4.0')
    r = s.get(f'{live_url}/api/upgrade/check')
    assert r.json()['code'] == 0
    d = r.json()['data']
    assert d['current_version'] == 'v2.4.0'
    assert d['has_update'] is False


def test_check_update_with_pending(live_url, app, project, auditor, reimburser):
    """UP-3: 检查到有待升级版本"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    # 强制设置当前为 v1.0.0
    from sqlalchemy import text
    with app.app_context():
        from models import db
        db.session.execute(text(
            "INSERT OR REPLACE INTO schema_migration (version, description, status, down_revision) VALUES ('v1.0.0', 'old', 'applied', NULL)"
        ))
        db.session.commit()
    r = s.get(f'{live_url}/api/upgrade/check')
    d = r.json()['data']
    assert d['has_update'] is True
    assert len(d['pending_versions']) >= 1


def test_list_versions(live_url, app, project, auditor, reimburser):
    """UP-4: 列出所有版本"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/upgrade/list')
    assert r.json()['code'] == 0
    items = r.json()['data']
    versions = {v['version'] for v in items}
    assert 'v1.0.0' in versions
    assert 'v2.4.0' in versions


def test_changelog(live_url, app, project, auditor, reimburser):
    """UP-5: 查 changelog"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/upgrade/changelog/v1.0.0')
    assert r.json()['code'] == 0
    d = r.json()['data']
    assert d['version'] == 'v1.0.0'
    assert 'changelog' in d
    assert 'v1.0.0' in d['changelog']


def test_changelog_not_found(live_url, app, project, auditor, reimburser):
    """UP-6: changelog 不存在"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/upgrade/changelog/v999.0.0')
    assert r.json()['code'] != 0


# ============= 预检 =============

def test_precheck(live_url, app, project, auditor, reimburser):
    """UP-7: 升级前预检"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/upgrade/precheck')
    assert r.json()['code'] == 0
    d = r.json()['data']
    assert 'checks' in d
    assert 'ok' in d
    # 必须有这些检查项
    names = {c['name'] for c in d['checks']}
    assert '数据库连接' in names
    assert '当前版本' in names


# ============= 执行升级 =============

def test_perform_upgrade(live_url, app, project, auditor, reimburser):
    """UP-8: 执行升级（从 v1.0.0 到最新）"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    # 设置当前为 v1.0.0
    from sqlalchemy import text
    with app.app_context():
        from models import db
        db.session.execute(text("DELETE FROM schema_migration"))
        db.session.execute(text(
            "INSERT INTO schema_migration (version, description, status, down_revision) VALUES ('v1.0.0', 'old', 'applied', NULL)"
        ))
        db.session.commit()

    r = s.post(f'{live_url}/api/upgrade/perform', json={})
    assert r.json()['code'] == 0, r.json()
    d = r.json()['data']
    assert d['success'] is True
    assert d['from_version'] == 'v1.0.0'
    assert d['to_version'] == 'v2.4.0'

    # 验证 schema_migration 表
    r2 = s.get(f'{live_url}/api/upgrade/current')
    assert r2.json()['data']['current'] == 'v2.4.0'


def test_perform_already_latest(live_url, app, project, auditor, reimburser):
    """UP-9: 已是最新"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    # 跑迁移到 v2.4.0
    from migrations.runner import MigrationManager
    with app.app_context():
        mgr = MigrationManager()
        mgr.upgrade('v2.4.0')
    r = s.post(f'{live_url}/api/upgrade/perform', json={})
    assert r.json()['code'] == 0
    d = r.json()['data']
    assert d['success'] is True
    assert d['from_version'] == 'v2.4.0'
    assert d['to_version'] == 'v2.4.0'


# ============= 权限 =============

def test_reimburser_cannot_access(live_url, app, project, auditor, reimburser):
    """UP-10: 报销人无访问权限"""
    _clear()
    s = login(live_url, 'reimb001', 'Reimb@001!')
    assert s.get(f'{live_url}/api/upgrade/check').status_code == 403
    assert s.get(f'{live_url}/api/upgrade/list').status_code == 403
    assert s.get(f'{live_url}/api/upgrade/changelog/v1.0.0').status_code == 403


def test_auditor_cannot_perform(live_url, app, project, auditor, reimburser):
    """UP-11: 稽核员无 perform 权限"""
    _clear()
    s = login(live_url, 'audit001', 'Audit@001!')
    r = s.post(f'{live_url}/api/upgrade/perform', json={})
    assert r.status_code == 403


# ============= Service 单测 =============

def test_version_compare():
    """UP-12: 版本比较"""
    from services.upgrade_service import version_compare, version_tuple
    assert version_tuple('v1.0.0') == (1, 0, 0)
    assert version_tuple('2.3.1') == (2, 3, 1)
    assert version_compare('v1.0.0', 'v1.0.0') == 0
    assert version_compare('v1.0.0', 'v2.0.0') == -1
    assert version_compare('v2.0.0', 'v1.0.0') == 1
    assert version_compare('v1.10.0', 'v1.9.0') == 1
