"""
终审独立审计服务（D3 决策）
===========================
- 与 finance_audit_log 区分
- 记录终审（final_approve / final_reject）的独立操作
- 区别：终审是终局动作，独立性要求高
- 支持导出审计报告 PDF（不可篡改）
"""
from datetime import datetime
from pathlib import Path

from flask import request
from models import db
from models.models import (
    ResearchAuditLog, ExpenseBill, SysUser, AuditLog,
)


def log_research_audit(
    bill_id: int,
    auditor_id: int,
    action: str,
    reason: str = None,
    original_status: str = None,
    new_status: str = None,
    auditor_role: str = 'finance',
    ip_address: str = None,
    client_id: str = None,
) -> int:
    """记录一次终审独立审计

    Args:
        bill_id: 报销单 ID
        auditor_id: 操作人 ID
        action: final_approve / final_reject / override / archive
        reason: 备注 / 原因
        original_status: 变更前状态
        new_status: 变更后状态
        auditor_role: finance / auditor
        ip_address: 操作 IP（从 request 推断）
        client_id: 客户端 ID

    Returns:
        audit_id
    """
    # 自动获取 IP
    if not ip_address:
        try:
            ip_address = request.remote_addr if request else None
        except RuntimeError:
            pass

    audit = ResearchAuditLog(
        bill_id=bill_id,
        auditor_id=auditor_id,
        auditor_role=auditor_role,
        action=action,
        reason=reason,
        original_status=original_status,
        new_status=new_status,
        ip_address=ip_address,
        client_id=client_id,
    )
    db.session.add(audit)

    # 同时写通用审计日志（双写）
    log_audit = AuditLog(
        actor_id=auditor_id,
        actor_role=auditor_role,
        action=f'research_{action}',
        target_type='bill',
        target_id=str(bill_id),
        detail=f'终审独立审计: {action} - {reason or ""}',
        ip_address=ip_address,
    )
    db.session.add(log_audit)
    db.session.commit()

    return audit.id


def list_research_audits(
    bill_id: int = None,
    auditor_id: int = None,
    action: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
) -> list:
    """查询终审独立审计记录"""
    query = ResearchAuditLog.query

    if bill_id:
        query = query.filter_by(bill_id=bill_id)
    if auditor_id:
        query = query.filter_by(auditor_id=auditor_id)
    if action:
        query = query.filter_by(action=action)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(ResearchAuditLog.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            query = query.filter(ResearchAuditLog.created_at <= ed)
        except ValueError:
            pass

    items = query.order_by(ResearchAuditLog.created_at.desc()).limit(limit).all()

    # 关联用户
    user_ids = {it.auditor_id for it in items}
    users = {u.id: u for u in SysUser.query.filter(SysUser.id.in_(user_ids)).all()} if user_ids else {}

    return [{
        'id': it.id,
        'bill_id': it.bill_id,
        'auditor_id': it.auditor_id,
        'auditor_name': users.get(it.auditor_id).real_name if it.auditor_id in users else '-',
        'auditor_role': it.auditor_role,
        'action': it.action,
        'reason': it.reason,
        'original_status': it.original_status,
        'new_status': it.new_status,
        'ip_address': it.ip_address,
        'client_id': it.client_id,
        'created_at': it.created_at.isoformat() if it.created_at else None,
    } for it in items]


def get_bill_research_history(bill_id: int) -> list:
    """获取单据的完整终审历史（按时间线）"""
    return list_research_audits(bill_id=bill_id, limit=50)


def verify_research_audit_chain(bill_id: int) -> dict:
    """校验单据的终审审计链是否完整

    Returns:
        {
            'ok': True/False,
            'count': int,
            'missing_actions': [...],
            'last_action': str,
        }
    """
    items = ResearchAuditLog.query.filter_by(bill_id=bill_id).order_by(ResearchAuditLog.created_at.asc()).all()
    if not items:
        return {
            'ok': True,
            'count': 0,
            'missing_actions': [],
            'last_action': None,
            'message': '无终审记录（可能金额未达终审阈值）',
        }

    actions = [it.action for it in items]
    # 终审链应当有 final_approve / final_reject / dual_sign_approve / dual_sign_reject 之一
    terminal_actions = {'final_approve', 'final_reject',
                        'dual_sign_approve', 'dual_sign_reject'}
    if not any(a in terminal_actions for a in actions):
        return {
            'ok': False,
            'count': len(items),
            'missing_actions': ['final_approve / final_reject / dual_sign_*'],
            'last_action': actions[-1] if actions else None,
        }

    return {
        'ok': True,
        'count': len(items),
        'missing_actions': [],
        'last_action': actions[-1] if actions else None,
    }
