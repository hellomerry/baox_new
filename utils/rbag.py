"""
.rbag 数据包工具（T3）
- build_package 构建包
- parse_package 解析 + 校验
- save/load 文件
- 强制脱敏
"""
import json
import os
import uuid
import zipfile
import shutil
from datetime import datetime
from io import BytesIO
from typing import Tuple

from utils.crypto import sha256_bytes, sha256_file


# ============= 敏感字段脱敏（3C 决策） =============

DESENSITIZE_RULES = {
    'id_card': lambda x: x[:6] + '*' * 8 + x[-4:] if x and len(x) == 18 else '****',
    'bank_card': lambda x: '****',
    'phone': lambda x: x[:3] + '****' + x[-4:] if x and len(x) == 11 else '****',
}

SENSITIVE_FIELDS = ['id_card', 'bank_card', 'phone']


def desensitize_user_data(user_data: dict) -> dict:
    """对报销人数据进行脱敏"""
    result = dict(user_data)
    for field in SENSITIVE_FIELDS:
        if field in result and result[field]:
            v = str(result[field])
            rule = DESENSITIZE_RULES.get(field)
            if rule:
                try:
                    result[field] = rule(v)
                except Exception:
                    result[field] = '****'
    return result


def desensitize_payload(payload: dict) -> dict:
    """对完整 payload 脱敏"""
    result = dict(payload)
    if 'user_data' in result and isinstance(result['user_data'], dict):
        result['user_data'] = desensitize_user_data(result['user_data'])
    return result


# ============= 包构建 =============

def build_package(
    package_type: str,
    payload: dict,
    attachments: list = None,
    creator_account: str = '',
    creator_role: str = '',
    source_client: str = '',
    target_role: str = '',
    desensitize: bool = True,
) -> bytes:
    """
    构建 .rbag 包（返回 bytes）
    
    :param package_type: 包类型
    :param payload: 业务数据 dict
    :param attachments: [{'id': 'xxx', 'path': '...'}]
    :param creator_account: 创建者账号
    :param creator_role: 创建者角色
    :param source_client: 来源客户端标识
    :param target_role: 目标角色
    :param desensitize: 是否脱敏（岗位客户端出包必须 True）
    """
    if attachments is None:
        attachments = []

    # 1. 脱敏
    if desensitize:
        payload = desensitize_payload(payload)

    # 2. 序列化 payload
    payload_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    payload_checksum = sha256_bytes(payload_bytes)

    # 3. 构造 manifest
    manifest = {
        'package_id': str(uuid.uuid4()),
        'package_type': package_type,
        'version': '1.0',
        'created_at': datetime.now().isoformat(),
        'creator_account': creator_account,
        'creator_role': creator_role,
        'source_client': source_client,
        'target_role': target_role,
        'payload_count': 1,
        'checksum': f'sha256:{payload_checksum}',
        'encrypted': False,
        'desensitized': desensitize,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')

    # 4. 构造签名（对 manifest + payload 一起签）
    signature_input = manifest_bytes + payload_bytes
    signature = sha256_bytes(signature_input)

    # 5. 写入 zip
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', manifest_bytes)
        zf.writestr('data.json', payload_bytes)
        zf.writestr('signature.bin', signature.encode('utf-8'))

        for att in attachments:
            att_id = att.get('id', str(uuid.uuid4()))
            att_path = att.get('path')
            if att_path and os.path.exists(att_path):
                att_name = f'attachments/{att_id}_{os.path.basename(att_path)}'
                zf.write(att_path, att_name)

    buf.seek(0)
    return buf.getvalue()


def save_package_to_file(package_bytes: bytes, save_dir: str) -> str:
    """保存包到文件，返回文件路径"""
    os.makedirs(save_dir, exist_ok=True)
    seq = uuid.uuid4().hex[:6]
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'package_{seq}_{ts}.rbag'
    file_path = os.path.join(save_dir, filename)
    with open(file_path, 'wb') as f:
        f.write(package_bytes)
    return file_path


# ============= 包解析与校验 =============

class PackageVerificationError(Exception):
    """包校验失败"""
    pass


def parse_package(package_bytes: bytes) -> dict:
    """
    解析 .rbag 包
    返回: { 'manifest': {...}, 'payload': {...}, 'attachments': [...], 'valid': bool, 'error': str }
    """
    result = {
        'manifest': None,
        'payload': None,
        'attachments': [],
        'valid': False,
        'error': None,
    }

    try:
        buf = BytesIO(package_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            # 1. 读取 manifest
            if 'manifest.json' not in zf.namelist():
                raise PackageVerificationError('manifest.json 不存在')
            manifest_bytes = zf.read('manifest.json')
            manifest = json.loads(manifest_bytes.decode('utf-8'))
            result['manifest'] = manifest

            # 2. 读取 payload
            if 'data.json' not in zf.namelist():
                raise PackageVerificationError('data.json 不存在')
            payload_bytes = zf.read('data.json')
            payload = json.loads(payload_bytes.decode('utf-8'))
            result['payload'] = payload

            # 3. 校验 checksum
            expected = manifest.get('checksum', '').replace('sha256:', '')
            actual = sha256_bytes(payload_bytes)
            if expected != actual:
                raise PackageVerificationError(
                    f'data.json 校验失败：期望 {expected[:16]}... 实际 {actual[:16]}...'
                )

            # 4. 校验签名
            if 'signature.bin' not in zf.namelist():
                raise PackageVerificationError('signature.bin 不存在')
            sig_bytes = zf.read('signature.bin')
            expected_sig = sha256_bytes(manifest_bytes + payload_bytes)
            actual_sig = sig_bytes.decode('utf-8')
            if expected_sig != actual_sig:
                raise PackageVerificationError('签名校验失败，包可能被篡改')

            # 5. 提取附件
            for name in zf.namelist():
                if name.startswith('attachments/'):
                    result['attachments'].append({
                        'name': name,
                        'data': zf.read(name),
                    })

            result['valid'] = True

    except PackageVerificationError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f'解析失败: {e}'

    return result
