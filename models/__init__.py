"""
models 包初始化
导出 db 和所有 Model 类（供 init_db.py 和其他模块使用）
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# 导入所有 Model
from .models import (
    SysUser, ExpenseProject, UserProject, AgentAuth,
    FinancialControlRule, ExpenseBill, ExpenseBillItem,
    AttendanceRecord, PositionLevel, ExpenseStandard, UserPosition,
    ImportLog, AuditLog, FinanceAuditLog, SysConfig, ClientMeta,
    Notification,           # M3 决策新增
    BillChangeLog,          # N3 决策新增
    ErrorLog,               # N4 决策新增
)

__all__ = [
    'db',
    'SysUser', 'ExpenseProject', 'UserProject', 'AgentAuth',
    'FinancialControlRule', 'ExpenseBill', 'ExpenseBillItem',
    'AttendanceRecord', 'PositionLevel', 'ExpenseStandard', 'UserPosition',
    'ImportLog', 'AuditLog', 'FinanceAuditLog', 'SysConfig', 'ClientMeta',
    'Notification', 'BillChangeLog', 'ErrorLog',
]
