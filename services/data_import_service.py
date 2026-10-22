"""数据导入 service（v2.3.0）

核心：把校验过的 Excel 行转成 DB 记录
- 失败行收集错误
- 整体事务回滚（部分成功 / 全失败）
"""
import json
import logging
from datetime import datetime, date
from typing import List, Dict
from werkzeug.security import generate_password_hash

from models import db
from models.models import (
    SysUser, ExpenseProject, ExpenseStandard, PositionLevel,
    DataImportLog,
)

log = logging.getLogger(__name__)


def _parse_date(val):
    """把 Excel 的日期转 date"""
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val.strip(), '%Y-%m-%d').date()
        except ValueError:
            return None
    return None


# ============= 业务导入 =============

def import_users(rows: List[Dict], operator_id: int) -> Dict:
    """导入用户

    Returns: {'success': int, 'failed': int, 'errors': [...]}
    """
    success = 0
    errors = []

    for row in rows:
        if not row.get('_valid'):
            errors.append({
                'row': row['_row'],
                'username': row.get('username'),
                'error': '; '.join(row['_errors']),
            })
            continue

        try:
            username = str(row['username']).strip()
            if SysUser.query.filter_by(username=username).first():
                errors.append({
                    'row': row['_row'],
                    'username': username,
                    'error': '用户名已存在',
                })
                continue

            password = (row.get('password') or 'NewP@ss123').strip() or 'NewP@ss123'
            u = SysUser(
                username=username,
                real_name=str(row['real_name']).strip(),
                role=str(row['role']).strip(),
                staff_type=str(row['staff_type']).strip(),
                password_hash=generate_password_hash(password),
                phone=str(row.get('phone') or '').strip() or None,
                email=str(row.get('email') or '').strip() or None,
                department=str(row.get('department') or '').strip() or None,
                account_status='normal',
                failure_count=0,
            )
            db.session.add(u)
            success += 1
        except Exception as e:
            log.exception(f'import user {row.get("username")} failed')
            errors.append({
                'row': row['_row'],
                'username': row.get('username'),
                'error': f'系统错误: {e}',
            })

    return {'success': success, 'failed': len(errors), 'errors': errors}


def import_projects(rows: List[Dict], operator_id: int) -> Dict:
    """导入项目"""
    success = 0
    errors = []

    # 缓存财务账号 → id
    fin_cache = {}
    for fin in SysUser.query.filter_by(role='finance').all():
        fin_cache[fin.username] = fin.id

    for row in rows:
        if not row.get('_valid'):
            errors.append({
                'row': row['_row'],
                'project_code': row.get('project_code'),
                'error': '; '.join(row['_errors']),
            })
            continue

        try:
            code = str(row['project_code']).strip()
            if ExpenseProject.query.filter_by(project_code=code).first():
                errors.append({
                    'row': row['_row'],
                    'project_code': code,
                    'error': '项目编码已存在',
                })
                continue

            start = _parse_date(row.get('start_date'))
            end = _parse_date(row.get('end_date'))
            if not start or not end:
                errors.append({
                    'row': row['_row'],
                    'project_code': code,
                    'error': '日期格式错误',
                })
                continue

            finance_id = None
            fin_username = row.get('finance_username')
            if fin_username:
                finance_id = fin_cache.get(str(fin_username).strip())
                if not finance_id:
                    errors.append({
                        'row': row['_row'],
                        'project_code': code,
                        'error': f'财务账号 {fin_username} 不存在',
                    })
                    continue

            p = ExpenseProject(
                project_code=code,
                project_name=str(row['project_name']).strip(),
                project_type=str(row.get('project_type') or '普通').strip(),
                start_date=start,
                end_date=end,
                status='active',
                finance_auditor_id=finance_id,
                created_by=operator_id,
            )
            db.session.add(p)
            success += 1
        except Exception as e:
            log.exception(f'import project {row.get("project_code")} failed')
            errors.append({
                'row': row['_row'],
                'project_code': row.get('project_code'),
                'error': f'系统错误: {e}',
            })

    return {'success': success, 'failed': len(errors), 'errors': errors}


def import_standards(rows: List[Dict], operator_id: int) -> Dict:
    """导入报销标准"""
    success = 0
    errors = []

    # 缓存职务等级 code → id
    pos_cache = {p.level_code: p.id for p in PositionLevel.query.all()}

    for row in rows:
        if not row.get('_valid'):
            errors.append({
                'row': row['_row'],
                'position_code': row.get('position_code'),
                'error': '; '.join(row['_errors']),
            })
            continue

        try:
            pos_code = str(row['position_code']).strip()
            pos_id = pos_cache.get(pos_code)
            if not pos_id:
                errors.append({
                    'row': row['_row'],
                    'position_code': pos_code,
                    'error': f'职务等级 {pos_code} 不存在',
                })
                continue

            staff_type = str(row['staff_type']).strip()
            sub_type = str(row['subsidy_type']).strip()
            try:
                amount = float(row['amount'])
            except (TypeError, ValueError):
                errors.append({
                    'row': row['_row'],
                    'position_code': pos_code,
                    'error': '金额格式错误',
                })
                continue

            # 查重
            existing = ExpenseStandard.query.filter_by(
                position_id=pos_id,
                staff_type=staff_type,
                subsidy_type=sub_type,
            ).first()
            if existing:
                errors.append({
                    'row': row['_row'],
                    'position_code': pos_code,
                    'error': f'{pos_code} / {staff_type} / {sub_type} 已存在',
                })
                continue

            s = ExpenseStandard(
                position_id=pos_id,
                staff_type=staff_type,
                subsidy_type=sub_type,
                amount=amount,
                valid_start=date.today(),
                remark=str(row.get('remark') or '').strip() or None,
            )
            db.session.add(s)
            success += 1
        except Exception as e:
            log.exception(f'import standard {row.get("position_code")} failed')
            errors.append({
                'row': row['_row'],
                'position_code': row.get('position_code'),
                'error': f'系统错误: {e}',
            })

    return {'success': success, 'failed': len(errors), 'errors': errors}


# ============= 入口 =============

IMPORTERS = {
    'user': import_users,
    'project': import_projects,
    'standard': import_standards,
}


def do_import(import_type: str, rows: List[Dict], operator_id: int,
              file_name: str, file_hash: str, file_size: int) -> DataImportLog:
    """统一入口：导入 + 记录日志 + 事务处理

    规则：
    - 所有 valid 行尝试导入
    - invalid 行记入 errors
    - success > 0 → commit
    - success == 0 → rollback
    """
    if import_type not in IMPORTERS:
        raise ValueError(f'未知导入类型: {import_type}')

    # 创建 log 记录（pending 状态）
    log_entry = DataImportLog(
        import_type=import_type,
        file_name=file_name,
        file_hash=file_hash,
        file_size=file_size,
        total_rows=len(rows),
        success_count=0,
        failed_count=0,
        status='pending',
        imported_by=operator_id,
    )
    db.session.add(log_entry)
    db.session.commit()

    # 调对应 importer
    importer = IMPORTERS[import_type]
    result = importer(rows, operator_id)

    # 状态判定
    total = len(rows)
    success = result['success']
    failed = result['failed']
    if success == 0 and failed == 0:
        status = 'success'  # 空文件
    elif success == 0:
        status = 'failed'
        db.session.rollback()
    elif failed == 0:
        status = 'success'
        db.session.commit()
    else:
        status = 'partial'
        db.session.commit()

    # 更新 log
    log_entry.success_count = success
    log_entry.failed_count = failed
    log_entry.status = status
    log_entry.error_report = json.dumps(result['errors'], ensure_ascii=False)
    log_entry.imported_at = datetime.now()
    db.session.commit()

    return log_entry
