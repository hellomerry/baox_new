"""
冲红服务（L2 决策）
- 财务冲红：已批准的报销单出错时，生成一笔反向单据
- 只能冲红 archived/approved 状态的单据
- 冲红单与原单关联
"""
import json
from datetime import datetime
from decimal import Decimal

from models import db
from models.models import (
    ExpenseBill, ExpenseBillItem, SysUser, AuditLog, FinanceAuditLog, ExpenseProject
)
from utils.bill_number import generate_bill_no, amount_to_capital
from utils.validators import check_status_transition


class RedRushService:

    @staticmethod
    def red_rush_bill(operator_id: int, original_bill_id: int, reason: str) -> tuple:
        """
        冲红一张已归档的报销单

        :return: (ok, message, new_bill)
        """
        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'finance':
            return False, '仅财务可冲红', None

        original = ExpenseBill.query.get(original_bill_id)
        if not original:
            return False, '原报销单不存在', None

        if original.status not in ('archived', 'approved'):
            return False, f'仅已批准/已归档单据可冲红，当前状态 {original.status}', None

        if original.red_rushed:
            return False, '该单已冲红过，不可重复冲红', None

        # 生成冲红单（金额取负）
        project = ExpenseProject.query.get(original.project_id)
        new_bill = ExpenseBill(
            bill_no=generate_bill_no(project.project_code),
            user_id=original.user_id,
            project_id=original.project_id,
            bill_type=original.bill_type,
            travel_start_date=original.travel_start_date,
            travel_end_date=original.travel_end_date,
            destination=f'[冲红] {original.destination or ""}',
            transport_fee=-Decimal(str(original.transport_fee or 0)),
            accommodation_fee=-Decimal(str(original.accommodation_fee or 0)),
            subsidy_fee=-Decimal(str(original.subsidy_fee or 0)),
            other_fee=-Decimal(str(original.other_fee or 0)),
            total_amount=-Decimal(str(original.total_amount or 0)),
            capital_amount='负 ' + (original.capital_amount or ''),
            status='submitted_finance',  # 冲红单直接进财务终审
            creator_id=operator_id,
            is_agent_filled=True,
            red_rush_of=original.id,
        )
        db.session.add(new_bill)
        db.session.flush()  # 拿到 new_bill.id

        # 复制明细（金额取负）
        original_items = ExpenseBillItem.query.filter_by(bill_id=original.id).all()
        for it in original_items:
            new_item = ExpenseBillItem(
                bill_id=new_bill.id,
                item_type=it.item_type,
                amount=-Decimal(str(it.amount or 0)),
                expense_date=it.expense_date,
                description=f'[冲红] {it.description or ""}',
                attachment_path=it.attachment_path,
                attachment_hash=it.attachment_hash,
            )
            db.session.add(new_item)

        # 标记原单为已冲红
        original.red_rushed = True
        original.red_rush_bill_id = new_bill.id

        # 写日志
        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role,
            action='RED_RUSH_BILL',
            target_type='bill',
            target_id=str(original.id),
            detail=json.dumps({
                'bill_no': original.bill_no,
                'red_rush_bill_id': new_bill.id,
                'reason': reason,
            }, ensure_ascii=False),
        )
        db.session.add(log)

        # 财务独立审计
        fin_log = FinanceAuditLog(
            finance_user_id=operator_id,
            action='RED_RUSH',
            bill_id=original.id,
            amount=original.total_amount,
            original_status='archived',
            new_status='archived',
            comment=reason,
        )
        db.session.add(fin_log)

        db.session.commit()

        return True, f'冲红成功，新单号 {new_bill.bill_no}', new_bill
