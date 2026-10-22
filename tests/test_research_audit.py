"""
D3 决策：终审独立审计测试
- /api/audit/research/list
- /api/audit/research/bill/<id>
- /api/audit/research/verify/<id>
- /api/audit/research/export/<id>
"""
import io
import os
import zipfile
import pytest
import requests
from threading import Thread
import time
from werkzeug.serving import make_server
from werkzeug.security import generate_password_hash

from models import db
from models.models import (
    SysUser, ExpenseProject, ExpenseBill, ResearchAuditLog,
)
from datetime import date


def login(base_url, username='admin', password='NewP@ss123'):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login',
               json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


@pytest.fixture
def research_bill(app, admin_user, project):
    """创建测试单据 + 终审审计记录"""
    with app.app_context():
        # 创建报销人
        u = SysUser(
            username='reimb_d3', real_name='张三', role='reimburser',
            staff_type='在编', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(u)
        db.session.flush()

        # 创建单据
        bill = ExpenseBill(
            bill_no='B-D3-TEST-001', user_id=u.id, project_id=project['id'],
            bill_type='personal', travel_start_date=date(2026, 1, 1),
            travel_end_date=date(2026, 1, 5), destination='北京',
            total_amount=200000, capital_amount='贰拾万',
            status='submitted_finance', creator_id=u.id,
        )
        db.session.add(bill)
        db.session.commit()
        bill_id = bill.id

    return {'id': bill_id, 'bill_no': 'B-D3-TEST-001'}


def test_research_audit_log_creation(app, research_bill, admin_user):
    """D3-1: log_research_audit() 创建记录"""
    from services.research_audit_service import log_research_audit, list_research_audits

    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        audit_id = log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='final_approve',
            reason='大额单据终审通过',
            original_status='submitted_finance',
            new_status='approved',
            auditor_role='finance',
        )
        assert audit_id > 0

        items = list_research_audits(bill_id=research_bill['id'])
        assert len(items) == 1
        assert items[0]['action'] == 'final_approve'
        assert items[0]['auditor_name'] == '系统管理员'
        assert items[0]['reason'] == '大额单据终审通过'


def test_research_audit_chain_verify(app, research_bill, admin_user):
    """D3-2: 终审链完整性校验"""
    from services.research_audit_service import (
        log_research_audit, verify_research_audit_chain,
    )

    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        # 终审通过
        log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='final_approve',
            original_status='submitted_finance',
            new_status='approved',
        )

        chain = verify_research_audit_chain(research_bill['id'])
        assert chain['ok'] is True
        assert chain['count'] == 1
        assert chain['last_action'] == 'final_approve'


def test_research_audit_api_list(live_url, app, research_bill, admin_user):
    """D3-3: /api/audit/research/list"""
    from services.research_audit_service import log_research_audit

    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='final_approve',
            reason='D3-3 测试',
        )

    s = login(live_url)
    r = s.get(f'{live_url}/api/audit/research/list')
    assert r.json()['code'] == 0
    assert len(r.json()['data']) >= 1
    assert any(item['reason'] == 'D3-3 测试' for item in r.json()['data'])


def test_research_audit_api_bill_history(live_url, app, research_bill, admin_user):
    """D3-4: /api/audit/research/bill/<id>"""
    from services.research_audit_service import log_research_audit

    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='final_reject',
            reason='金额超限',
        )
        log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='override',
            reason='经审批人协商后通过',
        )

    s = login(live_url)
    r = s.get(f'{live_url}/api/audit/research/bill/{research_bill["id"]}')
    assert r.json()['code'] == 0
    data = r.json()['data']
    assert len(data['history']) == 2
    assert data['chain']['ok'] is True
    assert data['chain']['count'] == 2


def test_research_audit_api_verify(live_url, app, research_bill, admin_user):
    """D3-5: /api/audit/research/verify/<id>"""
    s = login(live_url)
    r = s.get(f'{live_url}/api/audit/research/verify/{research_bill["id"]}')
    assert r.json()['code'] == 0
    # 无审计记录但金额未达阈值（业务允许）
    assert r.json()['data']['count'] == 0
    assert 'ok' in r.json()['data']


def test_research_audit_pdf_export(live_url, app, research_bill, admin_user):
    """D3-6: /api/audit/research/export/<id> 生成 PDF"""
    from services.research_audit_service import log_research_audit

    with app.app_context():
        admin = SysUser.query.filter_by(username='admin').first()
        log_research_audit(
            bill_id=research_bill['id'],
            auditor_id=admin.id,
            action='final_approve',
            reason='终审通过',
        )

    s = login(live_url)
    r = s.get(f'{live_url}/api/audit/research/export/{research_bill["id"]}')
    assert r.status_code == 200
    assert r.headers['content-type'] == 'application/pdf'
    # PDF 文件以 %PDF 开头
    assert r.content[:4] == b'%PDF'


def test_research_audit_non_finance_forbidden(live_url, app):
    """D3-7: 非财务不能查看终审审计"""
    with app.app_context():
        from werkzeug.security import generate_password_hash
        from utils.ratelimit import _limiter
        _limiter.clear()
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = generate_password_hash('NewP@ss123')
        admin.failure_count = 0
        # 创建一个稽核员
        auditor = SysUser(
            username='audit_d3', real_name='稽核D3', role='auditor',
            staff_type='在编', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(auditor)
        db.session.commit()

    s = requests.Session()
    r = s.post(f'{live_url}/api/auth/login',
               json={'username': 'audit_d3', 'password': 'Test@001'})
    assert r.json()['code'] == 0

    r = s.get(f'{live_url}/api/audit/research/list')
    # 稽核员被拒（仅财务可查看）
    assert r.json()['code'] == 1
    assert r.status_code == 403


# ============= D3 override 流程测试 =============

def test_override_requires_finance(live_url, app, research_bill, admin_user):
    """D3-8: override 仅财务可操作"""
    with app.app_context():
        from werkzeug.security import generate_password_hash
        from utils.ratelimit import _limiter
        _limiter.clear()
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = generate_password_hash('NewP@ss123')
        admin.failure_count = 0
        # 报销人
        u = SysUser(
            username='r_ovr', real_name='R', role='reimburser',
            staff_type='在编', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(u)
        db.session.commit()

    s = requests.Session()
    s.post(f'{live_url}/api/auth/login',
           json={'username': 'r_ovr', 'password': 'Test@001'})
    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={'target_status': 'approved', 'reason': '测试强制修改原因文本必须够长'},
    )
    assert r.status_code == 403
    assert r.json()['code'] == 1


def test_override_requires_long_reason(live_url, app, research_bill, admin_user):
    """D3-9: 原因 < 10 字符应被拒"""
    s = login(live_url)
    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={'target_status': 'approved', 'reason': '太短'},
    )
    assert r.json()['code'] == 1
    assert '10' in r.json()['message']


def test_override_requires_target_status(live_url, app, research_bill, admin_user):
    """D3-10: 缺 target_status 应被拒"""
    s = login(live_url)
    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={'reason': '一个足够长的原因文本用于通过验证'},
    )
    assert r.json()['code'] == 1
    assert '目标状态' in r.json()['message']


def test_override_success_writes_research_audit(live_url, app, research_bill, admin_user):
    """D3-11: override 成功 + 写 ResearchAuditLog"""
    s = login(live_url)

    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={
            'target_status': 'approved',
            'reason': '财务复核后强制通过，原稽核驳回理由不充分',
        },
    )
    assert r.json()['code'] == 0, r.json()

    # 验证：单据状态变了
    s2 = login(live_url)
    r2 = s2.get(f'{live_url}/api/audit/research/bill/{research_bill["id"]}')
    assert r2.json()['code'] == 0
    history = r2.json()['data']['history']
    assert len(history) == 1
    assert history[0]['action'] == 'override'
    assert history[0]['original_status'] == 'submitted_finance'
    assert history[0]['new_status'] == 'approved'
    assert '强制通过' in history[0]['reason']


def test_override_rejects_red_rush_status(live_url, app, research_bill, admin_user):
    """D3-12: 已冲红的单据不可 override"""
    s = login(live_url)
    # 标记为 red_rush
    with app.app_context():
        from models.models import ExpenseBill
        bill = ExpenseBill.query.get(research_bill['id'])
        bill.status = 'red_rush'
        db.session.commit()

    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={
            'target_status': 'approved',
            'reason': '尝试覆盖一个已冲红的单据',
        },
    )
    assert r.json()['code'] == 1
    assert '冲红' in r.json()['message']


def test_override_rejects_invalid_target(live_url, app, research_bill, admin_user):
    """D3-13: 非法目标状态应被拒"""
    s = login(live_url)
    r = s.post(
        f'{live_url}/api/bills/{research_bill["id"]}/override',
        json={
            'target_status': 'invalid_status',
            'reason': '试图切换到一个不存在的状态值用于测试',
        },
    )
    assert r.json()['code'] == 1
    assert '非法' in r.json()['message']
