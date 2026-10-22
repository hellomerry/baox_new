"""
存量数据加密工具测试
"""
import os
import subprocess
import sqlite3
import pytest
import sys
from pathlib import Path

# 把 tools/ 加到 path
TOOLS_DIR = Path(__file__).resolve().parent.parent / 'tools'
BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def user_db(tmp_path):
    """临时数据库 + 几条明文数据"""
    db_path = tmp_path / 'test_encrypt.db'

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    # 建表
    cursor.execute("""
        CREATE TABLE sys_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            real_name VARCHAR(50) NOT NULL,
            role VARCHAR(20) NOT NULL,
            id_card VARCHAR(255),
            bank_card VARCHAR(255),
            phone VARCHAR(255),
            account_status VARCHAR(20) DEFAULT 'normal',
            staff_type VARCHAR(20)
        )
    """)
    # 插入明文数据
    cursor.executemany(
        """INSERT INTO sys_user
           (username, password_hash, real_name, role, id_card, bank_card, phone)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ('zhang', 'x', '张三', 'reimburser',
             '110101199001011234', '6222021234567890123', '13800138000'),
            ('li', 'x', '李四', 'reimburser',
             '320101198501055432', '6228481234567890', '13900139000'),
            ('wang', 'x', '王五', 'reimburser',
             None, None, '13700137000'),
        ]
    )
    conn.commit()
    conn.close()
    return db_path


def test_dry_run_does_not_modify(user_db, monkeypatch):
    """dry-run 模式不应修改数据库"""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{user_db}')

    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'),
         '--dry-run', '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, f'stderr: {result.stderr}'

    # 数据库应保持原样（明文）
    conn = sqlite3.connect(str(user_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id_card FROM sys_user WHERE username='zhang'")
    val = cursor.fetchone()[0]
    conn.close()
    assert val == '110101199001011234', f'明文被改了: {val}'


def test_encrypt_then_verify(user_db, monkeypatch):
    """加密后明文变成密文，再解密还原"""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{user_db}')

    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'),
         '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, f'stderr: {result.stderr}'

    # 验证：现在应该是密文（base64 长度 > 32，不等于原明文）
    conn = sqlite3.connect(str(user_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id_card, bank_card, phone FROM sys_user WHERE username='zhang'")
    idc, bank, phone = cursor.fetchone()
    conn.close()

    assert idc != '110101199001011234'
    assert bank != '6222021234567890123'
    assert phone != '13800138000'
    assert len(idc) > 32
    assert len(bank) > 32
    assert len(phone) > 32

    # 解密还原
    sys.path.insert(0, str(BASE_DIR))
    from utils.crypto import decrypt_field
    assert decrypt_field(idc) == '110101199001011234'
    assert decrypt_field(bank) == '6222021234567890123'
    assert decrypt_field(phone) == '13800138000'


def test_skip_null_values(user_db, monkeypatch):
    """空值应跳过（不报错）"""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{user_db}')

    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'),
         '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, f'stderr: {result.stderr}'

    # wang 的 id_card/bank_card 是 NULL，phone 是明文
    conn = sqlite3.connect(str(user_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id_card, bank_card, phone FROM sys_user WHERE username='wang'")
    idc, bank, phone = cursor.fetchone()
    conn.close()
    assert idc is None  # 保持 NULL
    assert bank is None
    assert phone != '13700137000'  # phone 被加密


def test_skip_already_encrypted(user_db, monkeypatch):
    """已加密的字段应跳过"""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{user_db}')

    # 先加密一次
    subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'), '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
        check=True,
    )

    # 拿到加密后的值
    conn = sqlite3.connect(str(user_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id_card FROM sys_user WHERE username='zhang'")
    encrypted_idc = cursor.fetchone()[0]
    conn.close()

    # 第二次跑
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'),
         '--dry-run', '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    assert result.returncode == 0
    assert '0 条需加密' in result.stdout or '所有字段都已加密' in result.stdout

    # 再次确认值没变
    conn = sqlite3.connect(str(user_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id_card FROM sys_user WHERE username='zhang'")
    final_idc = cursor.fetchone()[0]
    conn.close()
    assert final_idc == encrypted_idc  # 同样的密文


def test_database_not_exists(monkeypatch, tmp_path):
    """不存在的数据库应清晰报错"""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/nonexistent.db')

    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / 'encrypt_existing_user_data.py'),
         '-y'],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    assert result.returncode == 1
    assert '数据库不存在' in result.stdout or '数据库不存在' in result.stderr
