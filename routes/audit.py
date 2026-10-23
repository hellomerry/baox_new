"""
审计日志路由（T5 补完 + D3 决策）
- 查询审计日志（合规要求）
- 查询错误日志
- 查询财务终审日志
- 查询终审独立审计（D3）
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from models import db
from models.models import AuditLog, FinanceAuditLog, ErrorLog
from utils.decorators import login_required, get_current_user
from services.research_audit_service import (
    list_research_audits,
    get_bill_research_history,
    verify_research_audit_chain,
)

audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/list')
@login_required
def list_logs():
    """审计日志列表"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    action_filter = request.args.get('action', '')

    q = AuditLog.query
    if action_filter:
        q = q.filter(AuditLog.action.like(f'%{action_filter}%'))

    pagination = q.order_by(AuditLog.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # 取所有 actor
    actor_ids = set(l.actor_id for l in pagination.items if l.actor_id)
    from models.models import SysUser
    users_map = {u.id: u for u in SysUser.query.filter(SysUser.id.in_(actor_ids)).all()} if actor_ids else {}

    return jsonify({
        'code': 0,
        'data': {
            'items': [{
                'id': l.id,
                'actor_id': l.actor_id,
                'actor_name': users_map[l.actor_id].real_name if l.actor_id in users_map else f'#{l.actor_id}',
                'actor_role': l.actor_role,
                'action': l.action,
                'target_type': l.target_type,
                'target_id': l.target_id,
                'detail': l.detail,
                'ip_address': l.ip_address,
                'created_at': l.created_at.isoformat() if l.created_at else None,
            } for l in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@audit_bp.route('/finance-logs')
@login_required
def finance_logs():
    """财务终审独立日志"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    pagination = FinanceAuditLog.query.order_by(
        FinanceAuditLog.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'code': 0,
        'data': {
            'items': [{
                'id': l.id,
                'finance_user_id': l.finance_user_id,
                'action': l.action,
                'bill_id': l.bill_id,
                'amount': float(l.amount) if l.amount else 0,
                'original_status': l.original_status,
                'new_status': l.new_status,
                'comment': l.comment,
                'dual_signer_id': l.dual_signer_id,
                'created_at': l.created_at.isoformat() if l.created_at else None,
            } for l in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@audit_bp.route('/errors')
@login_required
def error_logs():
    """错误日志（仅财务可见）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    pagination = ErrorLog.query.order_by(
        ErrorLog.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'code': 0,
        'data': {
            'items': [{
                'id': l.id,
                'type': l.type,
                'message': l.message,
                'stack_trace': (l.stack_trace or '')[:500],
                'user_id': l.user_id,
                'client_id': l.client_id,
                'context': l.context,
                'created_at': l.created_at.isoformat() if l.created_at else None,
            } for l in pagination.items],
            'total': pagination.total,
        }
    })


@audit_bp.route('/ping')
def ping():
    return jsonify({'msg': 'audit blueprint ready'})


# ============= D3 决策：终审独立审计路由 =============

@audit_bp.route('/research/list')
@login_required
def research_audit_list():
    """终审独立审计日志列表（D3）

    Query params:
        - bill_id: 单据 ID
        - auditor_id: 操作人 ID
        - action: 动作（final_approve / final_reject / override）
        - start_date / end_date: 时间范围 ISO 格式
        - limit: 默认 100
    """
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    bill_id = request.args.get('bill_id', type=int)
    auditor_id = request.args.get('auditor_id', type=int)
    action = request.args.get('action')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = request.args.get('limit', default=100, type=int)

    items = list_research_audits(
        bill_id=bill_id,
        auditor_id=auditor_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return jsonify({'code': 0, 'data': items})


@audit_bp.route('/research/bill/<int:bill_id>')
@login_required
def research_audit_bill_history(bill_id):
    """单据的终审独立审计时间线"""
    user = get_current_user()
    if user.role not in ('finance', 'auditor'):
        return jsonify({'code': 1, 'message': '无权查看'}), 403

    history = get_bill_research_history(bill_id)
    chain = verify_research_audit_chain(bill_id)
    return jsonify({
        'code': 0,
        'data': {
            'history': history,
            'chain': chain,
        }
    })


@audit_bp.route('/research/verify/<int:bill_id>')
@login_required
def research_audit_verify(bill_id):
    """校验单据的终审审计链"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    result = verify_research_audit_chain(bill_id)
    return jsonify({'code': 0, 'data': result})


@audit_bp.route('/research/export/<int:bill_id>')
@login_required
def research_audit_export(bill_id):
    """导出终审审计报告（PDF / Word）

    query:
        format=docx 时输出 Word 制式报告，默认 PDF

    输出：
        - 单据基础信息
        - 终审时间线
        - 操作人 + IP + 客户端 ID
        - 报告哈希（用于校验）
    """
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可导出'}), 403

    from models.models import ExpenseBill, SysUser
    from flask import send_file

    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return jsonify({'code': 1, 'message': '单据不存在'}), 404

    history = get_bill_research_history(bill_id)
    chain = verify_research_audit_chain(bill_id)
    creator = SysUser.query.get(bill.user_id) if bill.user_id else None

    fmt = (request.args.get('format') or 'pdf').lower()
    import tempfile
    try:
        if fmt == 'docx':
            from utils.word_export import export_research_audit_report_docx
            tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
            tmp.close()
            export_research_audit_report_docx(
                output_path=tmp.name,
                bill=bill,
                history=history,
                chain=chain,
                creator=creator,
            )
            return send_file(
                tmp.name,
                mimetype='application/vnd.openxmlformats-officedocument.'
                         'wordprocessingml.document',
                as_attachment=True,
                download_name=f'research_audit_bill_{bill.bill_no}.docx',
            )

        from utils.pdf_export import export_research_audit_report
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.close()
        export_research_audit_report(
            output_path=tmp.name,
            bill=bill,
            history=history,
            chain=chain,
            creator=creator,
        )
        return send_file(
            tmp.name,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'research_audit_bill_{bill.bill_no}.pdf',
        )
    except Exception as e:
        from utils.error_handler import log_client_error
        log_client_error(user.username if user else 'unknown', 'EXPORT_FAIL', str(e))
        return jsonify({'code': 1, 'message': f'导出失败: {e}'}), 500


# ============= D3 增强：决策链 + 筛选 =============

@audit_bp.route('/decision-chain/<int:bill_id>')
@login_required
def decision_chain(bill_id):
    """单据完整决策链（D3 增强）

    合并 audit_log + research_audit_log + finance_audit_log
    按时间倒序返回完整链路
    """
    from services.decision_chain_service import get_bill_decision_chain
    user = get_current_user()
    result = get_bill_decision_chain(bill_id)
    if not result:
        return jsonify({'code': 1, 'message': '单据不存在'}), 404

    # 权限：报销人只能看自己单据
    bill = result['bill']
    if user.role == 'reimburser' and bill['user_id'] != user.id:
        return jsonify({'code': 1, 'message': '无权查看他人单据'}), 403

    return jsonify({'code': 0, 'data': result})


@audit_bp.route('/research/filter', methods=['GET'])
@login_required
def research_audit_filter():
    """终审独立审计筛选（D3 增强）

    Query params:
        - action / auditor_id / bill_id / date_from / date_to
        - limit / offset
    """
    from services.decision_chain_service import filter_research_audits, research_audit_to_dict
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务可查看'}), 403

    items, total = filter_research_audits(
        action=request.args.get('action'),
        auditor_id=request.args.get('auditor_id', type=int),
        bill_id=request.args.get('bill_id', type=int),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        limit=request.args.get('limit', default=100, type=int),
        offset=request.args.get('offset', default=0, type=int),
    )
    return jsonify({
        'code': 0,
        'data': [research_audit_to_dict(i) for i in items],
        'total': total,
    })
