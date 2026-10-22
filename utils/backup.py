"""
数据库备份与恢复（M3 决策）
- 每日自动备份到 backup/ 目录
- 保留最近 30 份
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

import os
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

from config import Config


def backup_database(max_keep: int = 30) -> tuple:
    """
    备份数据库

    :return: (ok: bool, message: str, backup_path: str)
    """
    from config import BASE_DIR
    db_path = Path(Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', ''))
    if not db_path.exists():
        return False, '数据库文件不存在', None

    backup_dir = BASE_DIR / 'backup'
    backup_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'reimbursement_{ts}.db'
    backup_path = backup_dir / backup_name

    # 复制
    shutil.copy2(str(db_path), str(backup_path))

    # 校验
    src_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    dst_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    if src_hash != dst_hash:
        backup_path.unlink()
        return False, '备份校验失败（哈希不一致）', None

    # 清理旧备份
    backups = sorted(backup_dir.glob('reimbursement_*.db'), key=lambda p: p.stat().st_mtime)
    if len(backups) > max_keep:
        for old in backups[:-max_keep]:
            try:
                old.unlink()
            except Exception:
                pass

    return True, f'已备份到 {backup_path}（{backup_path.stat().st_size} 字节）', str(backup_path)


def list_backups() -> list:
    """列出所有备份"""
    from config import BASE_DIR
    backup_dir = BASE_DIR / 'backup'
    if not backup_dir.exists():
        return []
    items = []
    for p in sorted(backup_dir.glob('reimbursement_*.db'), reverse=True):
        items.append({
            'filename': p.name,
            'path': str(p),
            'size': p.stat().st_size,
            'mtime': datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        })
    return items


if __name__ == '__main__':
    ok, msg, path = backup_database()
    print(f'{"✅" if ok else "❌"} {msg}')
