"""决策链 service（D3 增强）

合并 3 个审计表为一个时间线：
- audit_log：通用操作日志（创建/提交/删除/导出等）
- research_audit_log：终审独立审计（override / dual_sign_request / dual_sign_approve / dual_sign_reject）
- finance_audit_log：财务双人会签（final_approve / final_reject / dual sign）

按时间倒序返回完整决策链路
"""
import logging
from typing import List, Dict
from models.models import (
    db, ExpenseBill, AuditLog, ResearchAuditLog, FinanceAuditLog, SysUser,
)

log = logging.getLogger(__name__)


def get_bill_decision_chain(bill_id: int) -> Dict:
    """获取单据的完整决策链

    Returns:
        {
            'bill': {...},
            'chain': [
                {
                    'id': int,
                    'source': 'audit_log' | 'research_audit_log' | 'finance_audit_log',
                    'action': str,
                    'operator_id': int,
                    'operator_name': str,
                    'operator_role': str,
                    'reason': str,
                    'original_status': str,
                    'new_status': str,
                    'detail_json': str,  # 仅 audit_log 有
                    'ip_address': str,    # 仅 research_audit_log 有
                    'amount': float,      # 仅 finance_audit_log 有
                    'created_at': str,
                },
                ...
            ],
        }
    """
    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return None

    # 1. 收集所有审计记录
    events = []

    # audit_log
    for a in AuditLog.query.filter_by(target_type='bill', target_id=str(bill_id)).all():
        events.append({
            'id': a.id,
            'source': 'audit_log',
            'action': a.action,
            'operator_id': a.actor_id,
            'operator_name': _user_name(a.actor_id),
            'operator_role': a.actor_role,
            'reason': None,
            'original_status': None,
            'new_status': None,
            'detail_json': a.detail,
            'ip_address': None,
            'amount': None,
            'created_at': a.created_at,
        })

    # research_audit_log
    for r in ResearchAuditLog.query.filter_by(bill_id=bill_id).all():
        events.append({
            'id': r.id,
            'source': 'research_audit_log',
            'action': r.action,
            'operator_id': r.auditor_id,
            'operator_name': _user_name(r.auditor_id),
            'operator_role': r.auditor_role,
            'reason': r.reason,
            'original_status': r.original_status,
            'new_status': r.new_status,
            'detail_json': None,
            'ip_address': r.ip_address,
            'amount': None,
            'created_at': r.created_at,
        })

    # finance_audit_log
    for f in FinanceAuditLog.query.filter_by(bill_id=bill_id).all():
        events.append({
            'id': f.id,
            'source': 'finance_audit_log',
            'action': f.action,
            'operator_id': f.finance_user_id,
            'operator_name': _user_name(f.finance_user_id),
            'operator_role': 'finance',
            'reason': f.comment,
            'original_status': f.original_status,
            'new_status': f.new_status,
            'detail_json': None,
            'ip_address': None,
            'amount': float(f.amount) if f.amount else None,
            'created_at': f.created_at,
        })

    # 2. 按时间倒序
    events.sort(key=lambda x: x['created_at'] or '', reverse=True)

    # 3. 格式化
    chain = []
    for e in events:
        chain.append({
            **e,
            'created_at': e['created_at'].isoformat() if e['created_at'] else None,
        })

    return {
        'bill': {
            'id': bill.id,
            'bill_no': bill.bill_no,
            'status': bill.status,
            'total_amount': float(bill.total_amount or 0),
            'user_id': bill.user_id,
            'finance_auditor_id': bill.finance_auditor_id,
            'finance_dual_signer_id': bill.finance_dual_signer_id,
            'finance_dual_signed': bill.finance_dual_signed,
            'created_at': bill.created_at.isoformat() if bill.created_at else None,
        },
        'chain': chain,
    }


def _user_name(user_id: int) -> str:
    u = SysUser.query.get(user_id)
    return u.real_name if u else f'#{user_id}'


# ============= 审计筛选 =============

def filter_research_audits(
    action: str = None,
    auditor_id: int = None,
    bill_id: int = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple:
    """筛选终审独立审计 + 返回总数

    Returns: (items, total)
    """
    from datetime import datetime
    q = ResearchAuditLog.query
    if action:
        q = q.filter_by(action=action)
    if auditor_id:
        q = q.filter_by(auditor_id=auditor_id)
    if bill_id:
        q = q.filter_by(bill_id=bill_id)
    if date_from:
        try:
            df = datetime.fromisoformat(date_from)
            q = q.filter(ResearchAuditLog.created_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            q = q.filter(ResearchAuditLog.created_at <= dt)
        except ValueError:
            pass

    total = q.count()
    items = q.order_by(ResearchAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def research_audit_to_dict(r: ResearchAuditLog) -> Dict:
    return {
        'id': r.id,
        'bill_id': r.bill_id,
        'auditor_id': r.auditor_id,
        'auditor_name': _user_name(r.auditor_id),
        'auditor_role': r.auditor_role,
        'action': r.action,
        'reason': r.reason,
        'original_status': r.original_status,
        'new_status': r.new_status,
        'ip_address': r.ip_address,
        'client_id': r.client_id,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }
