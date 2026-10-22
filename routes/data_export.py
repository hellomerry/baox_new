"""数据导出路由（v2.6.0）"""
from datetime import datetime
from io import BytesIO
from flask import Blueprint, request, jsonify, send_file

from services.data_export_service import (
    export_users, export_projects, export_standards, export_bills,
)
from utils.decorators import login_required, get_current_user, role_required

data_export_bp = Blueprint('data_export', __name__, url_prefix='/api/data-export')


@data_export_bp.route('/users.xlsx')
@role_required('admin', 'finance')
def users_xlsx():
    """导出用户"""
    role = request.args.get('role')
    status = request.args.get('status', 'normal')
    xlsx = export_users(role=role, status=status)
    return send_file(
        BytesIO(xlsx),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'用户导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )


@data_export_bp.route('/projects.xlsx')
@role_required('admin', 'finance')
def projects_xlsx():
    """导出项目"""
    status = request.args.get('status')
    xlsx = export_projects(status=status)
    return send_file(
        BytesIO(xlsx),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'项目导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )


@data_export_bp.route('/standards.xlsx')
@role_required('admin', 'finance')
def standards_xlsx():
    """导出报销标准"""
    xlsx = export_standards()
    return send_file(
        BytesIO(xlsx),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'报销标准导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )


@data_export_bp.route('/bills.xlsx')
@role_required('admin', 'finance')
def bills_xlsx():
    """导出报销单（带筛选）"""
    from datetime import date
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    status = request.args.get('status')
    project_id = request.args.get('project_id', type=int)
    user_id = request.args.get('user_id', type=int)

    sd = date.fromisoformat(start) if start else None
    ed = date.fromisoformat(end) if end else None

    xlsx = export_bills(
        start_date=sd, end_date=ed, status=status,
        project_id=project_id, user_id=user_id,
    )
    return send_file(
        BytesIO(xlsx),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'报销单导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )
