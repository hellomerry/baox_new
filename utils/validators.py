"""
业务校验（T4）
- 三层准入
- 状态机转换
- 金额阈值
- 防重复（K1 三态）
- 高标准计算
"""
from datetime import date
from sqlalchemy import or_, and_

from models.models import (
    SysUser, ExpenseProject, UserProject, AgentAuth, ExpenseBill,
    SysConfig, ExpenseStandard, UserPosition
)


def get_config_int(key: str, default: int) -> int:
    cfg = SysConfig.query.filter_by(config_key=key).first()
    if cfg and cfg.config_value.isdigit():
        return int(cfg.config_value)
    return default


# ============= 三层准入 =============

def check_user_validity(user: SysUser) -> tuple:
    """校验 1：人员有效性"""
    if user.account_status != 'normal':
        return False, f'人员状态异常：{user.account_status}'

    today = date.today()

    if user.valid_start_date and today < user.valid_start_date:
        return False, f'人员未到有效期（{user.valid_start_date}）'

    if user.valid_end_date and today > user.valid_end_date:
        if user.buffer_end_date and today <= user.buffer_end_date:
            pass
        else:
            return False, f'人员已过有效期（{user.valid_end_date}）'

    return True, ''


def check_user_project_bind(user_id: int, project_id: int) -> tuple:
    """校验 2：人项关联"""
    binding = UserProject.query.filter_by(
        user_id=user_id, project_id=project_id, status='active'
    ).first()
    if not binding:
        return False, '该人员未绑定到此项目'
    return True, ''


def check_project_validity(project: ExpenseProject) -> tuple:
    """校验 3：项目有效性"""
    if project.status != 'active':
        return False, f'项目状态：{project.status}'

    today = date.today()
    if today < project.start_date:
        return False, f'项目未到开始日期（{project.start_date}）'
    if today > project.end_date:
        return False, f'项目已过结束日期（{project.end_date}）'

    return True, ''


def run_three_layer_validation(user_id: int, project_id: int) -> tuple:
    """三层准入校验（总入口）"""
    user = SysUser.query.get(user_id)
    if not user:
        return False, '人员不存在'

    project = ExpenseProject.query.get(project_id)
    if not project:
        return False, '项目不存在'

    ok, msg = check_user_validity(user)
    if not ok:
        return False, f'【人员】{msg}'

    ok, msg = check_user_project_bind(user_id, project_id)
    if not ok:
        return False, f'【关联】{msg}'

    ok, msg = check_project_validity(project)
    if not ok:
        return False, f'【项目】{msg}'

    return True, ''


# ============= 状态机校验（G/L 决策） =============

def check_status_transition(from_status: str, to_status: str) -> tuple:
    """状态转换合法性"""
    allowed = {
        # G2 决策：代填 = 已审，提交后直接到财务
        'draft': ['submitted_auditor', 'submitted_finance'],
        'submitted_auditor': ['auditor_ok', 'rejected_auditor'],
        'rejected_auditor': ['submitted_auditor', 'draft'],
        'auditor_ok': ['submitted_finance'],
        'submitted_finance': ['approved', 'rejected_finance'],
        # B3 决策：驳回到稽核员
        'rejected_finance': ['submitted_auditor', 'draft', 'submitted_finance'],
        'approved': ['archived'],
        'archived': [],
    }

    if to_status not in allowed.get(from_status, []):
        return False, f'状态 {from_status} 不能转为 {to_status}'
    return True, ''


# ============= 金额阈值（B2 决策） =============

def determine_required_audit(total_amount: float) -> str:
    """
    根据金额决定需要哪种审批
    返回:
    - 'auditor_only'  : 稽核员审完即归档
    - 'finance_required' : 需财务终审
    - 'dual_sign_required' : 需双人会签
    """
    low_threshold = get_config_int('audit_threshold_low', 5000)
    high_threshold = get_config_int('audit_threshold_high', 100000)

    if total_amount < low_threshold:
        return 'auditor_only'
    elif total_amount < high_threshold:
        return 'finance_required'
    else:
        return 'dual_sign_required'


# ============= 防重复报销（K1 三态） =============

def check_duplicate_bill(user_id: int, project_id: int, start_date: date, end_date: date, exclude_bill_id: int = None) -> tuple:
    """
    K 决策：同一项目内同时段禁止；跨项目同时段允许（按高标准）
    K1 决策：三态返回 (status, message, conflicts)
    """
    query = ExpenseBill.query.filter(
        ExpenseBill.user_id == user_id,
        ExpenseBill.status.in_(['draft', 'submitted_auditor', 'auditor_ok', 'submitted_finance', 'rejected_auditor', 'rejected_finance', 'approved']),
        ExpenseBill.travel_start_date <= end_date,
        ExpenseBill.travel_end_date >= start_date,
    )
    if exclude_bill_id:
        query = query.filter(ExpenseBill.id != exclude_bill_id)

    overlapping = query.all()

    if not overlapping:
        return 'ok', '', []

    same_project = [b for b in overlapping if b.project_id == project_id]
    cross_project = [b for b in overlapping if b.project_id != project_id]

    # J1：同一项目内同时段禁止 → block
    if same_project:
        conflicts = [{
            'bill_no': b.bill_no,
            'project_id': b.project_id,
            'overlap_days': (min(end_date, b.travel_end_date) - max(start_date, b.travel_start_date)).days + 1,
        } for b in same_project]
        return 'block', f'同项目内已有同时段报销单：{same_project[0].bill_no}', conflicts

    # K1：跨项目同时段 → warning
    if cross_project:
        conflicts = [{
            'bill_no': b.bill_no,
            'project_id': b.project_id,
            'overlap_days': (min(end_date, b.travel_end_date) - max(start_date, b.travel_start_date)).days + 1,
        } for b in cross_project]
        return 'warning', f'同时段有 {len(cross_project)} 个其他项目报销，本单将按最高标准计算', conflicts

    return 'ok', '', []


# ============= 高标准（K2 决策：position_id + staff_type） =============

def get_max_standard(user_id: int, project_ids: list) -> dict:
    """
    J 决策：取所有项目标准中最高的
    K2 决策：双重条件 position_id + staff_type
    """
    user_pos = UserPosition.query.filter_by(
        user_id=user_id
    ).order_by(UserPosition.effective_date.desc()).first()

    if not user_pos:
        return {}

    user = SysUser.query.get(user_id)
    staff_type = user.staff_type if user else '在编'

    position_id = user_pos.position_id
    today = date.today()

    max_by_type = {}

    for project_id in project_ids:
        # J3：先查项目特定标准
        project_specific = ExpenseStandard.query.filter(
            ExpenseStandard.position_id == position_id,
            ExpenseStandard.staff_type == staff_type,
            ExpenseStandard.project_id == project_id,
            ExpenseStandard.valid_start <= today,
            or_(ExpenseStandard.valid_end.is_(None), ExpenseStandard.valid_end >= today)
        ).all()

        # 再查全局标准
        global_standards = ExpenseStandard.query.filter(
            ExpenseStandard.position_id == position_id,
            ExpenseStandard.staff_type == staff_type,
            ExpenseStandard.project_id.is_(None),
            ExpenseStandard.valid_start <= today,
            or_(ExpenseStandard.valid_end.is_(None), ExpenseStandard.valid_end >= today)
        ).all()

        standards = project_specific + global_standards

        for s in standards:
            if s.subsidy_type not in max_by_type or s.amount > max_by_type[s.subsidy_type].amount:
                max_by_type[s.subsidy_type] = s

    return max_by_type
