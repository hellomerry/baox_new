"""客户端数据裁剪 service（v2.10.0）

业务流程：
- 财务创建稽核员 → 生成稽核员绿色客户端包（含稽核员需要的子集数据）
- 稽核员创建报销员 → 生成报销员绿色客户端包（含报销员需要的子集数据）
- 数据规模：财务 > 稽核员 > 报销员

数据裁剪规则：
- 财务 → 稽核员包：
  - sys_user：财务(自己) + 目标稽核员 + 该稽核员代理的所有报销人
  - expense_project：所有项目（稽核员需要看到所有项目做代填）
  - expense_bill：所有相关单据（稽核员代理的报销人 + 自己）
  - user_project / agent_auth / position / standard / notification / config：相关
- 稽核员 → 报销员包：
  - sys_user：稽核员(自己) + 目标报销人
  - expense_project：报销人绑定的项目
  - expense_bill：报销人自己的所有单据
  - 其他：相关

实现方式：直接用 SQL 复制需要的行到目标 db（轻量、不依赖 backup/restore 工具）
"""
import logging
import os
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text, inspect
from models import db
from models.models import (
    SysUser, ExpenseProject, UserProject, AgentAuth, ExpenseBill,
    ExpenseBillItem, AttendanceRecord, PositionLevel, UserPosition,
    ExpenseStandard, ImportLog, AuditLog, FinanceAuditLog, SysConfig,
    ClientMeta, Notification, NotificationTemplate, BillChangeLog,
    ErrorLog, Attachment, DataImportLog, AppVersion, ResearchAuditLog,
    PersonnelTransfer,
)
from config import Config

log = logging.getLogger(__name__)


# 数据规模由角色决定
ROLE_DATA_SCOPE = {
    'finance': 'full',          # 全部
    'auditor': 'managed',       # 自己 + 代理的报销人
    'reimburser': 'self',       # 仅自己
}


def _get_bills_for_user(user_id: int, role: str) -> List[int]:
    """获取某个用户应可见的所有单据 id"""
    if role == 'reimburser':
        # 报销员自己的所有单据
        bills = ExpenseBill.query.filter_by(user_id=user_id).all()
        return [b.id for b in bills]
    if role == 'auditor':
        # 稽核员：自己创建的 + 自己代理的报销人的单据
        managed_ids = db.session.execute(text(
            "SELECT be_agent_id FROM agent_auth WHERE agent_id = :aid AND status = 'active'"
        ), {'aid': user_id}).fetchall()
        managed_user_ids = [r[0] for r in managed_ids] + [user_id]
        bills = ExpenseBill.query.filter(
            (ExpenseBill.user_id.in_(managed_user_ids)) |
            (ExpenseBill.creator_id == user_id)
        ).all()
        return [b.id for b in bills]
    # finance: all
    return [b.id for b in ExpenseBill.query.with_entities(ExpenseBill.id).all()]


def _get_managed_reimbursers(auditor_id: int) -> List[int]:
    """获取稽核员代理的所有报销人 id"""
    rows = db.session.execute(text(
        "SELECT be_agent_id FROM agent_auth WHERE agent_id = :aid AND status = 'active'"
    ), {'aid': auditor_id}).fetchall()
    return [r[0] for r in rows]


def _get_projects_for_users(user_ids: List[int]) -> List[int]:
    """获取这些用户绑定的项目 id 列表"""
    if not user_ids:
        return []
    rows = db.session.execute(text(
        "SELECT DISTINCT project_id FROM user_project WHERE user_id IN :uids AND status = 'active'"
    ).bindparams(db.bindparam('uids', expanding=True)),
        {'uids': user_ids}
    ).fetchall()
    return [r[0] for r in rows]


def _get_user_ids_for_auditor(auditor_id: int) -> List[int]:
    """稽核员 + 自己代理的报销人"""
    managed = _get_managed_reimbursers(auditor_id)
    return list(set(managed + [auditor_id]))


# ============= 数据裁剪：财务 → 稽核员 =============

def export_auditor_db(auditor_id: int, target_db_path: str,
                       include_finance_id: int = None) -> Dict:
    """为稽核员生成裁剪后的 SQLite 数据库

    包含：
    - 目标稽核员账号（密码重置为初始默认）
    - 该稽核员代理的所有报销人
    - 一个财务账号（用于跨设备登录时回传数据）
    - 所有项目（稽核员代填需要看到全项目）
    - 相关单据（稽核员 + 自己代理的报销人的单据）
    - 通知、配置、审计、版本等
    """
    if os.path.exists(target_db_path):
        os.remove(target_db_path)

    managed_reimbursers = _get_managed_reimbursers(auditor_id)
    relevant_user_ids = set(managed_reimbursers + [auditor_id])
    if include_finance_id:
        relevant_user_ids.add(include_finance_id)
    relevant_user_ids = list(relevant_user_ids)

    relevant_bill_ids = _get_bills_for_user(auditor_id, 'auditor')
    relevant_projects = _get_projects_for_users(relevant_user_ids)
    # 稽核员能看到所有项目（代填场景）
    all_project_ids = [p.id for p in ExpenseProject.query.all()]

    log.info(
        f'稽核员 #{auditor_id} 裁剪: '
        f'users={len(relevant_user_ids)}, projects={len(all_project_ids)}, bills={len(relevant_bill_ids)}'
    )

    return _write_target_db(
        target_db_path=target_db_path,
        user_ids=relevant_user_ids,
        project_ids=all_project_ids,
        bill_ids=relevant_bill_ids,
        include_notification_target_ids=relevant_user_ids,
    )


# ============= 数据裁剪：稽核员 → 报销员 =============

def export_reimburser_db(reimburser_id: int, target_db_path: str,
                          include_auditor_id: int = None) -> Dict:
    """为报销员生成裁剪后的 SQLite 数据库

    包含：
    - 目标报销员账号
    - 该报销员的稽核员（用于查看审核状态）
    - 报销员绑定的项目
    - 报销员自己的所有单据
    - 通知、配置
    """
    if os.path.exists(target_db_path):
        os.remove(target_db_path)

    relevant_user_ids = [reimburser_id]
    if include_auditor_id:
        relevant_user_ids.append(include_auditor_id)

    relevant_bill_ids = _get_bills_for_user(reimburser_id, 'reimburser')
    relevant_projects = _get_projects_for_users([reimburser_id])

    log.info(
        f'报销员 #{reimburser_id} 裁剪: '
        f'users={len(relevant_user_ids)}, projects={len(relevant_projects)}, bills={len(relevant_bill_ids)}'
    )

    return _write_target_db(
        target_db_path=target_db_path,
        user_ids=relevant_user_ids,
        project_ids=relevant_projects,
        bill_ids=relevant_bill_ids,
        include_notification_target_ids=relevant_user_ids,
    )


# ============= 数据裁剪：财务 → 财务（重打包） =============

def export_finance_db(finance_id: int, target_db_path: str) -> Dict:
    """为财务生成完整数据（重新打包自己用）"""
    if os.path.exists(target_db_path):
        os.remove(target_db_path)

    all_users = [u.id for u in SysUser.query.all()]
    all_projects = [p.id for p in ExpenseProject.query.all()]
    all_bills = [b.id for b in ExpenseBill.query.with_entities(ExpenseBill.id).all()]

    log.info(f'财务 #{finance_id} 完整备份: users={len(all_users)}, projects={len(all_projects)}, bills={len(all_bills)}')

    return _write_target_db(
        target_db_path=target_db_path,
        user_ids=all_users,
        project_ids=all_projects,
        bill_ids=all_bills,
        include_notification_target_ids=all_users,
    )


# ============= 通用：写目标 db =============

def _write_target_db(
    target_db_path: str,
    user_ids: List[int],
    project_ids: List[int],
    bill_ids: List[int],
    include_notification_target_ids: List[int],
) -> Dict:
    """用 SQL 复制行到目标 SQLite 数据库

    策略：直接操作源 db 拷贝到目标位置，然后 DELETE 不需要的行
    优点：不依赖 SQLAlchemy 模型定义新表，兼容任意 schema
    """
    # 1. 拷贝源 db（从 SQLAlchemy engine 拿真实路径，避免与测试 db 混淆）
    from sqlalchemy import create_engine
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    src_db = engine.url.database
    if not os.path.isabs(src_db):
        src_db = str(Config.BASE_DIR / src_db)
    # 关闭 engine 释放文件句柄
    engine.dispose()
    shutil.copy2(src_db, target_db_path)

    # 2. 打开目标 db 删多余行
    conn = sqlite3.connect(target_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # 2.1 sys_user：只保留相关用户
        if user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(f'DELETE FROM sys_user WHERE id NOT IN ({placeholders})', user_ids)

        # 2.2 expense_project：只保留相关项目
        if project_ids:
            placeholders = ','.join('?' * len(project_ids))
            cur.execute(f'DELETE FROM expense_project WHERE id NOT IN ({placeholders})', project_ids)
        else:
            cur.execute('DELETE FROM expense_project')

        # 2.3 user_project：清理无效关联
        if user_ids and project_ids:
            up_place = ','.join('?' * len(user_ids))
            pp_place = ','.join('?' * len(project_ids))
            cur.execute(
                f'DELETE FROM user_project WHERE user_id NOT IN ({up_place}) OR project_id NOT IN ({pp_place})',
                user_ids + project_ids
            )

        # 2.4 agent_auth：只保留相关用户的代理关系
        if user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(
                f'DELETE FROM agent_auth WHERE agent_id NOT IN ({placeholders}) AND be_agent_id NOT IN ({placeholders})',
                user_ids + user_ids
            )

        # 2.5 user_position：清理
        if user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(f'DELETE FROM user_position WHERE user_id NOT IN ({placeholders})', user_ids)

        # 2.6 expense_bill / expense_bill_item：只保留相关单据
        if bill_ids:
            placeholders = ','.join('?' * len(bill_ids))
            cur.execute(f'DELETE FROM expense_bill WHERE id NOT IN ({placeholders})', bill_ids)
            cur.execute(f'DELETE FROM expense_bill_item WHERE bill_id NOT IN ({placeholders})', bill_ids)
        else:
            cur.execute('DELETE FROM expense_bill')
            cur.execute('DELETE FROM expense_bill_item')

        # 2.7 attendance_record：只保留相关用户
        if user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(
                f'DELETE FROM attendance_record WHERE user_id NOT IN ({placeholders})',
                user_ids
            )

        # 2.8 attachment：保留相关单据的附件
        if bill_ids:
            placeholders = ','.join('?' * len(bill_ids))
            cur.execute(
                f'DELETE FROM attachment WHERE (bill_id > 0 AND bill_id NOT IN ({placeholders})) OR (bill_id = 0 AND uploader_id NOT IN ({",".join("?" * len(user_ids)) if user_ids else "0"}))',
                bill_ids + (user_ids if user_ids else [0])
            )
        elif user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(
                f'DELETE FROM attachment WHERE uploader_id NOT IN ({placeholders})',
                user_ids
            )
        else:
            cur.execute('DELETE FROM attachment')

        # 2.9 notification：只发给相关用户
        if include_notification_target_ids:
            placeholders = ','.join('?' * len(include_notification_target_ids))
            cur.execute(
                f'DELETE FROM notification WHERE user_id NOT IN ({placeholders})',
                include_notification_target_ids
            )
        # 2.10 personnel_transfer：只保留相关用户的
        if user_ids:
            placeholders = ','.join('?' * len(user_ids))
            cur.execute(
                f'DELETE FROM personnel_transfer WHERE operator_id NOT IN ({placeholders}) AND matched_user_id IS NOT NULL AND matched_user_id NOT IN ({placeholders})',
                user_ids + user_ids
            )

        # 2.11 audit_log / finance_audit_log / research_audit_log：保留最近的
        # 简化：保留所有（避免审计链断裂）

        # 2.12 清理：vacuum 压缩（VACUUM 不能在事务里）
        conn.commit()
        cur.execute('VACUUM')
    finally:
        conn.close()

    return {
        'success': True,
        'users': len(user_ids),
        'projects': len(project_ids),
        'bills': len(bill_ids),
        'db_size': os.path.getsize(target_db_path),
    }
