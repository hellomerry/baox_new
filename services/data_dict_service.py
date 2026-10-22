"""数据字典 service（v2.5.0）

每张表每列的含义 + 业务规则

数据来源：
- 表结构（从 SQLAlchemy model 反射）
- 业务说明（内置字典）
"""
import logging
from typing import Dict, List
from sqlalchemy import inspect, text
from models import db

log = logging.getLogger(__name__)


# ============= 业务说明字典 =============

# 表级说明
TABLE_DESCRIPTIONS = {
    'sys_user': '用户表。包含财务/稽核员/报销人三类账号。',
    'position_level': '职务等级表。预置 4 级（省部级/厅局级/处级/科级及以下）。',
    'user_position': '用户-职务关联表。一对多，记录用户的多个职务历史。',
    'expense_project': '项目表。每个报销单必须关联一个项目。',
    'user_project': '用户-项目关联表。报销人需绑定项目才能报销。',
    'agent_auth': '代理关系表。报销人→稽核员的代填授权。',
    'expense_bill': '报销单主表。核心业务表。',
    'expense_bill_item': '报销单明细表。一对多，按金额类型拆分。',
    'expense_standard': '报销标准表。按职务等级+人员类型+补助类型定义金额上限。',
    'attendance_record': '考勤记录表。报销人每日出勤状态。',
    'financial_control_rule': '财务控制规则表。可配置金额/考勤/重复检测规则。',
    'sys_config': '系统配置表。键值对形式存配置项。',
    'client_meta': '客户端元信息表。记录客户端类型/版本/最后在线时间。',
    'attachment': '附件表。SHA-256 去重，存储文件路径。',
    'audit_log': '操作日志表。通用审计。',
    'finance_audit_log': '财务双人会签表。',
    'research_audit_log': '终审独立审计表（D3 决策）。',
    'bill_change_log': '单据字段级修改日志（N3 决策）。',
    'error_log': '错误日志表。N4 决策。',
    'notification': '站内通知表。v2.2.0 公告/通知系统。',
    'notification_template': '通知模板表。7 个预置模板。',
    'data_import_log': '数据导入日志表。v2.3.0 数据导入向导。',
    'app_version': '应用版本表。v2.4.0 应用内升级向导。',
    'import_log': '数据包导入日志（.rbag 包）。',
    'schema_migration': '迁移记录表。',
}


# 关键字段的详细说明（按 table.column）
COLUMN_DESCRIPTIONS = {
    'sys_user.role': {'comment': '角色', 'enum': 'finance / auditor / reimburser', 'rule': '与客户端类型严格绑定'},
    'sys_user.staff_type': {'comment': '人员类型', 'enum': '在编 / 借调 / 跟班 / 实战练兵'},
    'sys_user.account_status': {'comment': '账号状态', 'enum': 'normal / locked / inactive'},
    'sys_user.natural_person_key': {'comment': '自然人标识', 'rule': 'C4 决策：身份证前6+生日8+末4 的 SHA256'},

    'expense_bill.status': {
        'comment': '单据状态',
        'enum': 'draft / submitted_auditor / auditor_ok / submitted_finance / pending_dual_sign / approved / archived / rejected_auditor / rejected_finance / red_rushed',
        'rule': '状态机驱动，转换由 check_status_transition 校验',
    },
    'expense_bill.bill_type': {'comment': '单据类型', 'enum': 'personal / project_total'},
    'expense_bill.is_agent_filled': {'comment': '是否代填', 'rule': 'G2 决策：creator_id != user_id 时为 True'},
    'expense_bill.red_rushed': {'comment': '是否已冲红', 'rule': 'L2 决策：archived/approved → 取负'},

    'expense_bill.finance_dual_signer_id': {'comment': '第二签人', 'rule': 'D3 决策：大额（≥10万）必须两人分别操作'},
    'expense_bill.finance_dual_signed': {'comment': '双签是否通过', 'rule': 'D3 决策：第二签人 approve 时设 True'},

    'expense_standard.subsidy_type': {'comment': '补助类型', 'enum': '伙食 / 住宿 / 交通 / 其他'},
    'expense_standard.amount': {'comment': '金额上限（元）'},

    'expense_project.status': {'comment': '项目状态', 'enum': 'active / closed / suspended'},
    'expense_project.finance_auditor_id': {'comment': '主审财务', 'rule': '决定该项目的财务终审人'},

    'agent_auth.status': {'comment': '代理状态', 'enum': 'active / revoked'},
    'agent_auth.auth_start_date': {'comment': '代理生效日期'},

    'audit_log.action': {'comment': '操作动作', 'examples': 'CREATE_BILL / SUBMIT_BILL / AUDITOR_APPROVE / FINAL_APPROVE / OVERRIDE_BILL'},

    'research_audit_log.action': {'comment': '终审动作', 'enum': 'override / dual_sign_request / dual_sign_approve / dual_sign_reject'},

    'notification.type': {
        'comment': '通知类型',
        'enum': 'bill_approved / bill_rejected / bill_auditor_rejected / bill_pending_dual / bill_overridden / bill_dual_rejected / system',
    },
    'notification.priority': {'comment': '优先级', 'enum': 'low / normal / high / urgent'},

    'data_import_log.import_type': {'comment': '导入类型', 'enum': 'user / project / standard'},
    'data_import_log.status': {'comment': '导入状态', 'enum': 'pending / success / partial / failed'},

    'app_version.mandatory': {'comment': '是否强制升级'},
}


# ============= 公共 API =============

def get_all_tables() -> List[Dict]:
    """列出所有表（带描述）"""
    insp = inspect(db.engine)
    table_names = insp.get_table_names()
    result = []
    for name in sorted(table_names):
        info = {
            'name': name,
            'description': TABLE_DESCRIPTIONS.get(name, '（无说明）'),
            'columns': [],
        }
        # 列信息
        for col in insp.get_columns(name):
            col_info = {
                'name': col['name'],
                'type': str(col['type']),
                'nullable': col.get('nullable', True),
                'default': str(col.get('default')) if col.get('default') is not None else None,
            }
            # 业务说明
            key = f'{name}.{col["name"]}'
            if key in COLUMN_DESCRIPTIONS:
                col_info.update(COLUMN_DESCRIPTIONS[key])
            info['columns'].append(col_info)
        # 主键
        pk = insp.get_pk_constraint(name)
        info['primary_key'] = pk.get('constrained_columns', []) if pk else []
        # 外键
        fks = insp.get_foreign_keys(name)
        info['foreign_keys'] = [
            {'columns': fk['constrained_columns'], 'ref': f"{fk['referred_table']}.{fk['referred_columns']}"}
            for fk in fks
        ]
        # 索引
        idxs = insp.get_indexes(name)
        info['indexes'] = [
            {'name': i['name'], 'columns': i['column_names'], 'unique': i.get('unique', False)}
            for i in idxs
        ]
        result.append(info)
    return result


def get_table_detail(name: str) -> Dict:
    """单表详情"""
    insp = inspect(db.engine)
    if name not in insp.get_table_names():
        return None
    info = {
        'name': name,
        'description': TABLE_DESCRIPTIONS.get(name, '（无说明）'),
    }
    info['columns'] = []
    for col in insp.get_columns(name):
        col_info = {
            'name': col['name'],
            'type': str(col['type']),
            'nullable': col.get('nullable', True),
            'default': str(col.get('default')) if col.get('default') is not None else None,
        }
        key = f'{name}.{col["name"]}'
        if key in COLUMN_DESCRIPTIONS:
            col_info.update(COLUMN_DESCRIPTIONS[key])
        info['columns'].append(col_info)

    pk = insp.get_pk_constraint(name)
    info['primary_key'] = pk.get('constrained_columns', []) if pk else []
    fks = insp.get_foreign_keys(name)
    info['foreign_keys'] = [
        {'columns': fk['constrained_columns'], 'ref': f"{fk['referred_table']}.{fk['referred_columns']}"}
        for fk in fks
    ]
    idxs = insp.get_indexes(name)
    info['indexes'] = [
        {'name': i['name'], 'columns': i['column_names'], 'unique': i.get('unique', False)}
        for i in idxs
    ]
    # 行数
    try:
        r = db.session.execute(text(f'SELECT COUNT(*) FROM {name}')).fetchone()
        info['row_count'] = r[0] if r else 0
    except Exception:
        info['row_count'] = None
    return info


def get_stats() -> Dict:
    """统计：表数 / 字段数 / 行总数"""
    insp = inspect(db.engine)
    tables = insp.get_table_names()
    total_columns = 0
    total_rows = 0
    for name in tables:
        cols = insp.get_columns(name)
        total_columns += len(cols)
        try:
            r = db.session.execute(text(f'SELECT COUNT(*) FROM {name}')).fetchone()
            total_rows += r[0] if r else 0
        except Exception:
            pass
    return {
        'table_count': len(tables),
        'column_count': total_columns,
        'row_count': total_rows,
    }
