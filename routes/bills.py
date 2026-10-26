"""
报销单路由（T4 + PDF 导出）
"""
import json
import os
from datetime import datetime, date
from flask import send_file
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, and_

from models import db
from models.models import ExpenseBill, ExpenseBillItem, SysUser, ExpenseProject
from utils.decorators import login_required, get_current_user
from services.bill_service import BillService

bills_bp = Blueprint('bills', __name__)


@bills_bp.route('/list')
@login_required
def list_bills():
    """查询列表"""
    user = get_current_user()
    filters = {}
    if request.args.get('status'):
        filters['status'] = request.args.get('status')
    if request.args.get('project_id'):
        filters['project_id'] = int(request.args.get('project_id'))
    if request.args.get('user_id'):
        filters['user_id'] = int(request.args.get('user_id'))
    if request.args.get('bill_type'):
        filters['bill_type'] = request.args.get('bill_type')

    bills = BillService.list_bills(user.id, filters)

    # 一次查全部关联
    user_ids = set()
    project_ids = set()
    for b in bills:
        if b.user_id:
            user_ids.add(b.user_id)
        project_ids.add(b.project_id)

    users_map = {u.id: u for u in SysUser.query.filter(SysUser.id.in_(user_ids)).all()} if user_ids else {}
    projects_map = {p.id: p for p in ExpenseProject.query.filter(ExpenseProject.id.in_(project_ids)).all()} if project_ids else {}

    return jsonify({
        'code': 0,
        'data': [{
            'id': b.id,
            'bill_no': b.bill_no,
            'bill_type': b.bill_type,
            'user_id': b.user_id,
            'user_name': users_map.get(b.user_id).real_name if b.user_id and b.user_id in users_map else None,
            'project_id': b.project_id,
            'project_name': projects_map.get(b.project_id).project_name if b.project_id in projects_map else None,
            'travel_start_date': b.travel_start_date.isoformat() if b.travel_start_date else None,
            'travel_end_date': b.travel_end_date.isoformat() if b.travel_end_date else None,
            'destination': b.destination,
            'transport_fee': float(b.transport_fee) if b.transport_fee else 0,
            'accommodation_fee': float(b.accommodation_fee) if b.accommodation_fee else 0,
            'subsidy_fee': float(b.subsidy_fee) if b.subsidy_fee else 0,
            'other_fee': float(b.other_fee) if b.other_fee else 0,
            'total_amount': float(b.total_amount) if b.total_amount else 0,
            'capital_amount': b.capital_amount,
            'status': b.status,
            'is_agent_filled': b.is_agent_filled,
            'created_at': b.created_at.isoformat() if b.created_at else None,
        } for b in bills]
    })


@bills_bp.route('/<int:bill_id>')
@login_required
def get_bill(bill_id):
    """单据详情"""
    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return jsonify({'code': 1, 'message': '报销单不存在'}), 404

    items = ExpenseBillItem.query.filter_by(bill_id=bill_id).all()

    # 关联查
    user = SysUser.query.get(bill.user_id) if bill.user_id else None
    project = ExpenseProject.query.get(bill.project_id)
    auditor = SysUser.query.get(bill.auditor_id) if bill.auditor_id else None

    return jsonify({
        'code': 0,
        'data': {
            'id': bill.id,
            'bill_no': bill.bill_no,
            'bill_type': bill.bill_type,
            'user_id': bill.user_id,
            'user_name': user.real_name if user else None,
            'project_id': bill.project_id,
            'project_name': project.project_name if project else None,
            'travel_start_date': bill.travel_start_date.isoformat() if bill.travel_start_date else None,
            'travel_end_date': bill.travel_end_date.isoformat() if bill.travel_end_date else None,
            'destination': bill.destination,
            'transport_fee': float(bill.transport_fee) if bill.transport_fee else 0,
            'accommodation_fee': float(bill.accommodation_fee) if bill.accommodation_fee else 0,
            'subsidy_fee': float(bill.subsidy_fee) if bill.subsidy_fee else 0,
            'other_fee': float(bill.other_fee) if bill.other_fee else 0,
            'total_amount': float(bill.total_amount) if bill.total_amount else 0,
            'capital_amount': bill.capital_amount,
            'status': bill.status,
            'is_agent_filled': bill.is_agent_filled,
            'applied_standard_source': bill.applied_standard_source,
            'auditor_id': bill.auditor_id,
            'auditor_name': auditor.real_name if auditor else None,
            'auditor_comment': bill.auditor_comment,
            'auditor_audit_at': bill.auditor_audit_at.isoformat() if bill.auditor_audit_at else None,
            'finance_auditor_id': bill.finance_auditor_id,
            'finance_comment': bill.finance_comment,
            'finance_audit_at': bill.finance_audit_at.isoformat() if bill.finance_audit_at else None,
            'finance_dual_signed': bill.finance_dual_signed,
            'finance_dual_signer_id': bill.finance_dual_signer_id,
            'finance_dual_sign_at': bill.finance_dual_sign_at.isoformat() if bill.finance_dual_sign_at else None,
            'finance_dual_comment': bill.finance_dual_comment,
            'items': [{
                'id': it.id,
                'item_type': it.item_type,
                'amount': float(it.amount) if it.amount else 0,
                'expense_date': it.expense_date.isoformat() if it.expense_date else None,
                'description': it.description,
                'attachment_path': it.attachment_path,
            } for it in items],
            'created_at': bill.created_at.isoformat() if bill.created_at else None,
        }
    })


@bills_bp.route('/create', methods=['POST'])
@login_required
def create_bill():
    """创建报销单"""
    data = request.get_json() or {}
    user = get_current_user()
    ok, msg, bill = BillService.create_bill(user.id, data)
    if not ok:
        return jsonify({'code': 1, 'message': msg}), 400
    return jsonify({
        'code': 0,
        'data': {
            'id': bill.id,
            'bill_no': bill.bill_no,
            'status': bill.status,
        },
        'message': msg,
    })


@bills_bp.route('/<int:bill_id>/submit', methods=['POST'])
@login_required
def submit_bill(bill_id):
    """提交报销单"""
    user = get_current_user()
    ok, msg = BillService.submit_bill(user.id, bill_id)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@bills_bp.route('/<int:bill_id>/auditor-audit', methods=['POST'])
@login_required
def auditor_audit(bill_id):
    """稽核员初审"""
    user = get_current_user()
    if user.role != 'auditor':
        return jsonify({'code': 1, 'message': '仅稽核员可操作'}), 403

    data = request.get_json() or {}
    decision = data.get('decision')
    comment = data.get('comment', '')

    ok, msg = BillService.audit_by_auditor(user.id, bill_id, decision, comment)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@bills_bp.route('/<int:bill_id>/finance-audit', methods=['POST'])
@login_required
def finance_audit(bill_id):
    """财务终审"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可操作'}), 403

    data = request.get_json() or {}
    decision = data.get('decision')
    comment = data.get('comment', '')
    dual_signer_id = data.get('dual_signer_id')

    ok, msg = BillService.audit_by_finance(user.id, bill_id, decision, comment, dual_signer_id)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@bills_bp.route('/<int:bill_id>/override', methods=['POST'])
@login_required
def override_bill(bill_id):
    """D3 决策：财务强制修改单据（override）

    适用场景：
    - 稽核员已驳回的单据，业务部门申诉后财务复核认为应通过
    - 终审已驳回的单据，重新评估后改为通过
    - 单据状态异常需要强制干预

    强制要求：
    - 必填原因（至少 10 个字符，用于审计追溯）
    - 自动写入 ResearchAuditLog（独立审计通道）
    - 仅财务可操作
    """
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可强制修改'}), 403

    data = request.get_json() or {}
    target_status = data.get('target_status')
    reason = (data.get('reason') or '').strip()

    if not target_status:
        return jsonify({'code': 1, 'message': '必须指定目标状态'}), 400
    if len(reason) < 10:
        return jsonify({'code': 1, 'message': '原因至少 10 个字符（用于审计追溯）'}), 400

    ok, msg = BillService.override_bill(user.id, bill_id, target_status, reason)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@bills_bp.route('/<int:bill_id>/dual-sign', methods=['POST'])
@login_required
def dual_sign_bill(bill_id):
    """D3 双签：第二签人终审同意 / 拒绝

    body:
        decision: 'approve' | 'reject'
        comment: 备注（reject 必填 ≥10 字符）

    必须：
    - 当前用户是单据指定的第二签人
    - 当前状态为 pending_dual_sign
    """
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可双签'}), 403

    data = request.get_json() or {}
    decision = data.get('decision')
    comment = (data.get('comment') or '').strip()

    if decision == 'approve':
        ok, msg = BillService.approve_dual_sign(user.id, bill_id, comment)
        return jsonify({'code': 0 if ok else 1, 'message': msg})
    elif decision == 'reject':
        if len(comment) < 10:
            return jsonify({'code': 1, 'message': '拒绝原因至少 10 个字符（用于审计追溯）'}), 400
        ok, msg = BillService.reject_dual_sign(user.id, bill_id, comment)
        return jsonify({'code': 0 if ok else 1, 'message': msg})
    else:
        return jsonify({'code': 1, 'message': 'decision 必须是 approve 或 reject'}), 400


@bills_bp.route('/pending-dual-sign', methods=['GET'])
@login_required
def list_pending_dual_sign():
    """D3 双签：列出"待我双签"的单据（财务工作台）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    bills = ExpenseBill.query.filter_by(
        status='pending_dual_sign',
        finance_dual_signer_id=user.id,
    ).order_by(ExpenseBill.finance_audit_at.asc()).all()

    return jsonify({
        'code': 0,
        'data': [{
            'id': b.id,
            'bill_no': b.bill_no,
            'total_amount': float(b.total_amount or 0),
            'capital_amount': b.capital_amount,
            'status': b.status,
            'finance_auditor_id': b.finance_auditor_id,
            'finance_audit_at': b.finance_audit_at.isoformat() if b.finance_audit_at else None,
            'finance_comment': b.finance_comment,
            'finance_dual_signer_id': b.finance_dual_signer_id,
            'finance_dual_signed': b.finance_dual_signed,
            'project_id': b.project_id,
            'user_id': b.user_id,
        } for b in bills]
    })


@bills_bp.route('/<int:bill_id>/delete', methods=['POST'])
@login_required
def delete_bill(bill_id):
    """删除（仅 draft）"""
    user = get_current_user()
    ok, msg = BillService.delete_bill(user.id, bill_id)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@bills_bp.route('/<int:bill_id>/red-rush', methods=['POST'])
@login_required
def red_rush_bill(bill_id):
    """冲红（仅财务）"""
    from services.redrush_service import RedRushService
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可冲红'}), 403

    data = request.get_json() or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'code': 1, 'message': '冲红原因必填'}), 400

    ok, msg, new_bill = RedRushService.red_rush_bill(user.id, bill_id, reason)
    if not ok:
        return jsonify({'code': 1, 'message': msg}), 400

    return jsonify({
        'code': 0,
        'message': msg,
        'data': {
            'new_bill_id': new_bill.id,
            'new_bill_no': new_bill.bill_no,
        }
    })


@bills_bp.route('/check-duplicate', methods=['POST'])
@login_required
def check_duplicate():
    """K1 三态防重复预检"""
    from utils.validators import check_duplicate_bill
    data = request.get_json() or {}
    user = get_current_user()

    user_id = data.get('user_id') or user.id
    project_id = data['project_id']
    start = datetime.strptime(data['travel_start_date'], '%Y-%m-%d').date()
    end = datetime.strptime(data['travel_end_date'], '%Y-%m-%d').date()

    status, msg, conflicts = check_duplicate_bill(user_id, project_id, start, end)
    return jsonify({
        'code': 0,
        'data': {
            'status': status,
            'message': msg,
            'conflicts': conflicts,
        }
    })


@bills_bp.route('/standard-preview', methods=['POST'])
@login_required
def standard_preview():
    """预览高标准计算结果"""
    from utils.validators import get_max_standard
    from services.bill_service import calc_subsidy_by_high_standard
    from decimal import Decimal

    data = request.get_json() or {}
    user = get_current_user()

    user_id = data.get('user_id') or user.id
    project_id = data['project_id']
    start = datetime.strptime(data['travel_start_date'], '%Y-%m-%d').date()
    end = datetime.strptime(data['travel_end_date'], '%Y-%m-%d').date()

    subsidy = calc_subsidy_by_high_standard(user_id, project_id, start, end)
    standards = get_max_standard(user_id, [project_id])

    return jsonify({
        'code': 0,
        'data': {
            'subsidy_fee': float(subsidy),
            'days': (end - start).days + 1,
            'standards': [{
                'subsidy_type': s.subsidy_type,
                'amount': float(s.amount),
                'source_project_id': s.project_id,
            } for s in standards.values()],
        }
    })


@bills_bp.route('/<int:bill_id>/pdf')
@login_required
def export_bill_pdf(bill_id):
    """导出报销单 PDF"""
    from utils.pdf_export import generate_bill_pdf
    from config import Config

    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return jsonify({'code': 1, 'message': '报销单不存在'}), 404

    items = ExpenseBillItem.query.filter_by(bill_id=bill_id).all()
    user = SysUser.query.get(bill.user_id) if bill.user_id else None
    project = ExpenseProject.query.get(bill.project_id)
    auditor = SysUser.query.get(bill.auditor_id) if bill.auditor_id else None
    finance_auditor = SysUser.query.get(bill.finance_auditor_id) if bill.finance_auditor_id else None

    # 存到临时目录
    pdf_dir = str(Config.BASE_DIR / 'rbag_temp' / 'pdf')
    os.makedirs(pdf_dir, exist_ok=True)
    safe_no = bill.bill_no.replace('/', '_')
    out_path = os.path.join(pdf_dir, f'{safe_no}.pdf')

    try:
        generate_bill_pdf(bill, items, project, user, auditor, finance_auditor, out_path)
    except Exception as e:
        return jsonify({'code': 500, 'message': f'PDF 生成失败: {e}'}), 500

    return send_file(
        out_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{safe_no}.pdf',
    )


@bills_bp.route('/<int:bill_id>/docx')
@login_required
def export_bill_docx(bill_id):
    """导出报销单 Word（制式）"""
    from utils.word_export import generate_bill_docx
    from config import Config

    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return jsonify({'code': 1, 'message': '报销单不存在'}), 404

    items = ExpenseBillItem.query.filter_by(bill_id=bill_id).all()
    user = SysUser.query.get(bill.user_id) if bill.user_id else None
    project = ExpenseProject.query.get(bill.project_id)
    auditor = SysUser.query.get(bill.auditor_id) if bill.auditor_id else None
    finance_auditor = SysUser.query.get(bill.finance_auditor_id) if bill.finance_auditor_id else None
    dual_signer = SysUser.query.get(bill.finance_dual_signer_id) if bill.finance_dual_signer_id else None

    # 存到临时目录
    docx_dir = str(Config.BASE_DIR / 'rbag_temp' / 'docx')
    os.makedirs(docx_dir, exist_ok=True)
    safe_no = bill.bill_no.replace('/', '_')
    out_path = os.path.join(docx_dir, f'{safe_no}.docx')

    try:
        generate_bill_docx(bill, items, project, user, auditor, finance_auditor,
                           out_path, dual_signer=dual_signer)
    except Exception as e:
        return jsonify({'code': 500, 'message': f'Word 生成失败: {e}'}), 500

    return send_file(
        out_path,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=f'{safe_no}.docx',
    )


@bills_bp.route('/<int:bill_id>/precheck')
@login_required
def bill_precheck(bill_id):
    """稽核预检（考勤联动 + 调令校验）查询，供审核界面展示预警"""
    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return jsonify({'code': 1, 'message': '报销单不存在'}), 404

    from services.precheck_service import run_prechecks
    return jsonify({'code': 0, 'data': run_prechecks(bill)})


@bills_bp.route('/ping')
def ping():
    return jsonify({'msg': 'bills blueprint ready'})
