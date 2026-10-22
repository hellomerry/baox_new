"""
报销标准路由（T5 补完）
- 列出所有标准
- 增删改（仅财务）
"""
from decimal import Decimal
from datetime import date
from flask import Blueprint, request, jsonify
from models import db
from models.models import ExpenseStandard, PositionLevel
from utils.decorators import login_required, get_current_user

standards_bp = Blueprint('standards', __name__)


@standards_bp.route('/list')
@login_required
def list_standards():
    """列出所有标准"""
    position_id = request.args.get('position_id', type=int)
    staff_type = request.args.get('staff_type', '')

    q = ExpenseStandard.query
    if position_id:
        q = q.filter(ExpenseStandard.position_id == position_id)
    if staff_type:
        q = q.filter(ExpenseStandard.staff_type == staff_type)

    items = q.order_by(
        ExpenseStandard.position_id, ExpenseStandard.subsidy_type
    ).all()

    # 取岗位名
    pos_ids = set(s.position_id for s in items)
    pos_map = {p.id: p for p in PositionLevel.query.filter(PositionLevel.id.in_(pos_ids)).all()} if pos_ids else {}

    return jsonify({
        'code': 0,
        'data': [{
            'id': s.id,
            'position_id': s.position_id,
            'level_name': pos_map[s.position_id].level_name if s.position_id and s.position_id in pos_map else ('全局' if s.position_id is None else f'#{s.position_id}'),
            'staff_type': s.staff_type,
            'subsidy_type': s.subsidy_type,
            'amount': float(s.amount) if s.amount else 0,
            'project_id': s.project_id,
            'valid_start': s.valid_start.isoformat() if s.valid_start else None,
            'valid_end': s.valid_end.isoformat() if s.valid_end else None,
        } for s in items]
    })


@standards_bp.route('/create', methods=['POST'])
@login_required
def create_standard():
    """新增标准（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可操作'}), 403

    data = request.get_json() or {}

    required = ['position_id', 'staff_type', 'subsidy_type', 'amount']
    for f in required:
        if f not in data:
            return jsonify({'code': 1, 'message': f'{f} 必填'}), 400

    s = ExpenseStandard(
        position_id=data['position_id'],
        staff_type=data['staff_type'],
        subsidy_type=data['subsidy_type'],
        amount=Decimal(str(data['amount'])),
        project_id=data.get('project_id'),
        valid_start=date.fromisoformat(data['valid_start']) if data.get('valid_start') else date.today(),
        valid_end=date.fromisoformat(data['valid_end']) if data.get('valid_end') else None,
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({'code': 0, 'data': {'id': s.id}, 'message': '创建成功'})


@standards_bp.route('/<int:std_id>', methods=['POST'])
@login_required
def update_standard(std_id):
    """更新标准（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可操作'}), 403

    s = ExpenseStandard.query.get(std_id)
    if not s:
        return jsonify({'code': 1, 'message': '标准不存在'}), 404

    data = request.get_json() or {}
    if 'amount' in data:
        s.amount = Decimal(str(data['amount']))
    if 'subsidy_type' in data:
        s.subsidy_type = data['subsidy_type']
    if 'valid_end' in data:
        s.valid_end = date.fromisoformat(data['valid_end']) if data['valid_end'] else None
    db.session.commit()
    return jsonify({'code': 0, 'message': '更新成功'})


@standards_bp.route('/<int:std_id>/delete', methods=['POST'])
@login_required
def delete_standard(std_id):
    """删除标准（仅财务）"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可操作'}), 403

    s = ExpenseStandard.query.get(std_id)
    if not s:
        return jsonify({'code': 1, 'message': '标准不存在'}), 404
    db.session.delete(s)
    db.session.commit()
    return jsonify({'code': 0, 'message': '已删除'})


@standards_bp.route('/ping')
def ping():
    return jsonify({'msg': 'standards blueprint ready'})
