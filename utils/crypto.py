"""
加密 / 签名工具（T3 + N1 字段加密）
- SHA256 文件 / 字节
- AES-256-CBC 加解密（N1/N2 用）
- 敏感字段加解密（带 base64 编码，存数据库）
"""
import sys
# Windows GBK 兜底
for _name in ('stdout', 'stderr'):
    _stream = getattr(sys, _name, None)
    if _stream is not None:
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

import hashlib
import os
import json
import base64
from typing import Tuple, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


# ============= SHA256 =============

def sha256_file(file_path: str) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """计算字节流 SHA256"""
    return hashlib.sha256(data).hexdigest()


def sha256_dict(d: dict) -> str:
    """对字典的稳定序列化计算 SHA256（key 排序）"""
    canonical = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


# ============= AES-256-CBC 原始 =============

def aes_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-256-CBC 加密（IV 前缀）"""
    key = _ensure_32_bytes(key)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return iv + ciphertext


def aes_decrypt(encrypted: bytes, key: bytes) -> bytes:
    """AES-256-CBC 解密"""
    key = _ensure_32_bytes(key)
    iv = encrypted[:16]
    ciphertext = encrypted[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    pad_len = padded[-1]
    return padded[:-pad_len]


def _ensure_32_bytes(key: bytes) -> bytes:
    """确保 key 是 32 字节，不足用 scrypt 派生"""
    if len(key) == 32:
        return key
    kdf = Scrypt(
        salt=b'rbag-n1-salt-fixed',
        length=32,
        n=2 ** 14,
        r=8,
        p=1,
        backend=default_backend()
    )
    return kdf.derive(key)


# ============= 字段加密（N1 决策） =============

# 加密字段的密钥来源：环境变量 → 配置文件 → 默认值
_FALLBACK_KEY = b'default-dev-key-CHANGE-IN-PROD-rbag-n1-2026'


def _get_master_key() -> bytes:
    """取主密钥"""
    env_key = os.environ.get('RBAG_ENCRYPTION_KEY')
    if env_key:
        return env_key.encode('utf-8')[:32].ljust(32, b'\x00')
    return _FALLBACK_KEY


def encrypt_field(plaintext: str) -> str:
    """
    加密单个字段（N1：身份证/银行卡/手机）

    :return: base64 字符串（IV + ciphertext）
    """
    if not plaintext:
        return ''
    key = _get_master_key()
    encrypted = aes_encrypt(plaintext.encode('utf-8'), key)
    return base64.b64encode(encrypted).decode('ascii')


def decrypt_field(ciphertext: str) -> str:
    """
    解密单个字段

    :return: 明文字符串；解密失败返回空串
    """
    if not ciphertext:
        return ''
    try:
        key = _get_master_key()
        encrypted = base64.b64decode(ciphertext.encode('ascii'))
        plaintext = aes_decrypt(encrypted, key)
        return plaintext.decode('utf-8')
    except Exception:
        return ''


# ============= 测试 =============

if __name__ == '__main__':
    # 自测
    text = '110101199001011234'
    enc = encrypt_field(text)
    dec = decrypt_field(enc)
    assert dec == text, f'加解密不一致: {dec} != {text}'
    print(f'plain: {text}')
    print(f'cipher: {enc[:50]}...')
    print(f'decrypted: {dec}')
    print('✅ AES-256 字段加密自测通过')

