"""公告/通知服务（v2.2.0）

核心 API：
- send_notification：发通知给指定用户
- send_to_role：发通知给指定角色的所有用户
- render_template：从模板渲染标题/内容
- mark_read：标记已读
- get_unread_count：获取未读数
- list_for_user：列出用户的通知

自动触发点（在 bill_service / research_audit_service 调用）：
- 财务驳回 → 通知报销人
- 财务通过 → 通知报销人
- 稽核员驳回 → 通知报销人
- 双签被拒 → 通知主财务
- override → 通知报销人
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import text
from models.models import db, Notification, NotificationTemplate, SysUser, ExpenseBill

log = logging.getLogger(__name__)


# ============= 模板渲染 =============

def render_template(template_str: str, variables: Dict[str, Any]) -> str:
    """简单模板渲染：{var_name} → 实际值

    缺失变量保留原样（不抛错），便于日志追踪
    """
    if not template_str:
        return ''
    try:
        return template_str.format(**variables)
    except KeyError as e:
        log.warning(f"模板渲染缺失变量：{e}, template={template_str}")
        return template_str


def get_template(notification_type: str) -> Optional[NotificationTemplate]:
    """获取通知模板"""
    return NotificationTemplate.query.filter_by(
        type=notification_type, enabled=True
    ).first()


# ============= 核心 API =============

def send_notification(
    user_id: int,
    notification_type: str,
    title: str = None,
    content: str = None,
    sender_id: int = None,
    bill_id: int = None,
    priority: str = None,
    variables: Dict[str, Any] = None,
) -> Optional[Notification]:
    """发通知给指定用户

    Args:
        user_id: 接收人 ID
        notification_type: 通知类型（bill_approved / bill_rejected / system / ...）
        title: 标题（如果提供则不渲染模板）
        content: 内容（如果提供则不渲染模板）
        sender_id: 发送人 ID（None=系统）
        bill_id: 关联单据 ID
        priority: 优先级
        variables: 模板变量（如 {'bill_no': 'B2026-001', 'amount': '5000.00'}）

    v2.10.0 模式 C：
    如果 user_id 是报销员且有 active AgentAuth（被稽核员代理），
    自动复制一份给所有 active 稽核员（标题前缀"代 [报销员名]"）。
    报销员本人仍然收到（他可能偶尔登录），但稽核员是必收。

    Returns:
        创建的 Notification 对象，失败返回 None
    """
    try:
        # 1. 校验用户存在
        user = SysUser.query.get(user_id)
        if not user:
            log.error(f"send_notification: 用户 {user_id} 不存在")
            return None

        # 2. 获取模板（如果未提供 title/content）
        if not title or not content:
            tpl = get_template(notification_type)
            if tpl:
                if not title:
                    title = render_template(tpl.title_template, variables or {})
                if not content:
                    content = render_template(tpl.content_template, variables or {})
            else:
                # 没有模板就退化
                title = title or notification_type
                content = content or '（无内容）'

        # 3. 默认优先级
        if not priority:
            tpl = get_template(notification_type)
            priority = tpl.default_priority if tpl else 'normal'

        # 4. 插入主通知
        n = Notification(
            user_id=user_id,
            sender_id=sender_id,
            type=notification_type,
            title=title[:200],  # 防止超长
            content=content,
            bill_id=bill_id,
            priority=priority,
        )
        db.session.add(n)
        db.session.flush()  # 让 n.id 可用

        # 5. 模式 C：被代填的报销员，复制通知给稽核员
        if user.role == 'reimburser':
            proxy_rows = db.session.execute(text(
                "SELECT agent_id FROM agent_auth "
                "WHERE be_agent_id = :uid AND status = 'active'"
            ), {'uid': user_id}).fetchall()
            for (agent_id,) in proxy_rows:
                proxy_title = f"[代 {user.real_name}] {title}"[:200]
                proxy_n = Notification(
                    user_id=agent_id,
                    sender_id=sender_id,
                    type=notification_type,
                    title=proxy_title,
                    content=content,
                    bill_id=bill_id,
                    priority=priority,
                )
                db.session.add(proxy_n)
                log.info(f"proxy notification: {notification_type} → auditor#{agent_id} (代理 {user.real_name})")

        db.session.commit()
        log.info(f"notification: {notification_type} → user#{user_id} (bill={bill_id})")
        return n
    except Exception as e:
        log.exception(f"send_notification 失败: {e}")
        db.session.rollback()
        return None


def send_to_role(
    role: str,
    notification_type: str,
    title: str = None,
    content: str = None,
    sender_id: int = None,
    bill_id: int = None,
    variables: Dict[str, Any] = None,
) -> int:
    """群发通知给指定角色的所有用户

    Returns: 成功发送数量
    """
    users = SysUser.query.filter_by(role=role, account_status='normal').all()
    count = 0
    for u in users:
        if send_notification(
            user_id=u.id,
            notification_type=notification_type,
            title=title, content=content,
            sender_id=sender_id,
            bill_id=bill_id,
            variables=variables,
        ):
            count += 1
    return count


def mark_read(notification_id: int, user_id: int) -> bool:
    """标记单条已读（仅本人能标）"""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return False
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now()
        db.session.commit()
    return True


def mark_all_read(user_id: int) -> int:
    """标记所有已读，返回标记条数"""
    count = Notification.query.filter_by(user_id=user_id, is_read=False).update({
        'is_read': True,
        'read_at': datetime.now(),
    })
    db.session.commit()
    return count


def get_unread_count(user_id: int) -> int:
    """获取用户未读通知数"""
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()


def list_for_user(
    user_id: int,
    is_read: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Notification]:
    """列出用户的通知（按时间倒序）"""
    q = Notification.query.filter_by(user_id=user_id)
    if is_read is not None:
        q = q.filter_by(is_read=is_read)
    return q.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()


def delete_notification(notification_id: int, user_id: int) -> bool:
    """删除通知（仅本人能删）"""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return False
    db.session.delete(n)
    db.session.commit()
    return True


# ============= 业务事件自动触发（便捷函数） =============

def notify_bill_approved(bill: ExpenseBill, operator_id: int):
    """财务通过 → 通知报销人"""
    return send_notification(
        user_id=bill.user_id,
        notification_type='bill_approved',
        sender_id=operator_id,
        bill_id=bill.id,
        variables={
            'bill_no': bill.bill_no,
            'amount': f"{float(bill.total_amount or 0):.2f}",
        },
    )


def notify_bill_rejected(bill: ExpenseBill, operator_id: int, reason: str):
    """财务驳回 → 通知报销人"""
    operator = SysUser.query.get(operator_id)
    return send_notification(
        user_id=bill.user_id,
        notification_type='bill_rejected',
        sender_id=operator_id,
        bill_id=bill.id,
        priority='high',
        variables={
            'bill_no': bill.bill_no,
            'operator': operator.real_name if operator else '财务',
            'reason': reason or '（未提供原因）',
        },
    )


def notify_bill_auditor_rejected(bill: ExpenseBill, operator_id: int, reason: str):
    """稽核员驳回 → 通知报销人"""
    return send_notification(
        user_id=bill.user_id,
        notification_type='bill_auditor_rejected',
        sender_id=operator_id,
        bill_id=bill.id,
        priority='high',
        variables={
            'bill_no': bill.bill_no,
            'reason': reason or '（未提供原因）',
        },
    )


def notify_bill_pending_dual(bill: ExpenseBill, operator_id: int):
    """大额报销主财务通过 → 通知第二签人"""
    return send_notification(
        user_id=bill.finance_dual_signer_id,
        notification_type='bill_pending_dual',
        sender_id=operator_id,
        bill_id=bill.id,
        priority='high',
        variables={
            'bill_no': bill.bill_no,
            'amount': f"{float(bill.total_amount or 0):.2f}",
        },
    )


def notify_bill_dual_rejected(bill: ExpenseBill, operator_id: int, reason: str):
    """双签被拒 → 通知主财务"""
    if not bill.finance_auditor_id:
        return None
    return send_notification(
        user_id=bill.finance_auditor_id,
        notification_type='bill_dual_rejected',
        sender_id=operator_id,
        bill_id=bill.id,
        priority='urgent',
        variables={
            'bill_no': bill.bill_no,
            'reason': reason or '（未提供原因）',
        },
    )


def notify_bill_overridden(bill: ExpenseBill, operator_id: int, new_status: str, reason: str):
    """强制修改状态 → 通知报销人 + 主财务"""
    log.warning(f'notify_bill_overridden: bill#{bill.id} user#{bill.user_id} finance_aud#{bill.finance_auditor_id}')
    n1 = send_notification(
        user_id=bill.user_id,
        notification_type='bill_overridden',
        sender_id=operator_id,
        bill_id=bill.id,
        priority='urgent',
        variables={
            'bill_no': bill.bill_no,
            'new_status': new_status,
            'reason': reason or '（未提供原因）',
        },
    )
    if bill.finance_auditor_id and bill.finance_auditor_id != bill.user_id:
        send_notification(
            user_id=bill.finance_auditor_id,
            notification_type='bill_overridden',
            sender_id=operator_id,
            bill_id=bill.id,
            priority='high',
            variables={
                'bill_no': bill.bill_no,
                'new_status': new_status,
                'reason': reason or '（未提供原因）',
            },
        )
    return n1
