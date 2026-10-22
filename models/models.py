"""
数据库 Model 定义
严格遵循 T0 任务书 + 88 条决策（A-P）
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Date, DateTime, DECIMAL, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from . import db


# ============= 表 1：sys_user（统一账号表）============
class SysUser(db.Model):
    __tablename__ = 'sys_user'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # Werkzeug pbkdf2 哈希
    real_name = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # finance / auditor / reimburser
    id_card = Column(String(255), nullable=True)            # N1 加密存储（base64）
    bank_card = Column(String(255), nullable=True)          # N1 加密存储
    phone = Column(String(255), nullable=True)              # N1 加密存储
    email = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    staff_type = Column(String(20), nullable=True)         # 在编/借调/跟班/实战练兵
    valid_start_date = Column(Date, nullable=True)
    valid_end_date = Column(Date, nullable=True)
    buffer_end_date = Column(Date, nullable=True)
    account_status = Column(String(20), default='normal')  # M4 决策：normal / locked / inactive
    failure_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    creator_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 自审回避辅助字段（C4 / G1）：用于检测同一自然人是否跨账号
    natural_person_key = Column(String(64), nullable=True, index=True)
    # 注：v2.10.0 模式 C 混合部署不再用独立字段，直接复用 agent_auth 表：
    # - 有 active agent_auth 关系 → 模式 C（稽核员代填，无需客户端）
    # - 无 active agent_auth 关系 → 模式 B（自助，正常登录）

    # 约束
    __table_args__ = (
        Index('idx_sys_user_role_status', 'role', 'account_status'),
    )


# ============= 表 2：expense_project（报销项目）============
class ExpenseProject(db.Model):
    __tablename__ = 'expense_project'

    id = Column(Integer, primary_key=True)
    project_code = Column(String(20), unique=True, nullable=False)
    project_name = Column(String(200), nullable=False)
    project_type = Column(String(20), nullable=False)  # 普通 / 专案
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), default='active')  # M6: active / inactive / archived
    finance_auditor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    max_amount_limit = Column(DECIMAL(12, 2), nullable=True)
    allowed_agent_mode = Column(String(20), default='full')  # full / summary
    # L3 决策：项目总账预算控制
    total_budget = Column(DECIMAL(14, 2), nullable=True)
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============= 表 3：user_project（人项绑定）============
class UserProject(db.Model):
    __tablename__ = 'user_project'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=False, index=True)
    bind_date = Column(Date, default=date.today)
    unbind_date = Column(Date, nullable=True)
    status = Column(String(20), default='active')  # active / unbound
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_user_project'),
    )


# ============= 表 4：agent_auth（代理授权 / 稽核员绑定）============
class AgentAuth(db.Model):
    __tablename__ = 'agent_auth'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    be_agent_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=False, index=True)
    auth_start_date = Column(Date, nullable=False)
    auth_end_date = Column(Date, nullable=True)
    agent_mode = Column(String(20), default='full')
    status = Column(String(20), default='active')  # active / revoked
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# ============= 表 5：financial_control_rule（财务控制规则）============
class FinancialControlRule(db.Model):
    __tablename__ = 'financial_control_rule'

    id = Column(Integer, primary_key=True)
    rule_code = Column(String(50), unique=True, nullable=False)
    rule_name = Column(String(200), nullable=False)
    rule_type = Column(String(50), nullable=False)  # amount / attendance / duplicate / etc
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=True)
    config_json = Column(Text, nullable=False)
    severity = Column(String(20), default='warning')  # info / warning / block
    enabled = Column(Boolean, default=True)
    effective_start = Column(Date, nullable=True)
    effective_end = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============= 表 6：expense_bill（报销单主表）============
class ExpenseBill(db.Model):
    __tablename__ = 'expense_bill'

    id = Column(Integer, primary_key=True)
    bill_no = Column(String(50), unique=True, nullable=False, index=True)
    # F1 / L5：B<YYYYMMDD>-<project_code>-<5位序号>

    # G3 / X5 决策：user_id 允许 NULL（项目总账时）
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=False, index=True)
    # G6 决策：bill_type 枚举
    bill_type = Column(String(20), nullable=False)  # personal / project_total / 普通 / 专案
    travel_start_date = Column(Date, nullable=False)
    travel_end_date = Column(Date, nullable=False)
    destination = Column(String(200), nullable=True)

    transport_fee = Column(DECIMAL(10, 2), default=0)
    accommodation_fee = Column(DECIMAL(10, 2), default=0)
    subsidy_fee = Column(DECIMAL(10, 2), default=0)
    other_fee = Column(DECIMAL(10, 2), default=0)
    total_amount = Column(DECIMAL(12, 2), nullable=False)
    capital_amount = Column(String(100), nullable=True)  # 大写金额

    # 状态机
    status = Column(String(30), default='draft', index=True)
    # draft / submitted_auditor / rejected_auditor / auditor_ok 
    # / submitted_finance / rejected_finance / approved / archived

    # 创建与流转
    creator_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    # G2 决策：is_agent_filled = (creator_id != user_id)
    is_agent_filled = Column(Boolean, default=False)

    # 稽核员初审
    auditor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    auditor_audit_at = Column(DateTime, nullable=True)
    auditor_comment = Column(Text, nullable=True)

    # 财务终审
    finance_auditor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    finance_audit_at = Column(DateTime, nullable=True)
    finance_comment = Column(Text, nullable=True)
    finance_dual_signed = Column(Boolean, default=False)
    finance_dual_signer_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    finance_dual_sign_at = Column(DateTime, nullable=True)  # v2.1.0: 第二签人签字时间
    finance_dual_comment = Column(Text, nullable=True)  # v2.1.0: 第二签人备注

    # 归档
    archived_at = Column(DateTime, nullable=True)

    # 稽核引擎标记
    audit_blocked = Column(Boolean, default=False)
    audit_block_reason = Column(Text, nullable=True)

    # K4 决策：标准来源记录（用于审计追溯）
    applied_standard_source = Column(Text, nullable=True)
    # JSON: {position_id, staff_type, items: [{subsidy_type, amount, source_project_id}], apply_days}

    # L2 决策：冲红相关字段
    red_rushed = Column(Boolean, default=False)
    red_rush_of = Column(Integer, ForeignKey('expense_bill.id'), nullable=True)
    red_rush_bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=True)

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============= 表 7：expense_bill_item（报销单明细）============
class ExpenseBillItem(db.Model):
    __tablename__ = 'expense_bill_item'

    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=False, index=True)
    item_type = Column(String(50), nullable=False)  # 交通/住宿/伙食/其他
    amount = Column(DECIMAL(10, 2), nullable=False)
    expense_date = Column(Date, nullable=False)
    description = Column(String(500), nullable=True)
    attachment_path = Column(String(500), nullable=True)  # 票据路径
    attachment_hash = Column(String(64), nullable=True, index=True)  # 票据 SHA256（防重）
    created_at = Column(DateTime, default=datetime.now)


# ============= 表 8：attendance_record（考勤记录）============
class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_record'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # 出差 / 在岗 / 未在岗 / 请假
    remark = Column(String(500), nullable=True)
    audit_status = Column(String(20), default='pending')  # H1: pending / approved / rejected
    auditor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    audited_at = Column(DateTime, nullable=True)
    audit_comment = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============= 表 9：position_level（职务等级·增强）============
class PositionLevel(db.Model):
    __tablename__ = 'position_level'

    id = Column(Integer, primary_key=True)
    level_code = Column(String(20), unique=True, nullable=False)
    level_name = Column(String(50), nullable=False)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ============= 表 9.5：expense_standard（报销标准）— K9 决策 =============
class ExpenseStandard(db.Model):
    __tablename__ = 'expense_standard'

    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey('position_level.id'), nullable=True)  # null=通用
    staff_type = Column(String(20), nullable=False)  # 在编/借调/跟班
    subsidy_type = Column(String(50), nullable=False)  # 伙食/住宿/交通/其他
    amount = Column(DECIMAL(10, 2), nullable=False)
    project_id = Column(Integer, ForeignKey('expense_project.id'), nullable=True)  # null=全局
    valid_start = Column(Date, nullable=False)
    valid_end = Column(Date, nullable=True)
    remark = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(Integer, ForeignKey('sys_user.id'), nullable=True)


# ============= 表 10：user_position（人员职务·增强）============
class UserPosition(db.Model):
    __tablename__ = 'user_position'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey('position_level.id'), nullable=False)
    effective_date = Column(Date, nullable=False)
    expire_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ============= 表 11：import_log（数据包导入日志）============
class ImportLog(db.Model):
    __tablename__ = 'import_log'

    id = Column(Integer, primary_key=True)
    package_id = Column(String(36), unique=True, nullable=False, index=True)
    package_type = Column(String(50), nullable=False)
    manifest_json = Column(Text, nullable=False)
    payload_summary = Column(Text, nullable=True)
    import_status = Column(String(20), default='success')
    skip_reason = Column(String(200), nullable=True)
    imported_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    imported_at = Column(DateTime, default=datetime.now)


# ============= 表 12：audit_log（操作日志）============
class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    actor_role = Column(String(20), nullable=False)
    action = Column(String(50), nullable=False, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(50), nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ============= 表 13：finance_audit_log（终审独立审计表）============
class FinanceAuditLog(db.Model):
    __tablename__ = 'finance_audit_log'

    id = Column(Integer, primary_key=True)
    finance_user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=False, index=True)
    amount = Column(DECIMAL(12, 2), nullable=True)
    original_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    comment = Column(Text, nullable=True)
    dual_signer_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ============= 表 14：sys_config（系统配置）============
class SysConfig(db.Model):
    __tablename__ = 'sys_config'

    id = Column(Integer, primary_key=True)
    config_key = Column(String(50), unique=True, nullable=False)
    config_value = Column(Text, nullable=False)
    config_name = Column(String(100), nullable=False)
    remark = Column(String(200), nullable=True)
    updated_by = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============= 表 15：client_meta（客户端元信息）============
class ClientMeta(db.Model):
    __tablename__ = 'client_meta'

    id = Column(Integer, primary_key=True)
    client_id = Column(String(50), unique=True, nullable=False)
    client_type = Column(String(20), nullable=False)
    client_name = Column(String(100), nullable=False)
    install_time = Column(DateTime, default=datetime.now)
    last_start_time = Column(DateTime, nullable=True)
    current_account_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    cert_fingerprint = Column(String(64), nullable=True)


# ============= 表 16：notification（站内消息）— M3 + v2.2.0 扩展 =============
class Notification(db.Model):
    __tablename__ = 'notification'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)  # v2.2.0
    type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    target_url = Column(String(500), nullable=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(50), nullable=True)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=True, index=True)  # v2.2.0
    priority = Column(String(16), nullable=False, default='normal')  # v2.2.0
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    sender = db.relationship('SysUser', foreign_keys=[sender_id])
    bill = db.relationship('ExpenseBill', foreign_keys=[bill_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.real_name if self.sender else '系统',
            'type': self.type,
            'title': self.title,
            'content': self.content,
            'target_url': self.target_url,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'bill_id': self.bill_id,
            'bill_no': self.bill.bill_no if self.bill else None,
            'priority': self.priority,
            'is_read': self.is_read,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ============= 表 16.5：notification_template（v2.2.0）=============
class NotificationTemplate(db.Model):
    __tablename__ = 'notification_template'

    id = Column(Integer, primary_key=True)
    type = Column(String(32), nullable=False, unique=True)
    title_template = Column(String(200), nullable=False)
    content_template = Column(Text, nullable=False)
    default_priority = Column(String(16), nullable=False, default='normal')
    enabled = Column(Boolean, nullable=False, default=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'title_template': self.title_template,
            'content_template': self.content_template,
            'default_priority': self.default_priority,
            'enabled': self.enabled,
            'description': self.description,
        }


# ============= 表 17：bill_change_log（字段级修改日志）— N3 =============
class BillChangeLog(db.Model):
    __tablename__ = 'bill_change_log'

    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=False, index=True)
    field_name = Column(String(50), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    operator_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    operator_role = Column(String(20), nullable=False)
    reason = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ============= 表 17.5：research_audit_log（D3 终审独立审计表）============
class ResearchAuditLog(db.Model):
    """D3 决策：终审独立审计日志
    - 与 finance_audit_log 区分
    - finance_audit_log：财务双人会签
    - research_audit_log：终审（>10万元大额）独立审计、稽核员驳回溯源
    - 区别：终审是终局动作，独立性要求高
    """
    __tablename__ = 'research_audit_log'

    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=False, index=True)
    auditor_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    auditor_role = Column(String(20), nullable=False)  # finance / auditor
    action = Column(String(50), nullable=False)  # final_approve / final_reject / override
    reason = Column(Text, nullable=True)  # 驳回原因 / 备注
    original_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    ip_address = Column(String(50), nullable=True)
    client_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ============= 表 18：error_log（错误日志）— N4 =============
class ErrorLog(db.Model):
    __tablename__ = 'error_log'

    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    message = Column(String(500), nullable=False)
    stack_trace = Column(Text, nullable=True)
    context = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    client_id = Column(String(50), nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ============= 表 20：attachment（附件）============
class Attachment(db.Model):
    __tablename__ = 'attachment'

    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey('expense_bill.id'), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA256
    mime_type = Column(String(50), nullable=True)
    uploader_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.now)


# ============= 表 25：data_import_log（数据导入向导日志）— v2.3.0 =============
class DataImportLog(db.Model):
    __tablename__ = 'data_import_log'

    id = Column(Integer, primary_key=True)
    import_type = Column(String(20), nullable=False, index=True)  # user / project / standard
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    file_size = Column(Integer, nullable=False, default=0)
    total_rows = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default='pending')  # pending / success / partial / failed
    error_report = Column(Text, nullable=True)  # JSON 列表：每行错误详情
    imported_by = Column(Integer, ForeignKey('sys_user.id'), nullable=False)
    imported_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'import_type': self.import_type,
            'file_name': self.file_name,
            'file_hash': self.file_hash,
            'file_size': self.file_size,
            'total_rows': self.total_rows,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'status': self.status,
            'error_report': self.error_report,
            'imported_by': self.imported_by,
            'imported_at': self.imported_at.isoformat() if self.imported_at else None,
        }


# ============= 表 26：app_version（应用版本 + changelog）— v2.4.0 =============
class AppVersion(db.Model):
    __tablename__ = 'app_version'

    id = Column(Integer, primary_key=True)
    version = Column(String(20), nullable=False, unique=True)
    release_date = Column(Date, nullable=False)
    min_required_version = Column(String(20), nullable=True)  # 最低升级前置版本
    title = Column(String(200), nullable=False)
    changelog = Column(Text, nullable=False)
    mandatory = Column(Boolean, nullable=False, default=False)  # 是否强制升级
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self, include_changelog: bool = True):
        d = {
            'id': self.id,
            'version': self.version,
            'release_date': self.release_date.isoformat() if self.release_date else None,
            'min_required_version': self.min_required_version,
            'title': self.title,
            'mandatory': self.mandatory,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_changelog:
            d['changelog'] = self.changelog
        return d


# ============= 表 27：personnel_transfer（人员调令：借调/跟班学习/实战练兵）— v2.8.0 =============
class PersonnelTransfer(db.Model):
    """人员调令表（借调/跟班学习/实战练兵）

    业务场景：
    - 其他单位借调人员到我单位出差
    - 跟班学习人员（外派来我处培训）
    - 实战练兵人员（上级单位临时指派）

    主要用途：
    - OCR 识别调令图片，自动入库真实姓名 + 有效期
    - 稽核/财务审核报销单时校验调令有效性
    - 与报销单关联，证明出差合规
    """
    __tablename__ = 'personnel_transfer'

    id = Column(Integer, primary_key=True)

    # 调令基本信息
    transfer_type = Column(String(30), nullable=False, index=True)
    # borrow: 借调 / follow_training: 跟班学习 / combat_training: 实战练兵 / other: 其他
    real_name = Column(String(50), nullable=False, index=True)
    # 真实姓名（中文，从调令识别）
    id_card_no = Column(String(64), nullable=True)
    # 身份证号（识别或手填，会走 AES-256 加密）

    # 调令上下文
    transfer_no = Column(String(50), nullable=True)
    # 调令编号（公文文号）
    source_unit = Column(String(200), nullable=True)
    # 原单位/派出单位
    target_unit = Column(String(200), nullable=True)
    # 接收单位/我单位
    issuer = Column(String(200), nullable=True)
    # 签发人/签发单位
    issue_date = Column(Date, nullable=True)
    # 调令签发日期

    # 有效期时段（核心字段）
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)

    # OCR 元数据
    attachment_id = Column(Integer, ForeignKey('attachment.id'), nullable=True)
    raw_text = Column(Text, nullable=True)
    # 原始 OCR 文本（真实引擎接入后用）
    confidence = Column(Integer, default=0, nullable=False)
    # 0-100 整型，0=模拟/无识别
    ocr_engine = Column(String(50), default='mock', nullable=False)
    # mock / baidu / tencent / aliyun / tesseract

    # 关联系统用户（识别后人工匹配）
    matched_user_id = Column(Integer, ForeignKey('sys_user.id'), nullable=True, index=True)

    # 录入与操作
    operator_id = Column(Integer, ForeignKey('sys_user.id'), nullable=False, index=True)
    # 录入人（财务或稽核员）
    status = Column(String(20), default='active', nullable=False, index=True)
    # active: 有效 / expired: 已过期 / cancelled: 已作废

    remark = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self, include_raw: bool = False):
        d = {
            'id': self.id,
            'transfer_type': self.transfer_type,
            'real_name': self.real_name,
            'id_card_no': '***' + self.id_card_no[-4:] if self.id_card_no else None,
            'transfer_no': self.transfer_no,
            'source_unit': self.source_unit,
            'target_unit': self.target_unit,
            'issuer': self.issuer,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'attachment_id': self.attachment_id,
            'matched_user_id': self.matched_user_id,
            'operator_id': self.operator_id,
            'status': self.status,
            'confidence': self.confidence,
            'ocr_engine': self.ocr_engine,
            'remark': self.remark,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_raw:
            d['raw_text'] = self.raw_text
        return d

    def is_valid_on(self, check_date: date = None) -> bool:
        """检查调令在指定日期是否有效"""
        if self.status != 'active':
            return False
        if check_date is None:
            check_date = date.today()
        return self.start_date <= check_date <= self.end_date
