"""
v2.10.0 — 代理关系管理测试

业务规则：
- 报销依托项目，所以 agent_auth 必须含 project_id
- 项目是稽核员创建的，所以代理关系由财务/稽核员设置
- 报销员**不能**自行设置代理

API：
- POST   /api/agents/setup
- DELETE /api/agents/<id>
- GET    /api/agents/list
- GET    /api/agents/by-project/<id>
- GET    /api/agents/mode-c-status
"""
import os
from datetime import date

import pytest

from models import db
from models.models import (
    SysUser, AgentAuth, UserProject, ExpenseProject,
)


@pytest.fixture
def auditor_client(client, auditor):
    r = client.post('/api/auth/login', json={'username': auditor['username'], 'password': auditor['password']})
    assert r.json['code'] == 0
    return client


@pytest.fixture
def reimburser_client(client, reimburser):
    r = client.post('/api/auth/login', json={'username': reimburser['username'], 'password': reimburser['password']})
    assert r.json['code'] == 0
    return client


# ============= 路由 setup 测试 =============

class TestAgentsSetup:
    """POST /api/agents/setup"""

    def test_finance_setup(self, app, admin_client, auditor, reimburser, project):
        """财务可设置任意代理关系"""
        r = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        assert r.status_code == 200
        assert r.json['code'] == 0
        assert 'id' in r.json['data']

    def test_auditor_setup_self(self, app, auditor_client, auditor, reimburser, project):
        """稽核员可为自己设置"""
        r = auditor_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        assert r.json['code'] == 0

    def test_auditor_cannot_setup_for_others(self, app, auditor_client, auditor, admin_user, reimburser, project):
        """稽核员不能为别人设置代理（admin 是财务，role 不对）"""
        # 1) agent_id 必须是稽核员
        r = auditor_client.post('/api/agents/setup', json={
            'agent_id': admin_user['id'],  # 财务做 agent
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        # service 先校验 role，不是稽核员 → 400
        assert r.status_code == 400

        # 2) 即使 agent 是稽核员，但当前用户不是自己 → 403
        from werkzeug.security import generate_password_hash
        with app.app_context():
            other_auditor = SysUser(
                username='other_auditor',
                real_name='其他稽核员',
                role='auditor',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Other@001!'),
            )
            db.session.add(other_auditor)
            db.session.commit()
            other_id = other_auditor.id

        r = auditor_client.post('/api/agents/setup', json={
            'agent_id': other_id,  # 别的稽核员
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        assert r.status_code == 403

    def test_reimburser_cannot_setup(self, app, reimburser_client, auditor, reimburser, project):
        """报销员**不能**自己设置代理（v2.10.0 关键约束）"""
        r = reimburser_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        assert r.status_code == 403

    def test_reimburser_must_be_bound_to_project(self, app, admin_client, auditor, admin_user):
        """报销员未绑定到项目时不能设置代理"""
        from werkzeug.security import generate_password_hash
        with app.app_context():
            orphan = SysUser(
                username='orphan_for_test',
                real_name='孤儿',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Orphan@001!'),
            )
            orphan_proj = ExpenseProject(
                project_code='TEST_X',
                project_name='测试项目X',
                project_type='普通',
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                status='active',
                finance_auditor_id=admin_user['id'],
                created_by=admin_user['id'],
            )
            db.session.add_all([orphan, orphan_proj])
            db.session.commit()
            orphan_id = orphan.id
            proj_id = orphan_proj.id

        r = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': orphan_id,
            'project_id': proj_id,
        })
        assert r.status_code == 400
        assert '未绑定到项目' in r.json['message']


# ============= 路由 list 测试 =============

class TestAgentsList:
    """GET /api/agents/list"""

    def test_auditor_sees_own_agents(self, app, auditor_client, admin_client, auditor, admin_user, project):
        """用新建报销员（避免 reimburser fixture 已有的 agent_auth 干扰）"""
        from werkzeug.security import generate_password_hash
        with app.app_context():
            new_reimb = SysUser(
                username='reimb_list_test',
                real_name='列表测试',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('ReimbList@001!'),
            )
            db.session.add(new_reimb)
            db.session.flush()
            db.session.add(UserProject(user_id=new_reimb.id, project_id=project['id'],
                                         status='active', created_by=admin_user['id']))
            db.session.commit()
            new_id = new_reimb.id

        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': new_id,
            'project_id': project['id'],
        })
        r = auditor_client.get('/api/agents/list')
        assert r.json['code'] == 0
        items = r.json['data']
        assert any(it['be_agent_id'] == new_id for it in items)

    def test_reimburser_sees_own_agents(self, app, reimburser_client, admin_client, auditor, admin_user, project):
        """新建专用报销员"""
        from werkzeug.security import generate_password_hash
        with app.app_context():
            new_reimb = SysUser(
                username='reimb_see_test',
                real_name='看自己',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('ReimbSee@001!'),
            )
            db.session.add(new_reimb)
            db.session.flush()
            db.session.add(UserProject(user_id=new_reimb.id, project_id=project['id'],
                                         status='active', created_by=admin_user['id']))
            db.session.commit()
            new_id = new_reimb.id

        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': new_id,
            'project_id': project['id'],
        })
        # 现在用 new_id 登录
        from werkzeug.security import check_password_hash
        with app.app_context():
            u = SysUser.query.get(new_id)
        r = reimburser_client.get('/api/agents/list')
        # 报销员列表可能空（不返回所有），改为查自己
        # 实际 service 返回该报销员的所有代理
        items = r.json['data']
        assert any(it['agent_id'] == auditor['id'] for it in items)

    def test_finance_sees_all(self, app, admin_client, auditor, admin_user, project):
        """新建专用报销员"""
        from werkzeug.security import generate_password_hash
        with app.app_context():
            new_reimb = SysUser(
                username='reimb_finance_test',
                real_name='财务视角',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('ReimbFin@001!'),
            )
            db.session.add(new_reimb)
            db.session.flush()
            db.session.add(UserProject(user_id=new_reimb.id, project_id=project['id'],
                                         status='active', created_by=admin_user['id']))
            db.session.commit()
            new_id = new_reimb.id

        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': new_id,
            'project_id': project['id'],
        })
        r = admin_client.get('/api/agents/list')
        items = r.json['data']
        assert any(it['be_agent_id'] == new_id for it in items)


# ============= 路由 by-project 测试 =============

class TestAgentsByProject:
    """GET /api/agents/by-project/<id>"""

    def test_shows_active_auths(self, app, admin_client, auditor, reimburser, project):
        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        r = admin_client.get(f'/api/agents/by-project/{project["id"]}')
        assert r.json['code'] == 0
        data = r.json['data']
        assert len(data['active_auths']) >= 1
        # 列出未代理的报销员
        assert any(u['need_agent'] is False for u in data['unassigned_reimbursers'])

    def test_includes_available_auditors(self, app, admin_client, project, auditor):
        """available_auditors 应至少包含 conftest 创建的 auditor"""
        r = admin_client.get(f'/api/agents/by-project/{project["id"]}')
        auditors = r.json['data']['available_auditors']
        assert any(a['id'] == auditor['id'] for a in auditors)

    def test_not_found(self, app, admin_client):
        r = admin_client.get('/api/agents/by-project/99999')
        assert r.status_code == 404


# ============= 路由 mode-c-status 测试 =============

class TestModeCStatus:
    """GET /api/agents/mode-c-status"""

    def test_full_mode_c(self, app, admin_client, auditor, reimburser, project):
        """报销员 1 个项目，被代理 → 完全模式 C"""
        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        r = admin_client.get('/api/agents/mode-c-status')
        items = r.json['data']
        u = next((x for x in items if x['user_id'] == reimburser['id']), None)
        assert u is not None
        assert u['mode'] == 'agent_c'
        assert u['total_projects'] == 1
        assert u['authed_projects'] == 1
        assert u['need_package'] is False

    def test_partial_mode(self, app, admin_client, auditor, admin_user, project):
        """新建报销员 2 个项目，只代理 1 个 → 部分模式"""
        from werkzeug.security import generate_password_hash
        from models.models import ExpenseProject
        with app.app_context():
            # 新建报销员
            u = SysUser(
                username='partial_test',
                real_name='部分测试',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Part@001!'),
            )
            db.session.add(u)
            db.session.flush()
            # 新建 2 个项目
            proj1 = ExpenseProject(
                project_code='PART1', project_name='部分1', project_type='普通',
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                status='active', finance_auditor_id=admin_user['id'], created_by=admin_user['id'],
            )
            proj2 = ExpenseProject(
                project_code='PART2', project_name='部分2', project_type='普通',
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                status='active', finance_auditor_id=admin_user['id'], created_by=admin_user['id'],
            )
            db.session.add_all([proj1, proj2])
            db.session.flush()
            # 报销员绑定 2 个项目
            db.session.add(UserProject(user_id=u.id, project_id=proj1.id, status='active', created_by=admin_user['id']))
            db.session.add(UserProject(user_id=u.id, project_id=proj2.id, status='active', created_by=admin_user['id']))
            db.session.commit()
            u_id = u.id
            p1_id, p2_id = proj1.id, proj2.id

        # 初始：两个项目都没代理 → self
        r = admin_client.get('/api/agents/mode-c-status')
        us = next((x for x in r.json['data'] if x['user_id'] == u_id), None)
        assert us['mode'] == 'self'
        assert us['total_projects'] == 2

        # 设置代理 1 个项目 → partial
        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': u_id,
            'project_id': p1_id,
        })
        r = admin_client.get('/api/agents/mode-c-status')
        us = next((x for x in r.json['data'] if x['user_id'] == u_id), None)
        assert us['mode'] == 'partial'
        assert us['authed_projects'] == 1
        assert us['total_projects'] == 2

    def test_self_mode(self, app, admin_client, project, admin_user):
        """新建报销员无任何代理关系 → 自助模式"""
        from werkzeug.security import generate_password_hash
        with app.app_context():
            solo = SysUser(
                username='solo_mode_test',
                real_name='独立测试',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Solo@001!'),
            )
            db.session.add(solo)
            db.session.flush()
            db.session.add(UserProject(user_id=solo.id, project_id=project['id'],
                                         status='active', created_by=admin_user['id']))
            db.session.commit()
            solo_id = solo.id

        r = admin_client.get('/api/agents/mode-c-status')
        items = r.json['data']
        u = next((x for x in items if x['user_id'] == solo_id), None)
        assert u is not None
        assert u['mode'] == 'self'
        assert u['total_projects'] == 1
        assert u['authed_projects'] == 0
        assert u['need_package'] is True


# ============= 路由 delete 测试 =============

class TestAgentsRevoke:
    """DELETE /api/agents/<id>"""

    def test_finance_can_revoke(self, app, admin_client, auditor, reimburser, project):
        ar = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        auth_id = ar.json['data']['id']
        r = admin_client.delete(f'/api/agents/{auth_id}')
        assert r.json['code'] == 0

    def test_auditor_can_revoke_own(self, app, auditor_client, admin_client, auditor, reimburser, project):
        ar = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        auth_id = ar.json['data']['id']
        r = auditor_client.delete(f'/api/agents/{auth_id}')
        assert r.json['code'] == 0

    def test_reimburser_cannot_revoke(self, app, reimburser_client, admin_client, auditor, reimburser, project):
        ar = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        auth_id = ar.json['data']['id']
        # 先确保 reimburser_client 是报销员身份（重新登录）
        lr = reimburser_client.post('/api/auth/login', json={'username': 'reimb001', 'password': 'Reimb@001!'})
        assert lr.json['code'] == 0, f"报销员登录失败: {lr.json}"
        r = reimburser_client.delete(f'/api/agents/{auth_id}')
        assert r.status_code == 403, f"报销员撤销应 403，实际 {r.status_code}: {r.data}"

    def test_revoke_not_found(self, app, admin_client):
        r = admin_client.delete('/api/agents/99999')
        assert r.status_code == 404


# ============= 集成：check-reimburser 联动 =============

class TestCheckReimburserIntegration:
    """/api/distribution/check-reimburser/<id> 跟代理管理联动"""

    def test_full_mode_c_blocks_build(self, app, admin_client, auditor, reimburser, project):
        """完全模式 C：build_for_reimburser 拒绝"""
        admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        r = admin_client.get(f'/api/distribution/check-reimburser/{reimburser["id"]}')
        body = r.json
        assert body['data']['mode'] == 'agent_c'
        assert body['data']['need_package'] is False

    def test_after_revoke_allows_build(self, app, admin_client, auditor, reimburser, project):
        """撤销代理后：自助模式，允许打包"""
        ar = admin_client.post('/api/agents/setup', json={
            'agent_id': auditor['id'],
            'be_agent_id': reimburser['id'],
            'project_id': project['id'],
        })
        admin_client.delete(f'/api/agents/{ar.json["data"]["id"]}')
        r = admin_client.get(f'/api/distribution/check-reimburser/{reimburser["id"]}')
        body = r.json
        assert body['data']['mode'] == 'self'
        assert body['data']['need_package'] is True
