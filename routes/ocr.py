"""OCR 票据识别 + 人员调令识别路由（v2.7.0 + v2.8.0 + v2.9.0 离线版）"""
import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from services.ocr_service import (
    extract_receipt_info, create_bill_from_ocr,
    extract_transfer_info, save_transfer_record,
    match_transfer_to_user, find_user_by_name,
    real_ocr,
)
from models.models import db, Attachment, PersonnelTransfer, SysUser
from utils.decorators import login_required, get_current_user, role_required

ocr_bp = Blueprint('ocr', __name__, url_prefix='/api/ocr')
log = logging.getLogger(__name__)


# ============= 票据识别 =============

@ocr_bp.route('/upload', methods=['POST'])
@login_required
def upload_receipt():
    """上传票据图片（保存 + 真实 OCR 识别）

    v2.9.0 起使用 rapidocr_onnxruntime 本地引擎，零外网依赖。

    form-data:
        file: 图片文件
    """
    user = get_current_user()
    if 'file' not in request.files:
        return jsonify({'code': 1, 'message': '请上传文件'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'code': 1, 'message': '文件名为空'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.pdf', '.bmp', '.gif'):
        return jsonify({'code': 1, 'message': f'不支持的文件格式: {ext}'}), 400

    if f.content_length and f.content_length > 10 * 1024 * 1024:
        return jsonify({'code': 1, 'message': '文件超过 10MB'}), 400

    # 保存到附件目录
    upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'receipts')
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(f.filename) or f'receipt_{datetime.now().strftime("%Y%m%d%H%M%S")}{ext}'
    file_path = os.path.join(upload_dir, safe_name)
    f.save(file_path)
    file_size = os.path.getsize(file_path)

    # 真实 OCR
    ocr = extract_receipt_info(file_path)

    # 存附件记录
    import hashlib
    with open(file_path, 'rb') as fp:
        file_hash = hashlib.sha256(fp.read()).hexdigest()

    att = Attachment(
        bill_id=0,
        file_name=safe_name,
        file_path=file_path,
        file_size=file_size,
        file_hash=file_hash,
        mime_type=f.mimetype or 'image/jpeg',
        uploader_id=user.id,
    )
    db.session.add(att)
    db.session.commit()

    return jsonify({
        'code': 0,
        'message': f'识别完成（{ocr["engine"]}，{ocr["message"]}）',
        'data': {
            'attachment_id': att.id,
            'file_name': safe_name,
            'file_size': file_size,
            'ocr': ocr,
        },
    })


@ocr_bp.route('/create-bill', methods=['POST'])
@login_required
def create_bill():
    """从 OCR 结果创建报销单草稿

    body: {ocr_data, project_id, attachment_id}
    """
    user = get_current_user()
    data = request.get_json() or {}
    ocr_data = data.get('ocr_data') or {}
    project_id = data.get('project_id')
    attachment_id = data.get('attachment_id')

    if not project_id:
        return jsonify({'code': 1, 'message': '请选择项目'}), 400

    result = create_bill_from_ocr(
        operator_id=user.id,
        project_id=project_id,
        ocr_data=ocr_data,
        attachment_id=attachment_id,
    )

    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 400

    return jsonify({
        'code': 0,
        'message': result['message'],
        'data': {
            'bill_id': result['bill_id'],
            'bill_no': result['bill_no'],
            'amount': result['amount'],
            'date': result['date'],
        },
    })


# ============= 人员调令识别（v2.8.0）============

@ocr_bp.route('/transfer/upload', methods=['POST'])
@role_required('finance', 'auditor')
def transfer_upload():
    """上传调令图片 + 真实 OCR 识别

    v2.9.0 起使用 rapidocr_onnxruntime 本地引擎，零外网依赖。
    自动提取：调令类型、真实姓名、有效期时段、单位上下文。

    form-data:
        file: 调令图片

    Returns:
        {
            'attachment_id': ...,
            'ocr': {status, engine, fields: {real_name, start_date, end_date, ...}, full_text, confidence, ...}
        }
    """
    user = get_current_user()
    if 'file' not in request.files:
        return jsonify({'code': 1, 'message': '请上传文件'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'code': 1, 'message': '文件名为空'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.pdf', '.bmp', '.gif'):
        return jsonify({'code': 1, 'message': f'不支持的文件格式: {ext}'}), 400

    if f.content_length and f.content_length > 10 * 1024 * 1024:
        return jsonify({'code': 1, 'message': '文件超过 10MB'}), 400

    # 保存到附件目录
    upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'transfers')
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(f.filename) or f'transfer_{datetime.now().strftime("%Y%m%d%H%M%S")}{ext}'
    file_path = os.path.join(upload_dir, safe_name)
    f.save(file_path)
    file_size = os.path.getsize(file_path)

    # 真实 OCR
    ocr = extract_transfer_info(file_path)

    # 存附件记录
    import hashlib
    with open(file_path, 'rb') as fp:
        file_hash = hashlib.sha256(fp.read()).hexdigest()

    att = Attachment(
        bill_id=0,
        file_name=safe_name,
        file_path=file_path,
        file_size=file_size,
        file_hash=file_hash,
        mime_type=f.mimetype or 'image/jpeg',
        uploader_id=user.id,
    )
    db.session.add(att)
    db.session.commit()

    return jsonify({
        'code': 0,
        'message': f'识别完成（{ocr["engine"]}，{ocr["message"]}）',
        'data': {
            'attachment_id': att.id,
            'file_name': safe_name,
            'file_size': file_size,
            'ocr': ocr,
        },
    })


@ocr_bp.route('/transfer/save', methods=['POST'])
@role_required('finance', 'auditor')
def transfer_save():
    """保存调令识别结果

    body: {fields: {...}, attachment_id: ..., raw_text: ...}
    """
    user = get_current_user()
    data = request.get_json() or {}
    fields = data.get('fields') or {}
    attachment_id = data.get('attachment_id')
    raw_text = data.get('raw_text') or fields.get('raw_text')

    # 如果前端没传 engine，标记为手动
    if not fields.get('ocr_engine'):
        fields['ocr_engine'] = 'manual'
    if raw_text:
        fields['raw_text'] = raw_text

    result = save_transfer_record(
        operator_id=user.id,
        fields=fields,
        attachment_id=attachment_id,
    )

    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 400

    return jsonify({
        'code': 0,
        'message': result['message'],
        'data': {'transfer_id': result['transfer_id']},
    })


@ocr_bp.route('/transfer/list', methods=['GET'])
@role_required('finance', 'auditor')
def transfer_list():
    """调令列表（支持筛选）"""
    query = PersonnelTransfer.query

    real_name = request.args.get('real_name', '').strip()
    transfer_type = request.args.get('transfer_type', '').strip()
    status = request.args.get('status', '').strip()

    if real_name:
        query = query.filter(PersonnelTransfer.real_name.like(f'%{real_name}%'))
    if transfer_type:
        query = query.filter(PersonnelTransfer.transfer_type == transfer_type)
    if status:
        query = query.filter(PersonnelTransfer.status == status)

    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    pagination = query.order_by(PersonnelTransfer.created_at.desc()).paginate(
        page=page, per_page=page_size, error_out=False
    )

    return jsonify({
        'code': 0,
        'data': {
            'items': [t.to_dict() for t in pagination.items],
            'total': pagination.total,
            'page': page,
            'page_size': page_size,
        },
    })


@ocr_bp.route('/transfer/<int:transfer_id>', methods=['GET'])
@role_required('finance', 'auditor')
def transfer_detail(transfer_id):
    """调令详情"""
    transfer = PersonnelTransfer.query.get(transfer_id)
    if not transfer:
        return jsonify({'code': 1, 'message': '调令不存在'}), 404

    d = transfer.to_dict(include_raw=True)
    # 关联用户
    if transfer.matched_user_id:
        u = SysUser.query.get(transfer.matched_user_id)
        if u:
            d['matched_user'] = {
                'id': u.id, 'username': u.username,
                'real_name': u.real_name, 'role': u.role,
            }
    # 录入人
    op = SysUser.query.get(transfer.operator_id)
    if op:
        d['operator'] = {
            'id': op.id, 'username': op.username,
            'real_name': op.real_name, 'role': op.role,
        }
    return jsonify({'code': 0, 'data': d})


@ocr_bp.route('/transfer/<int:transfer_id>/bind-user', methods=['POST'])
@role_required('finance', 'auditor')
def transfer_bind_user(transfer_id):
    """绑定调令到系统用户

    body: {user_id: ...}
    """
    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'code': 1, 'message': '请提供 user_id'}), 400

    result = match_transfer_to_user(transfer_id, int(user_id))
    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 400

    return jsonify({'code': 0, 'message': result['message']})


@ocr_bp.route('/transfer/search-user', methods=['GET'])
@role_required('finance', 'auditor')
def transfer_search_user():
    """按姓名模糊查询系统用户（用于匹配）"""
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'code': 0, 'data': []})
    users = find_user_by_name(name)
    return jsonify({'code': 0, 'data': users})


@ocr_bp.route('/transfer/<int:transfer_id>/cancel', methods=['POST'])
@role_required('finance')
def transfer_cancel(transfer_id):
    """作废调令（仅财务）"""
    transfer = PersonnelTransfer.query.get(transfer_id)
    if not transfer:
        return jsonify({'code': 1, 'message': '调令不存在'}), 404

    transfer.status = 'cancelled'
    db.session.commit()
    return jsonify({'code': 0, 'message': f'已作废 #{transfer_id}'})
