"""
人员路由（T4 + N1 解密）
"""
from flask import Blueprint, request, jsonify
from models import db
from models.models import SysUser, UserPosition, PositionLevel, AgentAuth, UserProject
from utils.decorators import login_required, get_current_user
from utils.crypto import decrypt_field
from services.user_service import UserService

users_bp = Blueprint('users', __name__)


@users_bp.route('/list')
@login_required
def list_users():
    """列出所有人员（按角色）"""
    user = get_current_user()
    role = request.args.get('role', '')

    if role:
        users = SysUser.query.filter_by(role=role, account_status='normal').all()
    else:
        users = SysUser.query.filter(SysUser.account_status == 'normal').all()

    return jsonify({
        'code': 0,
        'data': [{
            'id': u.id,
            'username': u.username,
            'real_name': u.real_name,
            'role': u.role,
            'staff_type': u.staff_type,
            'department': u.department,
            'account_status': u.account_status,
        } for u in users]
    })


@users_bp.route('/<int:user_id>')
@login_required
def get_user(user_id):
    """人员详情"""
    u = SysUser.query.get(user_id)
    if not u:
        return jsonify({'code': 1, 'message': '人员不存在'}), 404

    # 岗位
    pos = UserPosition.query.filter_by(user_id=user_id).order_by(UserPosition.effective_date.desc()).first()
    level_name = pos.position.level_name if pos and pos.position else None

    # 项目绑定
    bindings = UserProject.query.filter_by(user_id=user_id, status='active').all()

    return jsonify({
        'code': 0,
        'data': {
            'id': u.id,
            'username': u.username,
            'real_name': u.real_name,
            'role': u.role,
            'staff_type': u.staff_type,
            'department': u.department,
            'level_name': level_name,
            'account_status': u.account_status,
            'valid_start_date': u.valid_start_date.isoformat() if u.valid_start_date else None,
            'valid_end_date': u.valid_end_date.isoformat() if u.valid_end_date else None,
            'project_ids': [b.project_id for b in bindings],
            'must_change_password': len(u.password_hash) == 32,  # MD5 = 32 字符
            'phone': decrypt_field(u.phone) if u.phone else None,
            'id_card': decrypt_field(u.id_card) if u.id_card else None,
            'bank_card': decrypt_field(u.bank_card) if u.bank_card else None,
        }
    })


@users_bp.route('/create', methods=['POST'])
@login_required
def create_user():
    """创建人员（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可创建人员'}), 403

    data = request.get_json() or {}
    ok, msg, new_user = UserService.create_user(user.id, data)
    return jsonify({
        'code': 0 if ok else 1,
        'message': msg,
        'data': {'id': new_user.id} if new_user else None,
    })


@users_bp.route('/bind-auditor', methods=['POST'])
@login_required
def bind_auditor():
    """绑定报销人 ↔ 稽核员 ↔ 项目（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可绑定'}), 403

    data = request.get_json() or {}
    ok, msg = UserService.bind_auditor(
        user.id,
        data['reimburser_id'],
        data['auditor_id'],
        data['project_id'],
    )
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@users_bp.route('/assign-position', methods=['POST'])
@login_required
def assign_position():
    """分配职务级别（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可分配'}), 403

    data = request.get_json() or {}
    ok, msg = UserService.assign_position(data['user_id'], data['position_id'])
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@users_bp.route('/positions')
@login_required
def list_positions():
    """列出所有职务级别"""
    positions = PositionLevel.query.order_by(PositionLevel.id.asc()).all()
    return jsonify({
        'code': 0,
        'data': [{
            'id': p.id,
            'level_code': p.level_code,
            'level_name': p.level_name,
            'description': p.description,
        } for p in positions]
    })


@users_bp.route('/<int:user_id>/same-natural')
@login_required
def same_natural_person(user_id):
    """查同一自然人的所有账号（C4 决策）"""
    from services.natural_person_service import find_same_natural_person

    user = SysUser.query.get(user_id)
    if not user or not user.natural_person_key:
        return jsonify({'code': 0, 'data': []})

    same = find_same_natural_person(user.natural_person_key, exclude_user_id=user_id)
    return jsonify({
        'code': 0,
        'data': [{
            'id': u.id,
            'username': u.username,
            'real_name': u.real_name,
            'role': u.role,
            'staff_type': u.staff_type,
        } for u in same]
    })


@users_bp.route('/my-auditor')
@login_required
def my_auditor():
    """报销人查询自己的稽核员（按项目）"""
    user = get_current_user()
    bindings = AgentAuth.query.filter_by(be_agent_id=user.id, status='active').all()
    return jsonify({
        'code': 0,
        'data': [{
            'project_id': b.project_id,
            'auditor_id': b.agent_id,
            'auditor_name': b.agent.real_name if b.agent else None,
        } for b in bindings]
    })


@users_bp.route('/ping')
def ping():
    return jsonify({'msg': 'users blueprint ready'})
