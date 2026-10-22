"""
附件服务（T5 补完）
- 上传发票照片/PDF
- SHA256 校验
- 防篡改
- 与单据关联
"""
import os
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

from models import db
from models.models import ExpenseBill, Attachment


# 基础目录 = 当前文件上两级（项目根）
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = BASE_DIR / 'uploads'


ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'pdf', 'gif', 'bmp'}


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def save_attachment(file, bill_id: int, user_id: int) -> tuple:
    """
    保存附件

    :param file: FileStorage 对象
    :param bill_id: 关联报销单 ID
    :param user_id: 上传者 ID
    :return: (ok, message, attachment_id)
    """
    if not file or not file.filename:
        return False, '未选择文件', None

    if not _allowed(file.filename):
        return False, f'文件类型不支持（仅 {", ".join(ALLOWED_EXT)}）', None

    bill = ExpenseBill.query.get(bill_id)
    if not bill:
        return False, '报销单不存在', None

    # 按 bill_id 分目录
    bill_dir = UPLOAD_ROOT / f'bill_{bill_id}'
    bill_dir.mkdir(parents=True, exist_ok=True)

    # 文件名：时间戳_原文件名
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = secure_filename(file.filename)
    unique_name = f'{ts}_{uuid.uuid4().hex[:8]}_{safe_name}'
    full_path = bill_dir / unique_name

    # 写入
    file.save(str(full_path))

    # 计算 SHA256
    sha256 = hashlib.sha256()
    with open(full_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    file_hash = sha256.hexdigest()

    # 写库（存绝对路径，避免 sandbox 路径不一致）
    att = Attachment(
        bill_id=bill_id,
        file_name=safe_name,
        file_path=str(full_path),
        file_size=full_path.stat().st_size,
        file_hash=file_hash,
        mime_type=file.mimetype or 'application/octet-stream',
        uploader_id=user_id,
    )
    db.session.add(att)
    db.session.commit()

    return True, f'上传成功（{full_path.stat().st_size} 字节）', att.id


def list_attachments(bill_id: int) -> list:
    """列出某报销单的所有附件"""
    items = Attachment.query.filter_by(bill_id=bill_id).order_by(Attachment.uploaded_at.desc()).all()
    return [{
        'id': a.id,
        'file_name': a.file_name,
        'file_size': a.file_size,
        'file_hash': a.file_hash,
        'mime_type': a.mime_type,
        'uploader_id': a.uploader_id,
        'uploaded_at': a.uploaded_at.isoformat() if a.uploaded_at else None,
    } for a in items]


def verify_attachment_integrity(attachment_id: int) -> tuple:
    """校验附件完整性（重新计算 SHA256 对比）"""
    att = Attachment.query.get(attachment_id)
    if not att:
        return False, '附件不存在'

    full_path = Path(att.file_path)
    if not full_path.exists():
        return False, f'附件文件丢失：{full_path}'

    sha256 = hashlib.sha256()
    with open(full_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    actual = sha256.hexdigest()

    if actual == att.file_hash:
        return True, '完整性校验通过'
    else:
        return False, f'文件被篡改（存储哈希 {att.file_hash[:16]}... 当前 {actual[:16]}...）'
