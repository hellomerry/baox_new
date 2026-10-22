"""通知 API 路由（v2.2.0）"""
from flask import Blueprint, request, jsonify, g
from services.notification_service import (
    send_notification, send_to_role,
    mark_read, mark_all_read, get_unread_count,
    list_for_user, delete_notification,
    get_template,
)
from models.models import db, Notification, NotificationTemplate, SysUser
from utils.decorators import get_current_user, role_required
require_role = lambda *r: role_required(*r)

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


# ============= 我的通知 =============

@notifications_bp.route('/list', methods=['GET'])
def list_my_notifications():
    """列出当前用户的通知"""
    user = get_current_user()
    if not user:
        return jsonify({'code': 1, 'message': '未登录'}), 401

    is_read_param = request.args.get('is_read')
    is_read = None
    if is_read_param == 'true':
        is_read = True
    elif is_read_param == 'false':
        is_read = False

    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    items = list_for_user(user.id, is_read=is_read, limit=limit, offset=offset)
    return jsonify({
        'code': 0,
        'data': [n.to_dict() for n in items],
        'unread_count': get_unread_count(user.id),
    })


@notifications_bp.route('/unread-count', methods=['GET'])
def unread_count():
    """当前用户未读数（用于顶部红点）"""
    user = get_current_user()
    if not user:
        return jsonify({'code': 1, 'message': '未登录'}), 401
    return jsonify({
        'code': 0,
        'data': {'unread_count': get_unread_count(user.id)},
    })


@notifications_bp.route('/<int:nid>/read', methods=['POST'])
def mark_one_read(nid):
    """标记单条已读"""
    user = get_current_user()
    if not user:
        return jsonify({'code': 1, 'message': '未登录'}), 401

    if mark_read(nid, user.id):
        return jsonify({'code': 0, 'message': '已标记已读'})
    return jsonify({'code': 1, 'message': '通知不存在'}), 404


@notifications_bp.route('/read-all', methods=['POST'])
def mark_all():
    """标记全部已读"""
    user = get_current_user()
    if not user:
        return jsonify({'code': 1, 'message': '未登录'}), 401

    count = mark_all_read(user.id)
    return jsonify({'code': 0, 'message': f'已标记 {count} 条', 'data': {'count': count}})


@notifications_bp.route('/<int:nid>', methods=['DELETE'])
def delete_one(nid):
    """删除单条通知"""
    user = get_current_user()
    if not user:
        return jsonify({'code': 1, 'message': '未登录'}), 401

    if delete_notification(nid, user.id):
        return jsonify({'code': 0, 'message': '已删除'})
    return jsonify({'code': 1, 'message': '通知不存在'}), 404


# ============= 发送通知（财务/稽核员/管理员） =============

@notifications_bp.route('/send', methods=['POST'])
@role_required('finance', 'auditor', 'admin')
def send():
    """发送通知给指定用户或角色"""
    user = get_current_user()
    data = request.get_json() or {}

    target_user_id = data.get('user_id')
    target_role = data.get('target_role')
    notification_type = data.get('type', 'system')
    title = data.get('title')
    content = data.get('content')
    bill_id = data.get('bill_id')
    priority = data.get('priority')
    variables = data.get('variables', {})

    if not title and not content and not get_template(notification_type):
        return jsonify({'code': 1, 'message': '缺少标题或内容'}), 400

    # 群发 vs 单发
    if target_role:
        if target_role not in ('reimburser', 'auditor', 'finance', 'admin'):
            return jsonify({'code': 1, 'message': '无效角色'}), 400
        count = send_to_role(
            role=target_role,
            notification_type=notification_type,
            title=title, content=content,
            sender_id=user.id,
            bill_id=bill_id,
            variables=variables,
        )
        return jsonify({'code': 0, 'message': f'已发送给 {count} 人', 'data': {'count': count}})

    if not target_user_id:
        return jsonify({'code': 1, 'message': '缺少接收人'}), 400

    target = SysUser.query.get(target_user_id)
    if not target:
        return jsonify({'code': 1, 'message': '接收人不存在'}), 404

    # 不能给自己发
    if target_user_id == user.id:
        return jsonify({'code': 1, 'message': '不能给自己发通知'}), 400

    n = send_notification(
        user_id=target_user_id,
        notification_type=notification_type,
        title=title, content=content,
        sender_id=user.id,
        bill_id=bill_id,
        priority=priority,
        variables=variables,
    )
    if not n:
        return jsonify({'code': 1, 'message': '发送失败'}), 500

    return jsonify({'code': 0, 'message': '已发送', 'data': n.to_dict()})


# ============= 模板管理（仅管理员） =============

@notifications_bp.route('/templates', methods=['GET'])
@role_required('admin', 'finance')
def list_templates():
    """列出所有通知模板"""
    items = NotificationTemplate.query.order_by(NotificationTemplate.type).all()
    return jsonify({
        'code': 0,
        'data': [t.to_dict() for t in items],
    })


@notifications_bp.route('/templates/<int:tid>', methods=['PUT'])
@role_required('admin', 'finance')
def update_template(tid):
    """更新模板（仅管理员）"""
    t = NotificationTemplate.query.get(tid)
    if not t:
        return jsonify({'code': 1, 'message': '模板不存在'}), 404

    data = request.get_json() or {}
    if 'title_template' in data:
        t.title_template = data['title_template'][:200]
    if 'content_template' in data:
        t.content_template = data['content_template']
    if 'default_priority' in data:
        t.default_priority = data['default_priority']
    if 'enabled' in data:
        t.enabled = bool(data['enabled'])

    db.session.commit()
    return jsonify({'code': 0, 'message': '已更新', 'data': t.to_dict()})
