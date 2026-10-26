"""
报销单核心服务（T4）
实现：创建/提交/初审/终审/修改/删除/冲红 + 项目总账
G/H/I/J/K/L/M 决策落地
"""
import json
from datetime import datetime, date
from decimal import Decimal

from models import db
from models.models import (
    ExpenseBill, ExpenseBillItem, SysUser, AuditLog, FinanceAuditLog,
    ExpenseProject, AgentAuth, UserProject, SysConfig, UserPosition,
    ExpenseStandard, Notification
)
from utils.validators import (
    run_three_layer_validation, check_status_transition,
    determine_required_audit, check_duplicate_bill, get_max_standard
)
from utils.bill_number import generate_bill_no, amount_to_capital
from services import notification_service


# ============= 工具函数 =============

def get_config_int(key: str, default: int) -> int:
    cfg = SysConfig.query.filter_by(config_key=key).first()
    if cfg and cfg.config_value.isdigit():
        return int(cfg.config_value)
    return default


def calc_subsidy_by_high_standard(user_id: int, project_id: int, start_date: date, end_date: date,
                                  destination: str = None) -> Decimal:
    """
    J 决策：按高标准计算补助
    v2.11.2：destination 参与地区档交叉（地区特定标准按费用类型优先）
    """
    overlapping_projects = db.session.query(ExpenseBill.project_id).filter(
        ExpenseBill.user_id == user_id,
        ExpenseBill.status.in_(['draft', 'submitted_auditor', 'auditor_ok', 'submitted_finance', 'rejected_auditor', 'rejected_finance', 'approved']),
        ExpenseBill.travel_start_date <= end_date,
        ExpenseBill.travel_end_date >= start_date,
    ).distinct().all()

    project_ids = [project_id] + [p[0] for p in overlapping_projects if p[0] != project_id]

    max_standards = get_max_standard(user_id, project_ids, destination)

    if not max_standards:
        return Decimal('0')

    days = (end_date - start_date).days + 1
    total = Decimal('0')
    for s in max_standards.values():
        if s.subsidy_type in ['伙食', '住宿', '交通']:
            total += Decimal(str(s.amount)) * days

    return total


def notify_bill_status_change(bill, event_type: str, operator):
    """M3 决策：状态变更时通知相关人（v2.2.0 改用 notification_service）"""
    type_map = {
        'submit': 'bill_submitted',
        'auditor_ok': 'bill_auditor_ok',
        'auditor_reject': 'bill_auditor_rejected',
        'finance_approve': 'bill_approved',
        'finance_reject': 'bill_rejected',
    }

    ntype = type_map.get(event_type)
    if not ntype:
        return

    operator_id = operator.id if operator else None
    variables = {
        'bill_no': bill.bill_no,
        'amount': f"{float(bill.total_amount or 0):.2f}",
        'operator': operator.real_name if operator else '系统',
    }

    # 根据事件类型决定接收人
    if event_type == 'submit':
        if bill.auditor_id:
            notification_service.send_notification(
                user_id=bill.auditor_id, notification_type=ntype,
                sender_id=operator_id, bill_id=bill.id,
                variables=variables,
            )
    elif event_type in ('auditor_ok', 'finance_approve'):
        if bill.user_id:
            notification_service.send_notification(
                user_id=bill.user_id, notification_type=ntype,
                sender_id=operator_id, bill_id=bill.id,
                variables=variables,
            )
        if event_type == 'finance_approve':
            project = ExpenseProject.query.get(bill.project_id)
            if project and project.finance_auditor_id and project.finance_auditor_id != bill.user_id:
                notification_service.send_notification(
                    user_id=project.finance_auditor_id, notification_type=ntype,
                    sender_id=operator_id, bill_id=bill.id,
                    variables=variables,
                )
    elif event_type == 'auditor_reject':
        if bill.user_id:
            notification_service.send_notification(
                user_id=bill.user_id, notification_type=ntype,
                sender_id=operator_id, bill_id=bill.id,
                variables={**variables, 'reason': getattr(bill, 'auditor_comment', '') or '（未提供原因）'},
            )
    elif event_type == 'finance_reject':
        if bill.auditor_id:
            notification_service.send_notification(
                user_id=bill.auditor_id, notification_type=ntype,
                sender_id=operator_id, bill_id=bill.id,
                variables={**variables, 'reason': getattr(bill, 'finance_comment', '') or '（未提供原因）'},
            )
        if bill.user_id:
            notification_service.send_notification(
                user_id=bill.user_id, notification_type=ntype,
                sender_id=operator_id, bill_id=bill.id,
                variables={**variables, 'reason': getattr(bill, 'finance_comment', '') or '（未提供原因）'},
            )


# ============= 报销单 CRUD =============

class BillService:

    @staticmethod
    def create_bill(operator_id: int, bill_data: dict) -> tuple:
        """
        创建报销单

        X3 决策：bill_type='project_total' 时 user_id 必须为 NULL
        X5 决策：user_id 允许 NULL（项目总账时）
        G2 决策：is_agent_filled = (creator_id != user_id)，且 user_id 不为 NULL
        L7 决策：项目总账必填明细，合计=主单
        """
        operator = SysUser.query.get(operator_id)
        if not operator:
            return False, '操作员不存在', None

        user_id = bill_data.get('user_id')  # 项目总账时可为 None
        project_id = bill_data['project_id']
        bill_type = bill_data.get('bill_type', 'personal')

        # 1. 校验项目总账的 user_id 必须为 NULL
        if bill_type == 'project_total' and user_id is not None:
            return False, '项目总账报销单 user_id 必须为 NULL', None
        if bill_type != 'project_total' and user_id is None:
            return False, '个人报销单 user_id 不能为 NULL', None

        # 2. 三层准入（仅个人报销需要）
        if user_id is not None:
            ok, msg = run_three_layer_validation(user_id, project_id)
            if not ok:
                return False, msg, None

        # 3. 项目有效性
        project = ExpenseProject.query.get(project_id)
        if not project:
            return False, '项目不存在', None
        ok, msg = check_project_validity_check(project)
        if not ok:
            return False, f'【项目】{msg}', None

        # 4. 是否代填
        is_agent_filled = False
        if user_id is not None and user_id != operator_id:
            is_agent_filled = True
            # 稽核员代填：检查授权
            agent_auth = AgentAuth.query.filter_by(
                agent_id=operator_id,
                be_agent_id=user_id,
                project_id=project_id,
                status='active'
            ).first()
            if not agent_auth:
                return False, '您没有该报销人的代理权限', None

        # 5. 防重复校验
        from datetime import datetime as dt
        start = dt.strptime(bill_data['travel_start_date'], '%Y-%m-%d').date()
        end = dt.strptime(bill_data['travel_end_date'], '%Y-%m-%d').date()
        if user_id is not None:
            status, msg, _ = check_duplicate_bill(user_id, project_id, start, end)
            if status == 'block':
                return False, msg, None

        # 6. 计算总金额（K 决策：subsidy_fee 自动按高标准；v2.11.2：含地区档交叉）
        subsidy_fee = Decimal(str(bill_data.get('subsidy_fee', 0)))
        destination = bill_data.get('destination', '')
        if user_id is not None and subsidy_fee == 0:
            subsidy_fee = calc_subsidy_by_high_standard(user_id, project_id, start, end, destination)

        total = (
            Decimal(str(bill_data.get('transport_fee', 0))) +
            Decimal(str(bill_data.get('accommodation_fee', 0))) +
            subsidy_fee +
            Decimal(str(bill_data.get('other_fee', 0)))
        )

        # 7. L7 决策：项目总账必填明细，合计=主单
        items_data = bill_data.get('items', [])
        if bill_type == 'project_total':
            if not items_data or len(items_data) < 1:
                return False, '项目总账必须填写至少 1 条明细', None
            items_total = sum(Decimal(str(item.get('amount', 0))) for item in items_data)
            if abs(items_total - total) > Decimal('0.01'):
                return False, f'明细合计 {items_total} 与主单金额 {total} 不一致', None

        # 8. 生成单号
        bill_no = generate_bill_no(project.project_code)

        # 9. K4 决策：记录标准来源（v2.11.2：含地区档）
        applied_standard_source_json = None
        if user_id is not None and subsidy_fee > 0:
            user_pos = UserPosition.query.filter_by(user_id=user_id).order_by(UserPosition.effective_date.desc()).first()
            if user_pos:
                max_standards = get_max_standard(user_id, [project_id], destination)
                if max_standards:
                    from utils.region import resolve_region_tier
                    reimb_user = SysUser.query.get(user_id)
                    applied_standard_source_json = json.dumps({
                        'position_id': user_pos.position_id,
                        'staff_type': reimb_user.staff_type if reimb_user else '在编',
                        'items': [{
                            'subsidy_type': s.subsidy_type,
                            'amount': float(s.amount),
                            'source_project_id': s.project_id,
                            'region_tier': s.region_tier,
                        } for s in max_standards.values()],
                        'apply_days': (end - start).days + 1,
                        'destination': destination or None,
                        'region_tier': resolve_region_tier(destination) if destination else None,
                    }, ensure_ascii=False)

        # 10. 创建主单
        bill = ExpenseBill(
            bill_no=bill_no,
            user_id=user_id,
            project_id=project_id,
            bill_type=bill_type,
            travel_start_date=start,
            travel_end_date=end,
            destination=bill_data.get('destination', ''),
            transport_fee=bill_data.get('transport_fee', 0),
            accommodation_fee=bill_data.get('accommodation_fee', 0),
            subsidy_fee=subsidy_fee,
            other_fee=bill_data.get('other_fee', 0),
            total_amount=total,
            capital_amount=amount_to_capital(float(total)),
            status='draft',
            creator_id=operator_id,
            is_agent_filled=is_agent_filled,
            applied_standard_source=applied_standard_source_json,
        )
        db.session.add(bill)
        db.session.flush()

        # 11. 创建明细
        for item_data in items_data:
            item = ExpenseBillItem(
                bill_id=bill.id,
                item_type=item_data['item_type'],
                amount=item_data['amount'],
                expense_date=dt.strptime(item_data['expense_date'], '%Y-%m-%d').date(),
                description=item_data.get('description', ''),
                attachment_path=item_data.get('attachment_path'),
                attachment_hash=item_data.get('attachment_hash'),
            )
            db.session.add(item)

        # 12. 写操作日志
        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role,
            action='CREATE_BILL',
            target_type='bill',
            target_id=str(bill.id),
            detail=json.dumps({
                'bill_no': bill_no,
                'bill_type': bill_type,
                'total': float(total),
            }, ensure_ascii=False),
        )
        db.session.add(log)
        db.session.commit()

        # 13. 预检预警（考勤联动 + 调令校验，不阻断）
        from services.precheck_service import run_prechecks, summarize
        warning_summary = summarize(run_prechecks(bill))

        msg = '创建成功'
        if warning_summary:
            msg = f'创建成功（预检预警：{warning_summary}）'
        return True, msg, bill

    @staticmethod
    def submit_bill(operator_id: int, bill_id: int) -> tuple:
        """
        提交报销单

        G2 决策：代填 = 已审，提交后跳过稽核员初审
        """
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        operator = SysUser.query.get(operator_id)

        # 判断提交后状态
        if bill.bill_type == 'project_total':
            target_status = 'submitted_auditor'
        elif bill.is_agent_filled:
            target_status = 'submitted_finance'  # G2：跳过初审
        else:
            target_status = 'submitted_auditor'

        # 状态转换校验
        ok, msg = check_status_transition(bill.status, target_status)
        if not ok:
            return False, msg

        # 设置 auditor_id
        if bill.bill_type == 'project_total':
            bill.auditor_id = operator_id
        elif bill.is_agent_filled:
            bill.auditor_id = operator_id
        else:
            # 自填：稽核员字段设为绑定
            binding = AgentAuth.query.filter_by(
                be_agent_id=bill.user_id, project_id=bill.project_id, status='active'
            ).first()
            if not binding:
                return False, '该报销人在此项目未绑定稽核员'
            bill.auditor_id = binding.agent_id

        bill.status = target_status
        db.session.commit()

        # M3 通知
        try:
            notify_bill_status_change(bill, 'submit', operator)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return True, '提交成功'

    @staticmethod
    def audit_by_auditor(operator_id: int, bill_id: int, decision: str, comment: str = '') -> tuple:
        """
        稽核员初审
        G1 决策：自审允许
        """
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        operator = SysUser.query.get(operator_id)
        if operator.role != 'auditor':
            return False, '仅稽核员可操作'

        if bill.auditor_id != operator_id:
            return False, '您不是该单的稽核员'

        if decision == 'approve':
            new_status = 'auditor_ok'
        elif decision == 'reject':
            new_status = 'rejected_auditor'
        else:
            return False, 'decision 必须是 approve 或 reject'

        ok, msg = check_status_transition(bill.status, new_status)
        if not ok:
            return False, msg

        bill.status = new_status
        bill.auditor_audit_at = datetime.now()
        bill.auditor_comment = comment

        # 金额阈值
        required = determine_required_audit(float(bill.total_amount))
        if required == 'auditor_only':
            bill.status = 'archived'
            bill.archived_at = datetime.now()

        # 预检预警（考勤联动 + 调令校验）：通过时仍有预警 → 落审计日志供追溯
        from services.precheck_service import run_prechecks, summarize
        warning_summary = summarize(run_prechecks(bill))
        if warning_summary:
            db.session.add(AuditLog(
                actor_id=operator_id,
                actor_role=operator.role,
                action='PRECHECK_WARNING',
                target_type='bill',
                target_id=str(bill.id),
                detail=warning_summary,
            ))

        db.session.commit()

        # 通知
        try:
            event = 'auditor_ok' if decision == 'approve' else 'auditor_reject'
            notify_bill_status_change(bill, event, operator)
            db.session.commit()
        except Exception:
            db.session.rollback()

        msg = f'审核成功，新状态：{bill.status}'
        if warning_summary:
            msg += f'（预检预警：{warning_summary}）'
        return True, msg

    @staticmethod
    def audit_by_finance(operator_id: int, bill_id: int, decision: str, comment: str = '', dual_signer_id: int = None) -> tuple:
        """财务终审"""
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        operator = SysUser.query.get(operator_id)
        if operator.role != 'finance':
            return False, '仅财务可操作'

        # 主审财务校验
        project = ExpenseProject.query.get(bill.project_id)
        if project.finance_auditor_id and project.finance_auditor_id != operator_id:
            return False, '您不是该项目的主审财务'

        # auditor_ok → submitted_finance
        if bill.status == 'auditor_ok':
            bill.status = 'submitted_finance'
            bill.finance_auditor_id = operator_id
            db.session.commit()

        if decision == 'approve':
            required = determine_required_audit(float(bill.total_amount))

            if required == 'dual_sign_required':
                # D3 双签：大额报销必须两人分别操作
                if not dual_signer_id:
                    return False, '大额报销需双人会签，请指定第二签人'
                if dual_signer_id == operator_id:
                    return False, '第二签人不能是您自己'
                # 第二签人必须存在 + 是财务
                dual = SysUser.query.get(dual_signer_id)
                if not dual or dual.role != 'finance':
                    return False, '第二签人不存在或不是财务'
                if dual.account_status != 'normal':
                    return False, '第二签人账号状态异常'

                # 主财务 approve → 状态 = pending_dual_sign（不归档，待第二签人）
                bill.status = 'pending_dual_sign'
                bill.finance_audit_at = datetime.now()
                bill.finance_comment = comment
                bill.finance_dual_signer_id = dual_signer_id
                # finance_dual_signed 留空，等第二签人 approve 时才设 True

                # 终审独立审计：主财务发起双签
                from services.research_audit_service import log_research_audit
                log_research_audit(
                    bill_id=bill.id,
                    auditor_id=operator_id,
                    action='dual_sign_request',
                    reason=f'主财务 approve，等待第二签人 #{dual_signer_id} 终审',
                    original_status='submitted_finance',
                    new_status='pending_dual_sign',
                    auditor_role='finance',
                )

                # 同步写 FinanceAuditLog
                log = FinanceAuditLog(
                    finance_user_id=operator_id,
                    action='FINAL_APPROVE_PENDING_DUAL',
                    bill_id=bill.id,
                    amount=bill.total_amount,
                    original_status='submitted_finance',
                    new_status='pending_dual_sign',
                    comment=comment,
                    dual_signer_id=dual_signer_id,
                )
                db.session.add(log)
                db.session.commit()

                # 通知第二签人
                try:
                    notify_bill_status_change(bill, 'pending_dual_sign', operator)
                    # v2.2.0 用模板化的便捷通知
                    notification_service.notify_bill_pending_dual(bill, operator_id)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

                return True, f'已提交，待第二签人 #{dual_signer_id} 终审'

            # 小额：直接终审通过
            bill.status = 'approved'
            bill.finance_audit_at = datetime.now()
            bill.finance_comment = comment

            # 终审独立审计
            log = FinanceAuditLog(
                finance_user_id=operator_id,
                action='FINAL_APPROVE',
                bill_id=bill.id,
                amount=bill.total_amount,
                original_status='submitted_finance',
                new_status='approved',
                comment=comment,
                dual_signer_id=None,
            )
            db.session.add(log)

            # 自动归档
            bill.status = 'archived'
            bill.archived_at = datetime.now()
            db.session.commit()

            # 通知
            try:
                notify_bill_status_change(bill, 'finance_approve', operator)
                db.session.commit()
            except Exception:
                db.session.rollback()

            return True, '终审通过'

        elif decision == 'reject':
            bill.status = 'rejected_finance'
            bill.finance_audit_at = datetime.now()
            bill.finance_comment = comment

            log = FinanceAuditLog(
                finance_user_id=operator_id,
                action='FINAL_REJECT',
                bill_id=bill.id,
                amount=bill.total_amount,
                original_status='submitted_finance',
                new_status='rejected_finance',
                comment=comment,
            )
            db.session.add(log)
            db.session.commit()

            # 通知
            try:
                notify_bill_status_change(bill, 'finance_reject', operator)
                db.session.commit()
            except Exception:
                db.session.rollback()

            return True, '已驳回到稽核员'

        else:
            return False, 'decision 必须是 approve 或 reject'

    @staticmethod
    def approve_dual_sign(operator_id: int, bill_id: int, comment: str = '') -> tuple:
        """D3 双签：第二签人同意终审

        必须：
        - operator_id == bill.finance_dual_signer_id（指定的第二签人）
        - 当前状态 == 'pending_dual_sign'
        - 操作人是财务

        成功：
        - 状态 = approved → archived
        - finance_dual_signed = True
        - 写 ResearchAuditLog + FinanceAuditLog
        """
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        if bill.status != 'pending_dual_sign':
            return False, f'当前状态 {bill.status}，非待双签状态'

        if bill.finance_dual_signer_id != operator_id:
            return False, f'您不是该单据指定的第二签人（指定 #{bill.finance_dual_signer_id}）'

        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'finance':
            return False, '仅财务可双签'

        original_status = bill.status

        # 终审通过
        bill.status = 'approved'
        bill.finance_dual_signed = True
        bill.finance_dual_sign_at = datetime.now()
        bill.finance_dual_comment = comment

        # 终审独立审计
        from services.research_audit_service import log_research_audit
        log_research_audit(
            bill_id=bill.id,
            auditor_id=operator_id,
            action='dual_sign_approve',
            reason=comment or '第二签人同意终审',
            original_status=original_status,
            new_status='approved',
            auditor_role='finance',
        )

        # 同步写 FinanceAuditLog
        log = FinanceAuditLog(
            finance_user_id=operator_id,
            action='FINAL_APPROVE_DUAL',
            bill_id=bill.id,
            amount=bill.total_amount,
            original_status=original_status,
            new_status='approved',
            comment=comment,
            dual_signer_id=operator_id,  # 第二签人就是操作人
        )
        db.session.add(log)

        # 自动归档
        bill.status = 'archived'
        bill.archived_at = datetime.now()
        db.session.commit()

        # 通知
        try:
            notify_bill_status_change(bill, 'finance_approve', operator)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return True, '双签通过，已归档'

    @staticmethod
    def reject_dual_sign(operator_id: int, bill_id: int, reason: str = '') -> tuple:
        """D3 双签：第二签人拒绝终审

        必须：
        - operator_id == bill.finance_dual_signer_id
        - 当前状态 == 'pending_dual_sign'
        - 操作人是财务
        - reason 必填（≥10 字符）
        """
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        if bill.status != 'pending_dual_sign':
            return False, f'当前状态 {bill.status}，非待双签状态'

        if bill.finance_dual_signer_id != operator_id:
            return False, f'您不是该单据指定的第二签人（指定 #{bill.finance_dual_signer_id}）'

        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'finance':
            return False, '仅财务可双签'

        if not reason or len(reason) < 10:
            return False, '拒绝原因至少 10 个字符（用于审计追溯）'

        original_status = bill.status

        # 终审驳回
        bill.status = 'rejected_finance'
        bill.finance_dual_signed = False
        bill.finance_dual_sign_at = datetime.now()
        bill.finance_dual_comment = reason

        # 终审独立审计
        from services.research_audit_service import log_research_audit
        log_research_audit(
            bill_id=bill.id,
            auditor_id=operator_id,
            action='dual_sign_reject',
            reason=reason,
            original_status=original_status,
            new_status='rejected_finance',
            auditor_role='finance',
        )

        # 同步写 FinanceAuditLog
        log = FinanceAuditLog(
            finance_user_id=operator_id,
            action='FINAL_REJECT_DUAL',
            bill_id=bill.id,
            amount=bill.total_amount,
            original_status=original_status,
            new_status='rejected_finance',
            comment=reason,
            dual_signer_id=operator_id,
        )
        db.session.add(log)
        db.session.commit()

        # 通知
        try:
            notify_bill_status_change(bill, 'finance_reject', operator)
            # v2.2.0 显式通知主财务 + 报销人
            notification_service.notify_bill_dual_rejected(bill, operator_id, reason)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return True, '双签驳回'

    @staticmethod
    def list_bills(operator_id: int, filters: dict = None) -> list:
        """查询列表（按角色过滤）"""
        operator = SysUser.query.get(operator_id)
        query = ExpenseBill.query

        if operator.role == 'reimburser':
            query = query.filter(ExpenseBill.user_id == operator_id)
        elif operator.role == 'auditor':
            my_reimbursers = [a.be_agent_id for a in AgentAuth.query.filter_by(
                agent_id=operator_id, status='active'
            ).all()]
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    ExpenseBill.auditor_id == operator_id,
                    ExpenseBill.user_id.in_(my_reimbursers),
                )
            )
        # finance 看全部

        if filters:
            if 'status' in filters:
                query = query.filter(ExpenseBill.status == filters['status'])
            if 'project_id' in filters:
                query = query.filter(ExpenseBill.project_id == filters['project_id'])
            if 'user_id' in filters:
                query = query.filter(ExpenseBill.user_id == filters['user_id'])
            if 'bill_type' in filters:
                query = query.filter(ExpenseBill.bill_type == filters['bill_type'])

        return query.order_by(ExpenseBill.created_at.desc()).all()

    @staticmethod
    def delete_bill(operator_id: int, bill_id: int) -> tuple:
        """
        M7 决策：删除报销单
        仅 draft 状态，仅创建者可删
        """
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        if bill.status != 'draft':
            return False, f'仅 draft 状态可删除，当前 {bill.status}'

        if bill.creator_id != operator_id:
            return False, '仅创建者可删除'

        bill_no = bill.bill_no

        # 删除明细
        ExpenseBillItem.query.filter_by(bill_id=bill_id).delete()

        # 写日志
        operator = SysUser.query.get(operator_id)
        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role if operator else 'unknown',
            action='DELETE_BILL',
            target_type='bill',
            target_id=str(bill_id),
            detail=json.dumps({
                'bill_no': bill_no,
                'total_amount': float(bill.total_amount),
            }, ensure_ascii=False),
        )
        db.session.add(log)

        db.session.delete(bill)
        db.session.commit()

        return True, f'已删除报销单 {bill_no}'

    @staticmethod
    def override_bill(
        operator_id: int,
        bill_id: int,
        target_status: str,
        reason: str,
    ) -> tuple:
        """D3 决策：财务强制修改单据状态（override）

        Args:
            operator_id: 财务用户 ID
            bill_id: 单据 ID
            target_status: 目标状态
            reason: 强制修改原因（必填，≥10 字符）

        Returns:
            (ok, message)
        """
        # 1. 校验操作人
        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'finance':
            return False, '仅财务可强制修改'

        # 2. 校验单据
        bill = ExpenseBill.query.get(bill_id)
        if not bill:
            return False, '报销单不存在'

        # 3. 校验目标状态合法
        allowed_targets = {
            'draft', 'submitted', 'submitted_auditor', 'auditor_ok',
            'submitted_finance', 'approved', 'rejected_auditor',
            'rejected_finance', 'archived',
        }
        if target_status not in allowed_targets:
            return False, f'非法目标状态: {target_status}'

        # 4. 不能从归档/删除状态 override
        if bill.status in ('red_rush',):
            return False, f'已冲红的单据不可 override'

        # 5. 必须有原因
        if not reason or len(reason) < 10:
            return False, '原因至少 10 个字符（用于审计追溯）'

        original_status = bill.status

        # 6. 写 ResearchAuditLog（独立审计通道）
        from services.research_audit_service import log_research_audit
        log_research_audit(
            bill_id=bill_id,
            auditor_id=operator_id,
            action='override',
            reason=reason,
            original_status=original_status,
            new_status=target_status,
            auditor_role='finance',
        )

        # 7. 修改状态
        bill.status = target_status
        if target_status == 'archived' and not bill.archived_at:
            bill.archived_at = datetime.now()

        # 8. 写通用审计日志
        log = AuditLog(
            actor_id=operator_id,
            actor_role='finance',
            action='OVERRIDE_BILL',
            target_type='bill',
            target_id=str(bill_id),
            detail=json.dumps({
                'from': original_status,
                'to': target_status,
                'reason': reason,
            }, ensure_ascii=False),
        )
        db.session.add(log)

        db.session.commit()

        # v2.2.0 通知报销人 + 主财务
        try:
            notification_service.notify_bill_overridden(bill, operator_id, target_status, reason)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return True, f'已强制修改：{original_status} → {target_status}'


# ============= 工具函数（拆分） =============

def check_project_validity_check(project: ExpenseProject) -> tuple:
    """简化的项目有效性校验（避免循环引用）"""
    if project.status != 'active':
        return False, f'项目状态：{project.status}'

    today = date.today()
    if today < project.start_date:
        return False, f'项目未到开始日期（{project.start_date}）'
    if today > project.end_date:
        return False, f'项目已过结束日期（{project.end_date}）'

    return True, ''
