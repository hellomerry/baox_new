"""
业务校验测试
"""
import pytest
from datetime import date
from models import db
from models.models import (
    SysUser, ExpenseProject, UserProject, ExpenseBill, PositionLevel, UserPosition
)
from utils.validators import (
    run_three_layer_validation, check_duplicate_bill,
    check_status_transition, determine_required_audit, get_max_standard
)
from utils.bill_number import generate_bill_no, amount_to_capital
from werkzeug.security import generate_password_hash


def test_status_transition_valid():
    ok, _ = check_status_transition('draft', 'submitted_auditor')
    assert ok is True


def test_status_transition_invalid():
    ok, msg = check_status_transition('draft', 'archived')
    assert ok is False


def test_status_transition_skip_audit_for_agent_filled():
    """G2：代填可跳过初审直接到财务"""
    ok, _ = check_status_transition('draft', 'submitted_finance')
    assert ok is True  # 允许代填直接到财务


def test_amount_threshold(app):
    """B2：金额阈值"""
    with app.app_context():
        assert determine_required_audit(1000) == 'auditor_only'
        assert determine_required_audit(10000) == 'finance_required'
        assert determine_required_audit(200000) == 'dual_sign_required'


def test_capital_amount():
    assert '零元整' in amount_to_capital(0)
    assert '壹仟陆佰' in amount_to_capital(1600)
    assert '壹万' in amount_to_capital(10000)
    assert '贰角' in amount_to_capital(0.2)
    assert '伍分' in amount_to_capital(0.05)


def test_bill_number_format(app):
    """单号格式"""
    with app.app_context():
        # 需要有项目
        from models.models import ExpenseProject
        p = ExpenseProject(
            project_code='TEST01', project_name='测试', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', created_by=1,
        )
        db.session.add(p)
        db.session.commit()

        bill_no = generate_bill_no('TEST01')
        assert bill_no.startswith('B')
        assert '-TEST01-' in bill_no
        suffix = bill_no.split('-')[-1]
        assert len(suffix) == 5  # 5 位序号


def test_three_layer_validation_all_pass(app):
    """三层准入：全过"""
    with app.app_context():
        u = SysUser(
            username='r1', real_name='r1', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
            valid_start_date=date(2026, 1, 1), valid_end_date=date(2026, 12, 31),
        )
        p = ExpenseProject(
            project_code='PRJ1', project_name='p', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', created_by=1,
        )
        db.session.add_all([u, p])
        db.session.flush()
        db.session.add(UserProject(user_id=u.id, project_id=p.id, status='active', created_by=1))
        db.session.commit()

        ok, msg = run_three_layer_validation(u.id, p.id)
        assert ok is True, msg


def test_three_layer_validation_no_binding(app):
    """三层准入：人项未绑定"""
    with app.app_context():
        u = SysUser(
            username='r2', real_name='r2', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
        )
        p = ExpenseProject(
            project_code='PRJ2', project_name='p', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', created_by=1,
        )
        db.session.add_all([u, p])
        db.session.commit()
        ok, msg = run_three_layer_validation(u.id, p.id)
        assert ok is False
        assert '关联' in msg or '绑定' in msg


def test_three_layer_validation_user_expired(app):
    """三层准入：人员过期"""
    with app.app_context():
        u = SysUser(
            username='r3', real_name='r3', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
            valid_start_date=date(2020, 1, 1), valid_end_date=date(2020, 12, 31),
        )
        p = ExpenseProject(
            project_code='PRJ3', project_name='p', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', created_by=1,
        )
        db.session.add_all([u, p])
        db.session.flush()
        db.session.add(UserProject(user_id=u.id, project_id=p.id, status='active', created_by=1))
        db.session.commit()
        ok, msg = run_three_layer_validation(u.id, p.id)
        assert ok is False


def test_three_layer_validation_project_inactive(app):
    """三层准入：项目停用"""
    with app.app_context():
        u = SysUser(
            username='r4', real_name='r4', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
        )
        p = ExpenseProject(
            project_code='PRJ4', project_name='p', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='inactive', created_by=1,
        )
        db.session.add_all([u, p])
        db.session.flush()
        db.session.add(UserProject(user_id=u.id, project_id=p.id, status='active', created_by=1))
        db.session.commit()
        ok, msg = run_three_layer_validation(u.id, p.id)
        assert ok is False


def test_duplicate_check_no_overlap(app):
    """K1：无重叠 ok"""
    with app.app_context():
        u = SysUser(
            username='r5', real_name='r5', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
        )
        p = ExpenseProject(
            project_code='PRJ5', project_name='p', project_type='普通',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            status='active', created_by=1,
        )
        db.session.add_all([u, p])
        db.session.commit()
        status, msg, conflicts = check_duplicate_bill(u.id, p.id, date(2026, 8, 20), date(2026, 8, 22))
        assert status == 'ok'


def test_max_standard(app):
    """K2：高标准（取所有项目中最高）"""
    with app.app_context():
        u = SysUser(
            username='r6', real_name='r6', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('Test@001!'),
        )
        db.session.add(u)
        db.session.flush()
        pos = PositionLevel.query.filter_by(level_code='DIVISION').first()
        db.session.add(UserPosition(user_id=u.id, position_id=pos.id, effective_date=date.today()))
        db.session.commit()

        standards = get_max_standard(u.id, [1, 2, 3])
        # 应有伙食 / 住宿标准
        types = {s.subsidy_type for s in standards.values()}
        assert '伙食' in types or '住宿' in types
