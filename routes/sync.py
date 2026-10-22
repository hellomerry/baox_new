"""
同步路由（中心节点对端）
"""
from flask import Blueprint, jsonify, request
from services.sync_service import ping_center, upload_to_center, download_from_center, get_sync_status
from utils.decorators import login_required, get_current_user

sync_bp = Blueprint('sync', __name__)


@sync_bp.route('/status')
@login_required
def status():
    """当前同步状态"""
    return jsonify({'code': 0, 'data': get_sync_status()})


@sync_bp.route('/ping')
@login_required
def ping():
    """ping 中心节点"""
    ok, msg = ping_center()
    return jsonify({'code': 0 if ok else 1, 'message': msg, 'data': {'ok': ok}})


@sync_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    """上传 .rbag 到中心"""
    data = request.get_json() or {}
    file_path = data.get('file_path')
    if not file_path:
        return jsonify({'code': 1, 'message': 'file_path 必填'}), 400

    ok, msg = upload_to_center(file_path)
    return jsonify({'code': 0 if ok else 1, 'message': msg})


@sync_bp.route('/download/<package_id>', methods=['GET'])
@login_required
def download(package_id):
    """从中心下载"""
    ok, msg, data = download_from_center(package_id)
    if not ok:
        return jsonify({'code': 1, 'message': msg}), 500
    from flask import Response
    return Response(data, mimetype='application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename={package_id}.rbag'})


@sync_bp.route('/ping-public')
def ping_public():
    """公开心跳（无需登录）"""
    return jsonify({'msg': 'sync blueprint ready', 'data': get_sync_status()})
