"""应用升级路由（v2.4.0）"""
from flask import Blueprint, request, jsonify
from services.upgrade_service import (
    check_for_updates, precheck, perform_upgrade,
    get_current_version, get_latest_version,
)
from models.models import AppVersion, db
from utils.decorators import login_required, get_current_user, role_required

upgrade_bp = Blueprint('upgrade', __name__, url_prefix='/api/upgrade')


@upgrade_bp.route('/check', methods=['GET'])
@login_required
def check():
    """检查更新"""
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务/管理员可查看'}), 403
    return jsonify({'code': 0, 'data': check_for_updates()})


@upgrade_bp.route('/current', methods=['GET'])
@login_required
def current():
    """当前版本 + 最新版本"""
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务/管理员可查看'}), 403
    return jsonify({
        'code': 0,
        'data': {
            'current': get_current_version(),
            'latest': get_latest_version(),
        },
    })


@upgrade_bp.route('/list', methods=['GET'])
@login_required
def list_versions():
    """所有版本列表（不含 changelog）"""
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务/管理员可查看'}), 403
    items = AppVersion.query.order_by(AppVersion.release_date.asc()).all()
    return jsonify({
        'code': 0,
        'data': [v.to_dict(include_changelog=False) for v in items],
    })


@upgrade_bp.route('/changelog/<version>', methods=['GET'])
@login_required
def changelog(version):
    """查版本 changelog"""
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务/管理员可查看'}), 403
    v = AppVersion.query.filter_by(version=version).first()
    if not v:
        return jsonify({'code': 1, 'message': f'版本 {version} 不存在'}), 404
    return jsonify({'code': 0, 'data': v.to_dict(include_changelog=True)})


@upgrade_bp.route('/precheck', methods=['GET'])
@login_required
def pre_upgrade_check():
    """升级前预检"""
    user = get_current_user()
    if user.role not in ('finance', 'admin'):
        return jsonify({'code': 1, 'message': '仅财务/管理员可查看'}), 403
    return jsonify({'code': 0, 'data': precheck()})


@upgrade_bp.route('/perform', methods=['POST'])
@role_required('admin', 'finance')
def perform():
    """执行升级

    body: {target_version?: str}
    """
    data = request.get_json() or {}
    target = data.get('target_version')

    # 预检
    pre = precheck()
    if not pre['ok']:
        return jsonify({
            'code': 1,
            'message': '预检未通过，请先解决警告项',
            'data': pre,
        }), 400

    result = perform_upgrade(target)
    return jsonify({
        'code': 0 if result['success'] else 1,
        'message': '升级成功' if result['success'] else '升级失败',
        'data': result,
    })
