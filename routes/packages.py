"""
数据包路由（T3）
- /api/packages/export  导出
- /api/packages/import  导入
- /api/packages/list    列表
"""
import os
import json
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename

from models import db
from models.models import ImportLog, AuditLog
from utils.decorators import login_required, get_current_user
from utils.rbag import build_package, save_package_to_file, parse_package
from config import Config

packages_bp = Blueprint('packages', __name__)


@packages_bp.route('/export', methods=['POST'])
@login_required
def export_package():
    """
    导出数据包
    Body: {
        "package_type": "reimbursement_bill",
        "payload": {...},
        "target_role": "finance"
    }
    """
    data = request.get_json() or {}
    user = get_current_user()

    package_type = data.get('package_type')
    payload = data.get('payload', {})
    target_role = data.get('target_role', '')

    if not package_type:
        return jsonify({'code': 1, 'message': 'package_type 必填'}), 400

    # 收集附件（简化：先空着，T4 完善）
    attachments = []

    # 构建包（岗位客户端出包强制脱敏）
    package_bytes = build_package(
        package_type=package_type,
        payload=payload,
        attachments=attachments,
        creator_account=user.username,
        creator_role=user.role,
        source_client=f'{user.role}-{user.id}',
        target_role=target_role,
        desensitize=True,
    )

    # 保存到临时目录
    save_dir = str(Config.RBAG_TEMP_DIR / 'export')
    file_path = save_package_to_file(package_bytes, save_dir)

    # 解析回来拿 package_id
    parsed = parse_package(package_bytes)
    package_id = parsed['manifest']['package_id'] if parsed['valid'] else ''

    # 写操作日志
    try:
        log = AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            action='EXPORT_PACKAGE',
            target_type=package_type,
            detail=json.dumps({
                'file': os.path.basename(file_path),
                'target_role': target_role,
                'package_id': package_id,
            }, ensure_ascii=False),
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'code': 0,
        'data': {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'package_id': package_id,
            'size': len(package_bytes),
        }
    })


@packages_bp.route('/import', methods=['POST'])
@login_required
def import_package():
    """
    导入数据包
    Body: multipart/form-data with 'file' field
    """
    if 'file' not in request.files:
        return jsonify({'code': 1, 'message': '未上传文件'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.endswith('.rbag'):
        return jsonify({'code': 1, 'message': '文件必须是 .rbag 格式'}), 400

    user = get_current_user()
    package_bytes = file.read()

    # 1. 解析与校验
    parsed = parse_package(package_bytes)
    if not parsed['valid']:
        try:
            log = AuditLog(
                actor_id=user.id,
                actor_role=user.role,
                action='IMPORT_PACKAGE_FAILED',
                detail=json.dumps({'error': parsed['error']}, ensure_ascii=False),
                ip_address=request.remote_addr,
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({'code': 1, 'message': f'包校验失败: {parsed["error"]}'}), 400

    manifest = parsed['manifest']
    package_id = manifest['package_id']

    # 2. 查重
    existing = ImportLog.query.filter_by(package_id=package_id).first()
    if existing:
        return jsonify({
            'code': 1,
            'message': f'该包已导入过（{existing.imported_at}），跳过'
        }), 409

    # 3. 检查 target_role 与当前用户角色是否匹配
    target_role = manifest.get('target_role', '')
    if target_role and target_role != user.role:
        return jsonify({
            'code': 1,
            'message': f'该包目标是 {target_role}，当前用户是 {user.role}'
        }), 403

    # 4. 归档包到本地
    save_dir = str(Config.RBAG_TEMP_DIR / 'imported')
    os.makedirs(save_dir, exist_ok=True)
    safe_name = secure_filename(file.filename)
    archive_path = os.path.join(save_dir, f'{package_id}_{safe_name}')
    with open(archive_path, 'wb') as f:
        f.write(package_bytes)

    # 5. 写导入日志
    try:
        import_log = ImportLog(
            package_id=package_id,
            package_type=manifest['package_type'],
            manifest_json=json.dumps(manifest, ensure_ascii=False),
            payload_summary=json.dumps(parsed['payload'], ensure_ascii=False)[:1000],
            import_status='success',
            imported_by=user.id,
        )
        db.session.add(import_log)

        audit_log = AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            action='IMPORT_PACKAGE',
            target_type=manifest['package_type'],
            target_id=package_id,
            detail=json.dumps({
                'source_client': manifest.get('source_client', ''),
                'creator': manifest.get('creator_account', ''),
            }, ensure_ascii=False),
            ip_address=request.remote_addr,
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'code': 0,
        'data': {
            'package_id': package_id,
            'package_type': manifest['package_type'],
            'manifest': manifest,
            'payload': parsed['payload'],
            'attachment_count': len(parsed['attachments']),
        }
    })


@packages_bp.route('/list', methods=['GET'])
@login_required
def list_packages():
    """列出已导入的包"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    query = ImportLog.query.order_by(ImportLog.imported_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'code': 0,
        'data': {
            'items': [{
                'id': item.id,
                'package_id': item.package_id,
                'package_type': item.package_type,
                'import_status': item.import_status,
                'imported_at': item.imported_at.isoformat() if item.imported_at else None,
            } for item in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@packages_bp.route('/ping')
def ping():
    return jsonify({'msg': 'packages blueprint ready'})
