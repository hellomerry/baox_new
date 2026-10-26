"""
稽核预检测试（考勤联动 + 调令校验）— 主线 ⑤⑦
"""
import requests
from datetime import date, datetime

import pytest

from models import db
from models.models import (
    SysUser, ExpenseBill, AttendanceRecord, PersonnelTransfer, AuditLog,
)
from werkzeug.security import generate_password_hash


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login',
               json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def _make_bill(user_id, project_id, start=date(2026, 5, 10), end=date(2026, 5, 12)):
    return ExpenseBill(
        bill_no=f'B-PC-{datetime.now().strftime("%H%M%S")}-{user_id}',
        user_id=user_id, project_id=project_id, bill_type='personal',
        travel_start_date=start, travel_end_date=end, destination='北京',
        total_amount=1000, capital_amount='壹仟元整',
        status='submitted_auditor', creator_id=user_id,
    )


def _add_attendance(user_id, project_id, d, status='出差', audit_status='approved',
                    created_by=1):
    db.session.add(AttendanceRecord(
        user_id=user_id, project_id=project_id, attendance_date=d,
        status=status, audit_status=audit_status, created_by=created_by,
    ))


# ============= 单元：考勤联动 =============

def test_attendance_all_ok(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'])
        db.session.add(bill)
        for d in (date(2026, 5, 10), date(2026, 5, 11), date(2026, 5, 12)):
            _add_attendance(reimburser['id'], project['id'], d)
        db.session.commit()

        from services.precheck_service import check_attendance_for_bill
        r = check_attendance_for_bill(bill)
        assert r['status'] == 'ok'
        assert '全部为出差' in r['message']


def test_attendance_mismatch_warning(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'])
        db.session.add(bill)
        _add_attendance(reimburser['id'], project['id'], date(2026, 5, 10))
        _add_attendance(reimburser['id'], project['id'], date(2026, 5, 11), status='在岗')
        _add_attendance(reimburser['id'], project['id'], date(2026, 5, 12))
        db.session.commit()

        from services.precheck_service import check_attendance_for_bill
        r = check_attendance_for_bill(bill)
        assert r['status'] == 'warning'
        assert '1 天考勤非出差' in r['message']
        assert '在岗' in r['message']


def test_attendance_missing_days(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'])
        db.session.add(bill)
        # 只录第 1 天，缺 2 天
        _add_attendance(reimburser['id'], project['id'], date(2026, 5, 10))
        db.session.commit()

        from services.precheck_service import check_attendance_for_bill
        r = check_attendance_for_bill(bill)
        assert r['status'] == 'warning'
        assert '2 天无考勤记录' in r['message']

        # 完全无记录
        bill2 = _make_bill(reimburser['id'], project['id'],
                           start=date(2026, 6, 1), end=date(2026, 6, 1))
        bill2.bill_no = 'B-PC-EMPTY'
        db.session.add(bill2)
        db.session.commit()
        r2 = check_attendance_for_bill(bill2)
        assert r2['status'] == 'warning'
        assert '1 天无考勤记录' in r2['message']


def test_attendance_rejected_not_counted(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'],
                          start=date(2026, 5, 10), end=date(2026, 5, 10))
        db.session.add(bill)
        _add_attendance(reimburser['id'], project['id'], date(2026, 5, 10),
                        status='出差', audit_status='rejected')
        db.session.commit()

        from services.precheck_service import check_attendance_for_bill
        r = check_attendance_for_bill(bill)
        assert r['status'] == 'warning'
        assert '考勤被驳回' in r['message']


def test_attendance_skip_for_project_total(app, admin_user, project):
    with app.app_context():
        bill = ExpenseBill(
            bill_no='B-PC-TOTAL', user_id=None, project_id=project['id'],
            bill_type='project_total',
            travel_start_date=date(2026, 5, 10), travel_end_date=date(2026, 5, 12),
            destination='北京', total_amount=5000, capital_amount='伍仟元整',
            status='submitted_auditor', creator_id=admin_user['id'],
        )
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import check_attendance_for_bill
        assert check_attendance_for_bill(bill)['status'] == 'skip'


# ============= 单元：调令校验 =============

def _borrowed_user(username='borrowed_pc'):
    u = SysUser.query.filter_by(username=username).first()
    if not u:
        u = SysUser(
            username=username, real_name='钱借调', role='reimburser',
            staff_type='借调', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(u)
        db.session.flush()
    return u


def test_transfer_skip_for_regular_staff(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'])  # 在编
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import check_transfer_for_bill
        r = check_transfer_for_bill(bill)
        assert r['status'] == 'skip'


def test_transfer_no_record_warning(app, admin_user, project):
    with app.app_context():
        u = _borrowed_user()
        bill = _make_bill(u.id, project['id'])
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import check_transfer_for_bill
        r = check_transfer_for_bill(bill)
        assert r['status'] == 'warning'
        assert '未找到有效调令' in r['message']


def test_transfer_covering_ok_and_name_match(app, admin_user, project):
    with app.app_context():
        u = _borrowed_user()
        db.session.add(PersonnelTransfer(
            transfer_type='borrow', real_name=u.real_name,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            operator_id=admin_user['id'], status='active', transfer_no='令〔2026〕7号',
        ))
        bill = _make_bill(u.id, project['id'])
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import check_transfer_for_bill
        r = check_transfer_for_bill(bill)
        assert r['status'] == 'ok'
        assert '令〔2026〕7号' in r['message']


def test_transfer_not_covering_warning(app, admin_user, project):
    with app.app_context():
        u = _borrowed_user('borrowed_pc2')
        # 调令在出差前已到期
        db.session.add(PersonnelTransfer(
            transfer_type='follow_training', real_name=u.real_name,
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 30),
            operator_id=admin_user['id'], status='active',
        ))
        bill = _make_bill(u.id, project['id'])
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import check_transfer_for_bill
        r = check_transfer_for_bill(bill)
        assert r['status'] == 'warning'
        assert '未覆盖出差期间' in r['message']


def test_summarize(app, admin_user, project, reimburser):
    with app.app_context():
        bill = _make_bill(reimburser['id'], project['id'])
        db.session.add(bill)
        db.session.commit()

        from services.precheck_service import run_prechecks, summarize
        s = summarize(run_prechecks(bill))
        # 无考勤 → warning；在编 → skip
        assert '[考勤联动]' in s
        assert '[调令校验]' not in s


# ============= 集成：初审落审计日志 + API =============

def test_audit_by_auditor_logs_precheck_warning(live_url, app, reimburser, project, auditor):
    """初审通过 + 存在预警 → 返回消息提示 + PRECHECK_WARNING 审计日志"""
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 1000,
    })
    assert '预检预警' in r.json()['message']  # 创建即预警（无考勤）
    bill_id = r.json()['data']['id']
    s.post(f'{live_url}/api/bills/{bill_id}/submit')

    s_audit = login(live_url, 'audit001', 'Audit@001!')
    r = s_audit.post(f'{live_url}/api/bills/{bill_id}/auditor-audit',
                     json={'decision': 'approve', 'comment': '同意'})
    body = r.json()
    assert body['code'] == 0
    assert '预检预警' in body['message']

    with app.app_context():
        logs = AuditLog.query.filter_by(
            action='PRECHECK_WARNING', target_id=str(bill_id),
        ).all()
        assert len(logs) == 1
        assert '考勤联动' in logs[0].detail


def test_precheck_api(live_url, app, reimburser, project):
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-09-01',
        'travel_end_date': '2026-09-02',
        'destination': '北京',
        'transport_fee': 100,
    })
    bill_id = r.json()['data']['id']

    r = s.get(f'{live_url}/api/bills/{bill_id}/precheck')
    assert r.status_code == 200
    data = r.json()['data']
    assert {p['rule'] for p in data} == {'attendance', 'transfer'}
    att = next(p for p in data if p['rule'] == 'attendance')
    assert att['status'] == 'warning'


def test_precheck_api_requires_login(live_url):
    r = requests.get(f'{live_url}/api/bills/1/precheck')
    assert r.status_code == 401


def test_precheck_api_not_found(live_url):
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/bills/99999/precheck')
    assert r.status_code == 404
