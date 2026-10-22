"""
自然人分离服务（C4 / G1 决策）
- 自然人 key：身份证号哈希
- 检测同一自然人是否跨账号（防止用不同账号逃避自审回避）
- 自审允许，但记录自然人日志（G1 决策）
"""
import hashlib
from models import db
from models.models import SysUser, AuditLog


def compute_natural_person_key(id_card: str) -> str:
    """
    计算自然人 key（身份证 SHA256，不含末尾校验位以适应换证）
    """
    if not id_card or len(id_card) < 6:
        return ''
    # 取前 6 位 + 出生年月日（8位）+ 末 4 位，避开末尾校验位
    key = id_card[:6] + id_card[6:14] + id_card[-4:] if len(id_card) >= 18 else id_card
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def find_same_natural_person(natural_key: str, exclude_user_id: int = None) -> list:
    """
    查同一自然人的所有账号
    """
    if not natural_key:
        return []
    q = SysUser.query.filter_by(natural_person_key=natural_key)
    if exclude_user_id:
        q = q.filter(SysUser.id != exclude_user_id)
    return q.all()


def check_self_audit(creator_id: int, auditor_id: int) -> tuple:
    """
    检查自审（C4 / G1 决策）

    G1 决策：自审允许，但记录自然人日志
    返回: (is_self_audit: bool, is_same_natural: bool, message: str)
    """
    if creator_id == auditor_id:
        return True, True, '同一账号自审'

    creator = SysUser.query.get(creator_id)
    auditor = SysUser.query.get(auditor_id)

    if not creator or not auditor:
        return False, False, '人员不存在'

    # 检测同一自然人
    if (creator.natural_person_key and auditor.natural_person_key
            and creator.natural_person_key == auditor.natural_person_key):
        return True, True, '同一自然人跨账号自审'

    return False, False, '非自审'
