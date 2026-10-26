"""
稽核预检规则（考勤联动 + 调令校验）— 主线 ⑤⑦ 补缺
- check_attendance_for_bill：出差日期范围内考勤状态核验（人当日应在"出差"）
- check_transfer_for_bill：借调/跟班/实战练兵人员的调令有效期覆盖核验
- 预检结果为 warning 时不阻断审批流，供稽核员/财务参考并落审计日志
"""
from datetime import timedelta

from models.models import AttendanceRecord, PersonnelTransfer, SysUser

# 需要调令的人员类型（v2.8.0 PersonnelTransfer 语义）
TRANSFER_STAFF_TYPES = {'借调', '跟班', '实战练兵'}


def _date_range(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def check_attendance_for_bill(bill) -> dict:
    """考勤联动：核验报销人在出差期间每天的考勤状态

    规则：
        - 出差期间考勤全覆盖且均为「出差」（未被驳回）→ ok
        - 存在考勤但某天为非出差状态（在岗/请假/未在岗）→ warning（列明细）
        - 某些日期无考勤记录 → warning（考勤缺失天数）
    """
    if not bill.user_id or not bill.travel_start_date or not bill.travel_end_date:
        return {'rule': 'attendance', 'status': 'skip', 'message': '项目总账/日期缺失，跳过考勤核验'}

    records = AttendanceRecord.query.filter(
        AttendanceRecord.user_id == bill.user_id,
        AttendanceRecord.attendance_date >= bill.travel_start_date,
        AttendanceRecord.attendance_date <= bill.travel_end_date,
    ).all()
    by_date = {r.attendance_date: r for r in records}

    absent_days = []      # 无考勤记录
    mismatch_days = []    # 有记录但非出差 / 出差记录被驳回
    for d in _date_range(bill.travel_start_date, bill.travel_end_date):
        r = by_date.get(d)
        if r is None:
            absent_days.append(d)
        elif r.status != '出差':
            mismatch_days.append(f'{d}（{r.status}）')
        elif r.audit_status == 'rejected':
            mismatch_days.append(f'{d}（出差但考勤被驳回）')

    if not absent_days and not mismatch_days:
        return {'rule': 'attendance', 'status': 'ok', 'message': '出差期间考勤全部为出差状态'}

    parts = []
    if mismatch_days:
        shown = '、'.join(mismatch_days[:5]) + ('等' if len(mismatch_days) > 5 else '')
        parts.append(f'{len(mismatch_days)} 天考勤非出差：{shown}')
    if absent_days:
        if len(absent_days) == 1:
            parts.append(f'1 天无考勤记录（{absent_days[0]}）')
        else:
            parts.append(f'{len(absent_days)} 天无考勤记录（{absent_days[0]} 至 {absent_days[-1]}）')
    return {
        'rule': 'attendance',
        'status': 'warning',
        'message': '考勤核验异常：' + '；'.join(parts),
        'mismatch_days': mismatch_days,
        'absent_days': [str(d) for d in absent_days],
    }


def check_transfer_for_bill(bill) -> dict:
    """调令校验：借调/跟班/实战练兵人员的出差期间须被有效调令覆盖

    规则：
        - 人员类型不在调令范围 → skip
        - 存在 active 调令（按 matched_user_id 或 real_name 匹配）且
          [出差起, 出差止] ⊆ [调令 start_date, end_date] → ok
        - 有调令但不覆盖整个出差期间 / 无匹配调令 → warning
    """
    if not bill.user_id:
        return {'rule': 'transfer', 'status': 'skip', 'message': '项目总账，跳过调令核验'}

    user = SysUser.query.get(bill.user_id)
    if not user or user.staff_type not in TRANSFER_STAFF_TYPES:
        return {'rule': 'transfer', 'status': 'skip',
                'message': f'人员类型（{user.staff_type if user else "未知"}）无需调令'}

    from sqlalchemy import or_
    transfers = PersonnelTransfer.query.filter(
        PersonnelTransfer.status == 'active',
        or_(PersonnelTransfer.matched_user_id == user.id,
            PersonnelTransfer.real_name == user.real_name),
    ).order_by(PersonnelTransfer.end_date.desc()).all()

    if not transfers:
        return {'rule': 'transfer', 'status': 'warning',
                'message': f'{user.staff_type}人员未找到有效调令记录（匹配：{user.real_name}）'}

    covering = [t for t in transfers
                if t.start_date <= bill.travel_start_date and bill.travel_end_date <= t.end_date]
    if covering:
        t = covering[0]
        label = t.transfer_no or f'#{t.id}'
        return {'rule': 'transfer', 'status': 'ok',
                'message': f'调令 {label}（{t.start_date} 至 {t.end_date}）覆盖出差期间'}

    windows = '；'.join(f'{t.start_date} 至 {t.end_date}' for t in transfers[:3])
    return {'rule': 'transfer', 'status': 'warning',
            'message': f'调令有效期未覆盖出差期间（{bill.travel_start_date} 至 '
                       f'{bill.travel_end_date}），现有调令：{windows}'}


def run_prechecks(bill) -> list:
    """预检总入口：考勤联动 + 调令校验"""
    return [check_attendance_for_bill(bill), check_transfer_for_bill(bill)]


def summarize(prechecks: list) -> str:
    """把 warning 预检压缩成一句话（用于返回消息 / 审计日志）"""
    warns = [p for p in prechecks if p['status'] == 'warning']
    if not warns:
        return ''
    labels = {'attendance': '考勤联动', 'transfer': '调令校验'}
    return '；'.join(f'[{labels.get(w["rule"], w["rule"])}] {w["message"]}' for w in warns)
