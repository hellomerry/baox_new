"""
项目路由（T4）
"""
from flask import Blueprint, request, jsonify
from models import db
from models.models import ExpenseProject
from utils.decorators import login_required, get_current_user
from services.project_service import ProjectService

projects_bp = Blueprint('projects', __name__)


@projects_bp.route('/list')
@login_required
def list_projects():
    user = get_current_user()
    projects = ProjectService.list_projects(user.id)
    return jsonify({
        'code': 0,
        'data': [{
            'id': p.id,
            'project_code': p.project_code,
            'project_name': p.project_name,
            'description': p.description,
            'start_date': p.start_date.isoformat() if p.start_date else None,
            'end_date': p.end_date.isoformat() if p.end_date else None,
            'status': p.status,
            'finance_auditor_id': p.finance_auditor_id,
        } for p in projects]
    })


@projects_bp.route('/<int:project_id>')
@login_required
def get_project(project_id):
    p = ExpenseProject.query.get(project_id)
    if not p:
        return jsonify({'code': 1, 'message': '项目不存在'}), 404
    return jsonify({
        'code': 0,
        'data': {
            'id': p.id,
            'project_code': p.project_code,
            'project_name': p.project_name,
            'description': p.description,
            'start_date': p.start_date.isoformat() if p.start_date else None,
            'end_date': p.end_date.isoformat() if p.end_date else None,
            'status': p.status,
            'finance_auditor_id': p.finance_auditor_id,
            'finance_auditor_name': p.finance_auditor.real_name if p.finance_auditor else None,
        }
    })


@projects_bp.route('/create', methods=['POST'])
@login_required
def create_project():
    """创建项目

    v2.10.0 角色明确：
    - 财务（管理员）：可创建所有项目
    - 稽核员：可创建项目（v2.10.0 新增，按岗位权限）
    - 报销员：无权
    """
    user = get_current_user()
    if user.role not in ('finance', 'auditor'):
        return jsonify({'code': 1, 'message': '仅财务/稽核员可创建项目'}), 403

    data = request.get_json() or {}
    ok, msg, p = ProjectService.create_project(user.id, data)
    return jsonify({
        'code': 0 if ok else 1,
        'message': msg,
        'data': {'id': p.id, 'project_code': p.project_code} if p else None,
    })


@projects_bp.route('/ping')
def ping():
    return jsonify({'msg': 'projects blueprint ready'})
