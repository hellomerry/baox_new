"""
项目服务（T4）
- 创建项目
- 绑定主审财务
- 列出可用项目
"""
import json
from datetime import date
from models import db
from models.models import ExpenseProject, UserProject, AuditLog, SysUser


class ProjectService:

    @staticmethod
    def create_project(operator_id: int, project_data: dict) -> tuple:
        """创建项目"""
        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'finance':
            return False, '仅财务可创建项目', None

        project_code = project_data.get('project_code')
        if not project_code:
            return False, 'project_code 必填', None

        if ExpenseProject.query.filter_by(project_code=project_code).first():
            return False, f'项目代码 {project_code} 已存在', None

        finance_id = project_data.get('finance_auditor_id')

        project = ExpenseProject(
            project_code=project_code,
            project_name=project_data.get('project_name', ''),
            project_type=project_data.get('project_type', '普通'),
            start_date=date.fromisoformat(project_data['start_date']),
            end_date=date.fromisoformat(project_data['end_date']),
            status='active',
            finance_auditor_id=finance_id,
            created_by=operator_id,
        )
        db.session.add(project)
        db.session.commit()

        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role,
            action='CREATE_PROJECT',
            target_type='project',
            target_id=str(project.id),
            detail=json.dumps({'project_code': project_code}, ensure_ascii=False),
        )
        db.session.add(log)
        db.session.commit()

        return True, '创建成功', project

    @staticmethod
    def list_projects(operator_id: int) -> list:
        """列出所有项目（财务），或可见项目（其他角色）"""
        operator = SysUser.query.get(operator_id)
        if operator.role == 'finance':
            return ExpenseProject.query.order_by(ExpenseProject.created_at.desc()).all()

        # 其他角色：只看到 active + 自己绑定的
        if operator.role == 'reimburser':
            my_projects = [up.project_id for up in UserProject.query.filter_by(
                user_id=operator_id, status='active'
            ).all()]
            return ExpenseProject.query.filter(
                ExpenseProject.id.in_(my_projects),
                ExpenseProject.status == 'active',
            ).all()

        # 稽核员：看到自己代填的项目
        my_projects = [up.project_id for up in UserProject.query.filter_by(
            user_id=operator_id, status='active'
        ).all()]
        if not my_projects:
            return []
        return ExpenseProject.query.filter(ExpenseProject.id.in_(my_projects)).all()
