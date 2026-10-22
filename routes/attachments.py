"""
附件路由（T5 补完）
- 上传附件
- 列出附件
- 下载附件
- 校验完整性
"""
import os
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

from models import db
from models.models import Attachment, ExpenseBill
from utils.decorators import login_required, get_current_user
from services.attachment_service import save_attachment, list_attachments, verify_attachment_integrity
from config import Config

attachments_bp = Blueprint('attachments', __name__)


@attachments_bp.route('/upload/<int:bill_id>', methods=['POST'])
@login_required
def upload(bill_id):
    """上传附件到指定报销单"""
    user = get_current_user()
    if 'file' not in request.files:
        return jsonify({'code': 1, 'message': '未选择文件'}), 400

    file = request.files['file']
    ok, msg, att_id = save_attachment(file, bill_id, user.id)
    if not ok:
        return jsonify({'code': 1, 'message': msg}), 400
    return jsonify({'code': 0, 'message': msg, 'data': {'id': att_id}})


@attachments_bp.route('/list/<int:bill_id>')
@login_required
def list_attachments_route(bill_id):
    """列出某报销单的附件"""
    items = list_attachments(bill_id)
    return jsonify({'code': 0, 'data': items})


@attachments_bp.route('/<int:att_id>/download')
@login_required
def download(att_id):
    """下载附件"""
    att = Attachment.query.get(att_id)
    if not att:
        return jsonify({'code': 1, 'message': '附件不存在'}), 404

    full_path = Config.BASE_DIR / att.file_path
    if not full_path.exists():
        return jsonify({'code': 1, 'message': '文件已丢失'}), 404

    return send_file(
        str(full_path),
        mimetype=att.mime_type or 'application/octet-stream',
        as_attachment=True,
        download_name=att.file_name,
    )


@attachments_bp.route('/<int:att_id>/verify')
@login_required
def verify(att_id):
    """完整性校验"""
    ok, msg = verify_attachment_integrity(att_id)
    return jsonify({'code': 0 if ok else 1, 'message': msg, 'data': {'valid': ok}})


@attachments_bp.route('/ping')
def ping():
    return jsonify({'msg': 'attachments blueprint ready'})
