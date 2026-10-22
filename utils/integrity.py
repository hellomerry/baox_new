"""
数据库完整性检查（N5 决策）
启动时执行 PRAGMA integrity_check
"""
import os
import sqlite3
from typing import Tuple


def check_database_integrity(db_uri: str = None) -> Tuple[bool, str]:
    """
    启动时检查 SQLite 完整性
    
    :param db_uri: SQLAlchemy URI，如 'sqlite:///path/to/db'
    :return: (ok, message)
    """
    if not db_uri:
        from config import Config
        db_uri = Config.SQLALCHEMY_DATABASE_URI
    
    if not db_uri.startswith('sqlite:///'):
        return True, 'Not SQLite, skip'
    
    db_path = db_uri.replace('sqlite:///', '')
    if not os.path.exists(db_path):
        return False, f'数据库文件不存在: {db_path}'
    
    try:
        conn = sqlite3.connect(db_path)
        result = conn.execute('PRAGMA integrity_check').fetchone()
        conn.close()
        
        if result and result[0] == 'ok':
            return True, 'integrity OK'
        else:
            return False, f'integrity check failed: {result[0] if result else "unknown"}'
    except Exception as e:
        return False, f'integrity check exception: {e}'


def get_db_path(db_uri: str = None) -> str:
    """从 SQLAlchemy URI 提取 SQLite 文件路径"""
    if not db_uri:
        from config import Config
        db_uri = Config.SQLALCHEMY_DATABASE_URI
    
    if db_uri.startswith('sqlite:///'):
        return db_uri.replace('sqlite:///', '')
    return ''
