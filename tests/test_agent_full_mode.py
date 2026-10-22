"""
v2.10.0 — 模式 C 混合部署测试

核心：稽核员 = 代填报销员（agent_auth 关系）
- 模式 C：报销员被稽核员代理 → 无需登录客户端
- 模式 B：报销员无代理 → 自助登录

覆盖：
- 考勤代填：稽核员可为有 AgentAuth 的报销员录考勤
- 通知优化：被代理的报销员收到状态变化时，稽核员也收到"代 [名字]"通知
- 客户端分发：被代理的报销员不能单独打包
- 路由：record-for / check-reimburser
"""
import os
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from models import db
from models.models import (
    SysUser, AttendanceRecord, AgentAuth, Notification, UserProject,
)


# ============= 考勤代填测试 =============
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

class TestAttendanceAgentFill:
    """考勤代填（v2.10.0 模式 C）"""

    def test_auditor_records_for_reimburser(self, app, admin_user, auditor, reimburser):
        """稽核员成功为代理的报销员录考勤"""
        from services.attendance_service import AttendanceService
        today = date.today()
        ok, msg = AttendanceService.record_for_user(
            agent_id=auditor['id'],
            be_agent_id=reimburser['id'],
            project_id=1,
            attendance_date=today,
            status='在岗',
            remark='代填测试',
        )
        assert ok, msg

        with app.app_context():
            att = AttendanceRecord.query.filter_by(
                user_id=reimburser['id'], attendance_date=today
            ).first()
            assert att is not None
            assert att.remark == '代填测试'

    def test_auditor_cannot_record_for_non_managed(self, app, admin_user, auditor):
        """稽核员不能为无代理关系的报销员录考勤"""
        from services.attendance_service import AttendanceService
        from werkzeug.security import generate_password_hash
        with app.app_context():
            other = SysUser(
                username='other_no_agent',
                real_name='无代理',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Other@001!'),
            )
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        ok, msg = AttendanceService.record_for_user(
            agent_id=auditor['id'],
            be_agent_id=other_id,
            project_id=1,
            attendance_date=date.today(),
            status='在岗',
        )
        assert not ok
        assert '代填权限' in msg

    def test_finance_cannot_record_for_others(self, app, admin_user, auditor, reimburser):
        """财务不能代填考勤（仅稽核员）"""
        from services.attendance_service import AttendanceService
        ok, msg = AttendanceService.record_for_user(
            agent_id=admin_user['id'],
            be_agent_id=reimburser['id'],
            project_id=1,
            attendance_date=date.today(),
            status='在岗',
        )
        assert not ok
        assert '稽核员' in msg

    def test_is_under_agent(self, app, admin_user, auditor, reimburser):
        from services.attendance_service import AttendanceService
        with app.app_context():
            assert AttendanceService.is_under_agent(reimburser['id']) is True

    def test_get_agents_for(self, app, admin_user, auditor, reimburser):
        from services.attendance_service import AttendanceService
        with app.app_context():
            agents = AttendanceService.get_agents_for(reimburser['id'])
            assert auditor['id'] in agents


class TestAttendanceRoutes:
    """考勤路由测试"""

    def test_record_for_auditor(self, app, auditor_client, auditor, reimburser, project):
        """稽核员代填路由"""
        r = auditor_client.post(
            f'/api/attendance/record-for/{reimburser["id"]}',
            json={
                'attendance_date': date.today().isoformat(),
                'project_id': project['id'],
                'work_hours': 8.0,
                'is_overnight': False,
                'location': '北京',
            }
        )
        assert r.status_code == 200
        assert r.json['code'] == 0

    def test_record_for_reimburser_forbidden(self, app, reimburser_client, reimburser):
        """报销员不能调用代填路由"""
        r = reimburser_client.post(
            f'/api/attendance/record-for/{reimburser["id"]}',
            json={'attendance_date': date.today().isoformat(), 'project_id': 1, 'work_hours': 8}
        )
        assert r.status_code == 403

    def test_record_for_self(self, app, auditor_client, auditor):
        """稽核员为自己（不是报销员）代填应被拒"""
        r = auditor_client.post(
            f'/api/attendance/record-for/{auditor["id"]}',
            json={'attendance_date': date.today().isoformat(), 'project_id': 1, 'work_hours': 8}
        )
        # service 校验 be_agent.role == 'reimburser' → 失败
        assert r.json['code'] != 0


# ============= 通知优化测试 =============

class TestNotificationProxy:
    """通知优化：被代理的报销员，稽核员也收到"""

    def test_reimburser_gets_proxy_notification(self, app, admin_user, auditor, reimburser):
        """给报销员发通知时，稽核员收到带'代 [名字]'前缀的副本"""
        from services.notification_service import send_notification
        with app.app_context():
            r = SysUser.query.get(reimburser['id'])
            real_name = r.real_name
            send_notification(
                user_id=reimburser['id'],
                notification_type='test_type',
                title='测试通知',
                content='测试内容',
            )

            n = Notification.query.filter_by(user_id=reimburser['id'], title='测试通知').first()
            assert n is not None

            n_proxy = Notification.query.filter_by(
                user_id=auditor['id'], type='test_type'
            ).first()
            assert n_proxy is not None
            assert '代' in n_proxy.title
            assert real_name in n_proxy.title

    def test_self_mode_reimburser_no_proxy(self, app, admin_user):
        """无代理的报销员只收到自己的通知"""
        from services.notification_service import send_notification
        from werkzeug.security import generate_password_hash
        with app.app_context():
            solo = SysUser(
                username='solo_no_agent',
                real_name='独立',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Solo@001!'),
            )
            db.session.add(solo)
            db.session.commit()
            solo_id = solo.id

            send_notification(
                user_id=solo_id,
                notification_type='test_type',
                title='独立通知',
            )

            # 独立报销员自己收到
            assert Notification.query.filter_by(user_id=solo_id, title='独立通知').count() == 1

            # 没有稽核员代理 → 其他账号都不该收到
            assert Notification.query.filter(
                Notification.user_id != solo_id,
                Notification.title.like('%代 独立%')
            ).count() == 0


# ============= 客户端分发 =============

class TestCheckReimburserStatus:
    """检查报销员的部署模式"""

    def test_managed_reimburser_status(self, app, admin_client, auditor, reimburser):
        r = admin_client.get(f'/api/distribution/check-reimburser/{reimburser["id"]}')
        assert r.status_code == 200
        body = r.json
        assert body['data']['mode'] == 'agent_c'
        assert body['data']['need_package'] is False
        assert body['data']['proxy_auditor']['id'] == auditor['id']

    def test_self_reimburser_status(self, app, admin_client, project):
        from werkzeug.security import generate_password_hash
        from models import db
        with app.app_context():
            solo = SysUser(
                username='solo_for_check',
                real_name='独立',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Solo@001!'),
            )
            db.session.add(solo)
            db.session.flush()
            # 绑项目（独立=有项目但无代理）
            db.session.add(UserProject(
                user_id=solo.id, project_id=project['id'],
                status='active', created_by=1,
            ))
            db.session.commit()
            solo_id = solo.id

        r = admin_client.get(f'/api/distribution/check-reimburser/{solo_id}')
        body = r.json
        assert body['data']['mode'] == 'self', f"期望 self 但得到 {body['data']['mode']}"
        assert body['data']['need_package'] is True

    def test_build_blocked_for_managed_reimburser(self, app, admin_client, auditor, reimburser):
        """被代理的报销员不能单独打包（v2.10.0 模式 C）"""
        r = admin_client.post(f'/api/distribution/build/reimburser/{reimburser["id"]}')
        assert r.status_code == 400
        assert '模式 C' in r.json['message'] or '代填' in r.json['message']
