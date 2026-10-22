"""
考勤路由（T4 + v2.10.0 模式 C）
H 决策：考勤仅作参考
v2.10.0 模式 C：稽核员可代填考勤（基于 agent_auth 关系）
"""
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from models import db
from models.models import AttendanceRecord as Attendance, SysUser
from models.models import AttendanceRecord
from utils.decorators import login_required, get_current_user, role_required
from services.attendance_service import AttendanceService

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/list')
@login_required
def list_attendance():
    user = get_current_user()
    target_user_id = request.args.get('user_id', user.id, type=int)

    # 报销人只能查自己
    if user.role == 'reimburser' and target_user_id != user.id:
        return jsonify({'code': 1, 'message': '只能查自己的考勤'}), 403

    # 稽核员可查自己代理的报销员
    if user.role == 'auditor' and target_user_id != user.id:
        from models.models import AgentAuth
        auth = AgentAuth.query.filter_by(
            agent_id=user.id, be_agent_id=target_user_id, status='active'
        ).first()
        if not auth:
            return jsonify({'code': 1, 'message': '该报销员不在您代理范围'}), 403

    start = datetime.strptime(request.args.get('start', date.today().replace(day=1).isoformat()), '%Y-%m-%d').date()
    end = datetime.strptime(request.args.get('end', date.today().isoformat()), '%Y-%m-%d').date()

    records = AttendanceService.list_attendance(target_user_id, start, end)
    return jsonify({
        'code': 0,
        'data': [{
            'id': a.id,
            'user_id': a.user_id,
            'attendance_date': a.attendance_date.isoformat(),
            'work_hours': a.work_hours,
            'is_overnight': a.is_overnight,
            'location': a.location,
        } for a in records]
    })


@attendance_bp.route('/record', methods=['POST'])
@login_required
def record_attendance():
    """自己录考勤（报销人）"""
    user = get_current_user()
    if user.role != 'reimburser':
        return jsonify({'code': 1, 'message': '仅报销人可录入考勤'}), 403

    data = request.get_json() or {}
    # 兼容旧字段：work_hours/is_overnight/location → status/remark
    status = data.get('status', '在岗')
    remark_parts = []
    if data.get('location'):
        remark_parts.append(f"地点:{data['location']}")
    if data.get('work_hours'):
        remark_parts.append(f"工时:{data['work_hours']}h")
    if data.get('is_overnight'):
        remark_parts.append('驻场')
    remark = data.get('remark') or ' | '.join(remark_parts)

    ok, msg = AttendanceService.record_attendance(
        user_id=user.id,
        project_id=data.get('project_id', 1),  # 兼容：默认项目
        attendance_date=datetime.strptime(data['attendance_date'], '%Y-%m-%d').date(),
        status=status,
        remark=remark,
    )
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@attendance_bp.route('/record-for/<int:user_id>', methods=['POST'])
@login_required
def record_for_user(user_id):
    """稽核员代填考勤（v2.10.0 模式 C）"""
    user = get_current_user()
    if user.role != 'auditor':
        return jsonify({'code': 1, 'message': '仅稽核员可代填'}), 403

    data = request.get_json() or {}
    status = data.get('status', '在岗')
    remark_parts = []
    if data.get('location'):
        remark_parts.append(f"地点:{data['location']}")
    if data.get('work_hours'):
        remark_parts.append(f"工时:{data['work_hours']}h")
    if data.get('is_overnight'):
        remark_parts.append('驻场')
    remark = data.get('remark') or ' | '.join(remark_parts)

    ok, msg = AttendanceService.record_for_user(
        agent_id=user.id,
        be_agent_id=user_id,
        project_id=data.get('project_id', 1),
        attendance_date=datetime.strptime(data['attendance_date'], '%Y-%m-%d').date(),
        status=status,
        remark=remark,
    )
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@attendance_bp.route('/ping')
def ping():
    return jsonify({'msg': 'attendance blueprint ready'})


@attendance_bp.route('/pending', methods=['GET'])
@login_required
def list_pending():
    """列出待审考勤（稽核员视角：代理的报销员）"""
    user = get_current_user()
    if user.role == 'auditor':
        records = AttendanceService.list_pending(agent_id=user.id)
    elif user.role == 'finance':
        records = AttendanceService.list_pending()
    else:
        records = AttendanceRecord.query.filter_by(
            user_id=user.id, audit_status='pending'
        ).order_by(AttendanceRecord.attendance_date.desc()).all()
    return jsonify({
        'code': 0,
        'data': [{
            'id': a.id,
            'user_id': a.user_id,
            'attendance_date': a.attendance_date.isoformat(),
            'status': a.status,
            'remark': a.remark,
            'audit_status': a.audit_status,
            'created_by': a.created_by,
            'created_at': a.created_at.isoformat() if a.created_at else None,
        } for a in records]
    })


@attendance_bp.route('/<int:attendance_id>/audit', methods=['POST'])
@role_required('auditor')
def audit_attendance_route(attendance_id):
    """稽核员审批考勤"""
    user = get_current_user()
    data = request.get_json() or {}
    decision = data.get('decision', 'approved')
    comment = data.get('comment', '')
    ok, msg = AttendanceService.audit_attendance(
        operator_id=user.id,
        attendance_id=attendance_id,
        decision=decision,
        comment=comment,
    )
    return jsonify({'code': 0 if ok else 1, 'message': msg})
