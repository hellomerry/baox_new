"""D3 增强：决策链 + 筛选测试"""
import pytest
import requests
from utils.ratelimit import _limiter
from werkzeug.security import generate_password_hash


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def _clear():
    _limiter.clear()


# ============= 决策链 API =============

def test_decision_chain_for_archived_bill(live_url, app, project, auditor, reimburser):
    """DC-1: 已归档单据的决策链"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_au.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})
    s_fin.post(f'{live_url}/api/bills/{bill_id}/finance-audit', json={'decision': 'approve', 'comment': '通过'})

    r = s_re.get(f'{live_url}/api/audit/decision-chain/{bill_id}')
    assert r.json()['code'] == 0
    data = r.json()['data']
    assert data['bill']['id'] == bill_id
    assert data['bill']['status'] == 'archived'
    # 至少：create + final_approve（submit 当前未写 audit_log）
    assert len(data['chain']) >= 2
    # final_approve 必须存在
    actions = {e['action'] for e in data['chain']}
    assert 'FINAL_APPROVE' in actions or 'final_approve' in actions


def test_decision_chain_includes_override(live_url, app, project, auditor, reimburser):
    """DC-2: override 操作进决策链"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')

    s_fin.post(f'{live_url}/api/bills/{bill_id}/override', json={
        'target_status': 'draft', 'reason': '数据错误回退到草稿状态',
    })

    r = s_re.get(f'{live_url}/api/audit/decision-chain/{bill_id}')
    data = r.json()['data']
    actions = {e['action'] for e in data['chain']}
    assert 'override' in actions or 'OVERRIDE_BILL' in actions


def test_decision_chain_includes_dual_sign(live_url, app, project, auditor, reimburser):
    """DC-3: 双签流程完整进决策链"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    # 第二签人
    with app.app_context():
        from models.models import SysUser, db
        u2 = SysUser(username='fin_dc', real_name='第二签人DC', role='finance',
                     staff_type='在编', account_status='normal',
                     password_hash=generate_password_hash('Fin2@001!'))
        db.session.add(u2)
        db.session.commit()
        fin2_id = u2.id

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 50000, 'accommodation_fee': 30000, 'other_fee': 20000,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_au.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})
    s_fin.post(f'{live_url}/api/bills/{bill_id}/finance-audit', json={
        'decision': 'approve', 'dual_signer_id': fin2_id, 'comment': '主审通过',
    })
    s_fin2 = login(live_url, 'fin_dc', 'Fin2@001!')
    s_fin2.post(f'{live_url}/api/bills/{bill_id}/dual-sign', json={
        'decision': 'approve', 'comment': '同意',
    })

    r = s_re.get(f'{live_url}/api/audit/decision-chain/{bill_id}')
    data = r.json()['data']
    sources = {e['source'] for e in data['chain']}
    assert 'finance_audit_log' in sources
    assert 'research_audit_log' in sources


def test_decision_chain_not_found(live_url, app, project, auditor, reimburser):
    """DC-4: 单据不存在"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/audit/decision-chain/99999')
    assert r.json()['code'] != 0


def test_decision_chain_others_forbidden(live_url, app, project, auditor, reimburser):
    """DC-5: 报销人不能看他人的决策链"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    # 创建另一个报销人
    with app.app_context():
        from models.models import SysUser, UserProject, db
        other = SysUser(username='other_reim', real_name='他', role='reimburser',
                        staff_type='在编', account_status='normal',
                        password_hash=generate_password_hash('Other@001!'))
        db.session.add(other)
        db.session.commit()
        db.session.add(UserProject(user_id=other.id, project_id=project['id'],
                                   status='active', created_by=1))
        db.session.commit()
        other_id = other.id

    # other 创建单据
    s_other = login(live_url, 'other_reim', 'Other@001!')
    r = s_other.post(f'{live_url}/api/bills/create', json={
        'user_id': other_id, 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']

    # 报销人 1 尝试查看他人单据
    r = s_re.get(f'{live_url}/api/audit/decision-chain/{bill_id}')
    assert r.json()['code'] != 0


def test_decision_chain_own_bill_ok(live_url, app, project, auditor, reimburser):
    """DC-6: 报销人可看自己的决策链"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    r = s_re.get(f'{live_url}/api/audit/decision-chain/{bill_id}')
    assert r.json()['code'] == 0


# ============= 审计筛选 =============

def test_research_audit_filter_by_action(live_url, app, project, auditor, reimburser):
    """DC-7: 按 action 筛选"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_fin.post(f'{live_url}/api/bills/{bill_id}/override', json={
        'target_status': 'draft', 'reason': '测试 override 筛选',
    })

    r = s_fin.get(f'{live_url}/api/audit/research/filter?action=override')
    assert r.json()['code'] == 0
    items = r.json()['data']
    assert all(i['action'] == 'override' for i in items)
    assert any(i['bill_id'] == bill_id for i in items)


def test_research_audit_filter_by_bill_id(live_url, app, project, auditor, reimburser):
    """DC-8: 按单据筛选"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_fin.post(f'{live_url}/api/bills/{bill_id}/override', json={
        'target_status': 'draft', 'reason': '筛选测试',
    })

    r = s_fin.get(f'{live_url}/api/audit/research/filter?bill_id=' + str(bill_id))
    items = r.json()['data']
    assert all(i['bill_id'] == bill_id for i in items)


def test_research_audit_filter_by_date(live_url, app, project, auditor, reimburser):
    """DC-9: 按日期范围"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    today = '2026-08-25'
    r = s_fin.get(f'{live_url}/api/audit/research/filter?date_from={today}')
    assert r.json()['code'] == 0
    assert 'data' in r.json()


def test_research_audit_filter_combined(live_url, app, project, auditor, reimburser):
    """DC-10: 多条件组合"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    r = s_fin.get(f'{live_url}/api/audit/research/filter?action=override&limit=5')
    assert r.json()['code'] == 0
    assert 'total' in r.json()


def test_research_audit_filter_reimburser_forbidden(live_url, app, project, auditor, reimburser):
    """DC-11: 报销人不能访问审计筛选"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    r = s_re.get(f'{live_url}/api/audit/research/filter')
    assert r.status_code == 403


def test_research_audit_filter_pagination(live_url, app, project, auditor, reimburser):
    """DC-12: 分页"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    r = s_fin.get(f'{live_url}/api/audit/research/filter?limit=10&offset=0')
    assert r.json()['code'] == 0
    assert isinstance(r.json()['data'], list)
