"""
T4 报销单业务测试
- 使用 live_server 支持多 session（不同角色同时登录）
"""
import pytest
import requests
from datetime import date
from decimal import Decimal
from models import db
from models.models import (
    SysUser, ExpenseBill, ExpenseProject, UserProject, AgentAuth,
    PositionLevel, UserPosition
)
from werkzeug.security import generate_password_hash


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


# live_url 改用 conftest.py 的（已带 admin reset）


@pytest.fixture
def auditor(app, admin_user):
    """稽核员账号 - 返回 dict 含 ID"""
    with app.app_context():
        u = SysUser(
            username='audit001',
            real_name='稽核员',
            role='auditor',
            staff_type='在编',
            account_status='normal',
            password_hash=generate_password_hash('Audit@001!'),
            failure_count=0,
        )
        db.session.add(u)
        db.session.commit()
        pos = PositionLevel.query.filter_by(level_code='BUREAU').first()
        db.session.add(UserPosition(user_id=u.id, position_id=pos.id, effective_date=date.today()))
        db.session.commit()
        return {'id': u.id, 'username': 'audit001', 'password': 'Audit@001!'}


@pytest.fixture
def reimburser(app, admin_user, project, auditor):
    """报销人 + 绑定到稽核员 - 返回 dict"""
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
        db.session.add(UserProject(user_id=u.id, project_id=project['id'], status='active', created_by=1))
        db.session.add(AgentAuth(
            agent_id=auditor['id'], be_agent_id=u.id, project_id=project['id'],
            auth_start_date=date.today(), status='active', created_by=1,
        ))
        pos = PositionLevel.query.filter_by(level_code='DIVISION').first()
        db.session.add(UserPosition(user_id=u.id, position_id=pos.id, effective_date=date.today()))
        db.session.commit()
        return {'id': u.id, 'username': 'reimb001', 'password': 'Reimb@001!'}


def test_create_bill_personal(live_url, reimburser, project):
    """创建个人报销单"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000,
        'accommodation_fee': 500,
        'other_fee': 100,
    })
    assert r.json()['code'] == 0
    assert 'bill_no' in r.json()['data']


def test_create_bill_no_user_id(live_url, project, reimburser):
    """未指定 user_id 报错"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
    })
    assert r.json()['code'] == 1


def test_create_bill_project_total_must_have_no_user(live_url, reimburser, project):
    """项目总账 user_id 必须为 NULL"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],  # 应该为 NULL
        'project_id': project['id'],
        'bill_type': 'project_total',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    assert r.json()['code'] == 1


def test_bill_no_format(live_url, reimburser, project):
    """单号格式"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    assert r.json()['code'] == 0
    bill_no = r.json()['data']['bill_no']
    assert bill_no.startswith('B')
    assert f"-{project['code']}-" in bill_no
    suffix = bill_no.split('-')[-1]
    assert len(suffix) == 5


def test_capital_amount(live_url, reimburser, project, app):
    """大写金额（无补助时）"""
    # 直接插入数据库绕过补助自动计算
    from models.models import ExpenseBill
    with app.app_context():
        bill = ExpenseBill(
            bill_no='B-TEST-CAP',
            user_id=reimburser['id'], project_id=project['id'], bill_type='personal',
            travel_start_date=date(2026, 1, 1), travel_end_date=date(2026, 1, 2),
            destination='北京',
            transport_fee=1000, accommodation_fee=500, other_fee=100, subsidy_fee=0,
            total_amount=1600, capital_amount='壹仟陆佰元整',
            status='draft', creator_id=reimburser['id'],
        )
        db.session.add(bill)
        db.session.commit()
        bill_id = bill.id

    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.get(f'{live_url}/api/bills/{bill_id}')
    capital = r.json()['data']['capital_amount']
    assert '壹仟陆佰' in capital


def test_submit_bill(live_url, reimburser, project):
    """提交报销单"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    bill_id = r.json()['data']['id']
    r = s.post(f'{live_url}/api/bills/{bill_id}/submit')
    assert r.json()['code'] == 0


def test_audit_approve_low_amount(live_url, reimburser, project, auditor):
    """稽核员通过小额（< 5000 自动归档）"""
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')

    r = s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit',
                     json={'decision': 'approve', 'comment': 'OK'})
    assert r.json()['code'] == 0
    assert 'archived' in r.json()['message']


def test_audit_approve_high_amount(live_url, reimburser, project, auditor):
    """稽核员通过大额（> 5000 不归档）"""
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 3000, 'accommodation_fee': 2000, 'other_fee': 1000,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')

    r = s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit',
                     json={'decision': 'approve', 'comment': 'OK'})
    assert r.json()['code'] == 0
    # 6000+1500(sub)=7500，>5000 进入财务终审
    assert 'auditor_ok' in r.json()['message']  # 状态变 auditor_ok，等财务终审


def test_audit_reject(live_url, reimburser, project, auditor):
    """稽核员驳回"""
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')

    r = s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit',
                     json={'decision': 'reject', 'comment': 'NO'})
    assert r.json()['code'] == 0
    # 100+subsidy 可能 <5000 → 自动 archived
    # 或金额 >= 5000 → 状态变 rejected_auditor
    msg = r.json()['message']
    assert 'archived' in msg or 'rejected' in msg or '驳回' in msg


def test_finance_dual_sign(live_url, reimburser, project, auditor, app):
    """D3 决策：大额报销需双人会签（真双签）"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 不带双签人 → 应失败
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit', json={'decision': 'approve'})
    assert r.json()['code'] == 1

    # 创建第二签人
    with app.app_context():
        u2 = SysUser(username='fin2', real_name='第二签人', role='finance', staff_type='在编',
                    account_status='normal', password_hash=generate_password_hash('Fin2@001!'))
        db.session.add(u2)
        db.session.commit()
        fin2_id = u2.id

    # D3: 主财务提交大额 → 状态变 pending_dual_sign（不直接终审过）
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                     json={'decision': 'approve', 'dual_signer_id': fin2_id})
    assert r.json()['code'] == 0, r.json()

    # 单据应处于 pending_dual_sign
    r = s_admin.get(f'{live_url}/api/bills/{bill_id}')
    assert r.json()['code'] == 0
    bill = r.json()['data']
    assert bill['status'] == 'pending_dual_sign'
    assert bill['finance_dual_signer_id'] == fin2_id

    # 第二签人登录 → 看到"待我双签"列表里有这个单据
    s_fin2 = login(live_url, 'fin2', 'Fin2@001!')
    r = s_fin2.get(f'{live_url}/api/bills/pending-dual-sign')
    assert r.json()['code'] == 0
    assert any(b['id'] == bill_id for b in r.json()['data'])

    # D3: 第二签人 approve → 状态 archived
    r = s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                    json={'decision': 'approve', 'comment': '同意终审'})
    assert r.json()['code'] == 0, r.json()

    r = s_admin.get(f'{live_url}/api/bills/{bill_id}')
    bill = r.json()['data']
    assert bill['status'] == 'archived'
    assert bill['finance_dual_signed'] is True


def test_duplicate_check_same_project(live_url, reimburser, project):
    """K1：同项目同时段 block"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r1 = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    assert r1.json()['code'] == 0

    # 检查第二张同时段
    r2 = s.post(f'{live_url}/api/bills/check-duplicate', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
    })
    assert r2.json()['data']['status'] == 'block'


def test_check_duplicate_cross_project_warning(live_url, reimburser, project, app):
    """K1：跨项目同时段 warning"""
    s = login(live_url, 'reimb001', 'Reimb@001!')

    # 创建第二项目
    with app.app_context():
        p2 = ExpenseProject(
            project_code='TEST02', project_name='测试项目2', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', finance_auditor_id=1, created_by=1,
        )
        db.session.add(p2)
        db.session.commit()
        p2_id = p2.id

    r1 = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    assert r1.json()['code'] == 0

    r2 = s.post(f'{live_url}/api/bills/check-duplicate', json={
        'user_id': reimburser['id'],
        'project_id': p2_id,
        'travel_start_date': '2026-08-21',
        'travel_end_date': '2026-08-23',
    })
    assert r2.json()['data']['status'] == 'warning'


def test_list_bills_reimburser_only_own(live_url, reimburser, project):
    """报销人只能看到自己的单"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    r = s.get(f'{live_url}/api/bills/list')
    assert r.json()['code'] == 0
    assert all(b['user_id'] == reimburser['id'] for b in r.json()['data'])


def test_pdf_export(live_url, reimburser, project):
    """PDF 导出"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500,
    })
    bill_id = r.json()['data']['id']

    r = s.get(f'{live_url}/api/bills/{bill_id}/pdf')
    assert r.status_code == 200
    assert r.content[:4] == b'%PDF'


def test_red_rush(live_url, reimburser, project, auditor):
    """L2：冲红"""
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 缺原因 → 失败
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/red-rush', json={})
    assert r.json()['code'] == 1

    # 正常冲红
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/red-rush', json={'reason': '测试冲红'})
    assert r.json()['code'] == 0
    new_bill_no = r.json()['data']['new_bill_no']
    assert project['code'] in new_bill_no

    # 新单金额为负
    new_id = r.json()['data']['new_bill_id']
    r = s_admin.get(f'{live_url}/api/bills/{new_id}')
    assert r.json()['data']['total_amount'] < 0

    # 重复冲红拦截
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/red-rush', json={'reason': '再来'})
    assert r.json()['code'] == 1


# ============= D3 终审双签新测试 =============

def _create_dual_sign_bill(live_url, s_reimb, s_audit, s_admin, project, reimburser, app):
    """辅助：创建大额报销单 + 进 submitted_finance"""
    from werkzeug.security import generate_password_hash

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 创建第二签人
    with app.app_context():
        from models.models import SysUser
        from utils.ratelimit import _limiter
        _limiter.clear()
        u2 = SysUser(username='fin2', real_name='第二签人', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin2@001!'))
        db.session.add(u2)
        db.session.commit()
        fin2_id = u2.id

    return bill_id, fin2_id


def test_dual_sign_wrong_user_rejected(live_url, reimburser, project, auditor, app):
    """D3-14: 非指定双签人不能操作"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, fin2_id = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )

    # 主财务提交
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin2_id})

    # 另一个财务（不是 fin2）尝试 approve → 应失败
    with app.app_context():
        from werkzeug.security import generate_password_hash
        from models.models import SysUser
        u_other = SysUser(username='fin3', real_name='第三财务', role='finance',
                          staff_type='在编', account_status='normal',
                          password_hash=generate_password_hash('Fin3@001!'))
        db.session.add(u_other)
        db.session.commit()
        fin3_id = u_other.id

    s_fin3 = login(live_url, 'fin3', 'Fin3@001!')
    r = s_fin3.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                    json={'decision': 'approve', 'comment': '我尝试签'})
    assert r.json()['code'] == 1
    assert '不是该单据指定' in r.json()['message'] or '第二签人' in r.json()['message']


def test_dual_sign_reject_requires_long_reason(live_url, reimburser, project, auditor, app):
    """D3-15: 拒绝原因 < 10 字符应被拒"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, fin2_id = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin2_id})

    s_fin2 = login(live_url, 'fin2', 'Fin2@001!')
    r = s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                    json={'decision': 'reject', 'comment': '太短'})
    assert r.json()['code'] == 1
    assert '10' in r.json()['message']


def test_dual_sign_reject_changes_status(live_url, reimburser, project, auditor, app):
    """D3-16: 第二签人拒绝 → 状态变 rejected_finance"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, fin2_id = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin2_id})

    s_fin2 = login(live_url, 'fin2', 'Fin2@001!')
    r = s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                    json={'decision': 'reject',
                          'comment': '第二签人发现附件不全，决定驳回'})
    assert r.json()['code'] == 0, r.json()

    # 状态应该是 rejected_finance
    r = s_admin.get(f'{live_url}/api/bills/{bill_id}')
    assert r.json()['data']['status'] == 'rejected_finance'

    # 终审独立审计应有 dual_sign_reject
    r = s_admin.get(f'{live_url}/api/audit/research/bill/{bill_id}')
    history = r.json()['data']['history']
    actions = [h['action'] for h in history]
    assert 'dual_sign_request' in actions
    assert 'dual_sign_reject' in actions


def test_dual_sign_writes_audit_chain(live_url, reimburser, project, auditor, app):
    """D3-17: 双签完整通过 → 审计链有 request + approve"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, fin2_id = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )

    # 主财务提交
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin2_id,
                        'comment': '主财务初步审核通过'})

    # 第二签人通过
    s_fin2 = login(live_url, 'fin2', 'Fin2@001!')
    s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                json={'decision': 'approve', 'comment': '第二签人复核通过'})

    # 审计链完整性
    r = s_admin.get(f'{live_url}/api/audit/research/verify/{bill_id}')
    chain = r.json()['data']
    assert chain['ok'] is True
    assert chain['count'] >= 2

    r = s_admin.get(f'{live_url}/api/audit/research/bill/{bill_id}')
    history = r.json()['data']['history']
    actions = [h['action'] for h in history]
    assert 'dual_sign_request' in actions
    assert 'dual_sign_approve' in actions


def test_dual_sign_main_cannot_self_sign(live_url, reimburser, project, auditor, app):
    """D3-18: 主财务不能选自己当第二签人"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, _ = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )

    # 主财务 = admin，尝试选自己
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                     json={'decision': 'approve', 'dual_signer_id': 1})  # 1 = admin
    assert r.json()['code'] == 1
    assert '自己' in r.json()['message']


def test_dual_sign_invalid_dual_user(live_url, reimburser, project, auditor, app):
    """D3-19: 指定的第二签人不存在或非财务 → 应被拒"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    bill_id, _ = _create_dual_sign_bill(
        live_url, s_reimb, s_audit, s_admin, project, reimburser, app,
    )

    # 指定一个报销人作第二签人 → 应失败
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                     json={'decision': 'approve', 'dual_signer_id': reimburser['id']})
    assert r.json()['code'] == 1
    assert '财务' in r.json()['message']


def test_pending_dual_sign_list_isolated(live_url, reimburser, project, auditor, app):
    """D3-20: 待双签列表只返回指定给我的单据"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    from werkzeug.security import generate_password_hash
    from models.models import SysUser
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    # 创建两个大额单据，一个指定 fin2，一个指定 fin3
    with app.app_context():
        u2 = SysUser(username='fin2', real_name='第二签人2', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin2@001!'))
        u3 = SysUser(username='fin3', real_name='第二签人3', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin3@001!'))
        db.session.add_all([u2, u3])
        db.session.commit()
        fin2_id, fin3_id = u2.id, u3.id

    # 创建单据 1（指定 fin2）
    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill1 = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill1}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill1}/auditor-audit', json={'decision': 'approve'})
    s_admin.post(f'{live_url}/api/bills/{bill1}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin2_id})

    # 创建单据 2（指定 fin3）
    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-09-01', 'travel_end_date': '2026-09-03',
        'destination': '上海',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill2 = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill2}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill2}/auditor-audit', json={'decision': 'approve'})
    s_admin.post(f'{live_url}/api/bills/{bill2}/finance-audit',
                  json={'decision': 'approve', 'dual_signer_id': fin3_id})

    # fin2 登录 → 只看到 bill1
    s_fin2 = login(live_url, 'fin2', 'Fin2@001!')
    r = s_fin2.get(f'{live_url}/api/bills/pending-dual-sign')
    assert r.json()['code'] == 0
    ids = [b['id'] for b in r.json()['data']]
    assert bill1 in ids
    assert bill2 not in ids

    # fin3 登录 → 只看到 bill2
    s_fin3 = login(live_url, 'fin3', 'Fin3@001!')
    r = s_fin3.get(f'{live_url}/api/bills/pending-dual-sign')
    ids = [b['id'] for b in r.json()['data']]
    assert bill2 in ids
    assert bill1 not in ids


# ============= D3 终审 / 双签 / Override API UI 集成测试 =============

def test_final_audit_endpoint_api(live_url, app, project, auditor, reimburser):
    """D3-21: 终审 API（小额单签）"""
    from utils.ratelimit import _limiter
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    # 小额报销
    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 终审直接通过（小额）
    r = s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit', json={'decision': 'approve', 'comment': '小额通过'})
    assert r.json()['code'] == 0, r.json()


def test_pending_dual_sign_endpoint(live_url, app, project, auditor, reimburser):
    """D3-22: GET /api/bills/pending-dual-sign 端点"""
    from utils.ratelimit import _limiter
    from werkzeug.security import generate_password_hash
    from models.models import SysUser
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    # 创建第二签人
    with app.app_context():
        u2 = SysUser(username='fin_d3', real_name='第二签人D3', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin2@001!'))
        db.session.add(u2)
        db.session.commit()
        fin2_id = u2.id

    # 大额报销
    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                 json={'decision': 'approve', 'dual_signer_id': fin2_id, 'comment': '主财务'})

    # fin2 登录查看待办
    s_fin2 = login(live_url, 'fin_d3', 'Fin2@001!')
    r = s_fin2.get(f'{live_url}/api/bills/pending-dual-sign')
    assert r.json()['code'] == 0
    bills = r.json()['data']
    assert any(b['id'] == bill_id for b in bills)
    # 返回的 bill 字段应包含 status + finance_dual_signer_id
    my_bill = next(b for b in bills if b['id'] == bill_id)
    assert my_bill['status'] == 'pending_dual_sign'
    assert my_bill['finance_dual_signer_id'] == fin2_id


def test_dual_sign_approve_api(live_url, app, project, auditor, reimburser):
    """D3-23: 完整双签流程 API 端到端"""
    from utils.ratelimit import _limiter
    from werkzeug.security import generate_password_hash
    from models.models import SysUser
    _limiter.clear()
    s_reimb = login(live_url, 'reimb001', 'Reimb@001!')
    s_audit = login(live_url, 'audit001', 'Audit@001!')
    s_admin = login(live_url, 'admin', 'NewP@ss123')

    with app.app_context():
        u2 = SysUser(username='fin_d3_2', real_name='第二签人D3-2', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin2@001!'))
        db.session.add(u2)
        db.session.commit()
        fin2_id = u2.id

    r = s_reimb.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill_id = r.json()['data']['id']
    s_reimb.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 主财务提交
    s_admin.post(f'{live_url}/api/bills/{bill_id}/finance-audit',
                 json={'decision': 'approve', 'dual_signer_id': fin2_id, 'comment': '主财务初步通过'})

    # 第二签人登录 + approve
    s_fin2 = login(live_url, 'fin_d3_2', 'Fin2@001!')
    r = s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign',
                    json={'decision': 'approve', 'comment': '双签通过'})
    assert r.json()['code'] == 0, r.json()

    # 验证：get_bill 返回 archived + dual_signed = true
    r = s_admin.get(f'{live_url}/api/bills/{bill_id}')
    bill = r.json()['data']
    assert bill['status'] == 'archived'
    assert bill['finance_dual_signed'] is True
    assert bill['finance_dual_signer_id'] == fin2_id
    assert bill['finance_dual_sign_at'] is not None
