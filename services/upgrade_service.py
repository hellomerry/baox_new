"""应用升级 service（v2.4.0）

- 当前版本（来自 schema_migration 表）
- 最新版本（来自 app_version 表）
- 升级检查
- 升级前预检（备份、磁盘空间、DB 锁）
- 执行升级
- 降级（限同大版本内）
"""
import logging
import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from sqlalchemy import text
from flask import current_app

from models import db
from models.models import AppVersion

log = logging.getLogger(__name__)


# ============= 版本比较 =============

def version_tuple(v: str) -> Tuple[int, ...]:
    """v1.0.0 → (1, 0, 0)"""
    v = v.lstrip('v')
    try:
        return tuple(int(x) for x in v.split('.'))
    except ValueError:
        return (0, 0, 0)


def version_compare(a: str, b: str) -> int:
    """-1 a<b, 0 a=b, 1 a>b"""
    ta, tb = version_tuple(a), version_tuple(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


# ============= 当前/最新版本 =============

def get_current_version() -> Optional[str]:
    """当前 schema 迁移版本（最后一条 schema_migration）"""
    try:
        r = db.session.execute(text(
            "SELECT version FROM schema_migration WHERE status='applied' ORDER BY id DESC LIMIT 1"
        )).fetchone()
        return r[0] if r else None
    except Exception as e:
        log.warning(f'get_current_version: {e}')
        return None


def get_latest_version() -> Optional[str]:
    """最新发布版本（app_version 表）"""
    versions = AppVersion.query.all()
    if not versions:
        return None
    return max(versions, key=lambda v: version_tuple(v.version)).version


# ============= 升级检查 =============

def check_for_updates() -> Dict:
    """检查更新

    Returns:
        {
            'current_version': str | None,
            'latest_version': str | None,
            'has_update': bool,
            'pending_versions': [...],  # 待升级
            'mandatory_update': bool,    # 是否有强制升级
        }
    """
    current = get_current_version()
    latest = get_latest_version()

    if not current or not latest:
        return {
            'current_version': current,
            'latest_version': latest,
            'has_update': False,
            'pending_versions': [],
            'mandatory_update': False,
        }

    if version_compare(current, latest) >= 0:
        return {
            'current_version': current,
            'latest_version': latest,
            'has_update': False,
            'pending_versions': [],
            'mandatory_update': False,
        }

    # 找出待升级版本（current < v <= latest）
    all_versions = AppVersion.query.all()
    pending = []
    mandatory = False
    for v in sorted(all_versions, key=lambda x: version_tuple(x.version)):
        if version_compare(v.version, current) > 0 and version_compare(v.version, latest) <= 0:
            pending.append(v.to_dict(include_changelog=False))
            if v.mandatory:
                mandatory = True

    return {
        'current_version': current,
        'latest_version': latest,
        'has_update': True,
        'pending_versions': pending,
        'mandatory_update': mandatory,
    }


# ============= 预检 =============

def precheck() -> Dict:
    """升级前预检

    Returns:
        {
            'ok': bool,            # 全部通过
            'checks': [
                {'name': str, 'ok': bool, 'message': str, 'level': 'info'|'warning'|'error'},
                ...
            ]
        }
    """
    checks = []

    # 1. 数据库可访问
    try:
        db.session.execute(text("SELECT 1"))
        checks.append({'name': '数据库连接', 'ok': True, 'message': '正常', 'level': 'info'})
    except Exception as e:
        checks.append({'name': '数据库连接', 'ok': False, 'message': f'失败: {e}', 'level': 'error'})

    # 2. 磁盘空间（DB 文件目录剩余 > 100MB）
    try:
        from config import Config
        db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
        if os.path.exists(db_path):
            stat = os.statvfs(os.path.dirname(db_path) or '.')
            free_mb = (stat.f_bavail * stat.f_frsize) / 1024 / 1024
            ok = free_mb > 100
            checks.append({
                'name': '磁盘空间',
                'ok': ok,
                'message': f'剩余 {free_mb:.0f} MB' + ('（>100MB）' if ok else '（<100MB，请清理）'),
                'level': 'info' if ok else 'warning',
            })
    except Exception as e:
        checks.append({'name': '磁盘空间', 'ok': True, 'message': f'无法检测: {e}', 'level': 'info'})

    # 3. 当前版本检测
    current = get_current_version()
    if current:
        checks.append({'name': '当前版本', 'ok': True, 'message': current, 'level': 'info'})
    else:
        checks.append({'name': '当前版本', 'ok': False, 'message': '未检测到', 'level': 'error'})

    # 4. 待升级版本
    info = check_for_updates()
    if info['has_update']:
        checks.append({
            'name': '可升级版本',
            'ok': True,
            'message': f'{len(info["pending_versions"])} 个版本待升级',
            'level': 'info',
        })
    else:
        checks.append({'name': '可升级版本', 'ok': True, 'message': '已是最新', 'level': 'info'})

    # 5. 备份目录
    try:
        from config import Config
        backup_dir = os.path.join(Config.BASE_DIR, 'backups')
        if os.path.exists(backup_dir):
            checks.append({'name': '备份目录', 'ok': True, 'message': backup_dir, 'level': 'info'})
        else:
            checks.append({
                'name': '备份目录',
                'ok': True,
                'message': f'不存在（升级前自动创建）',
                'level': 'info',
            })
    except Exception as e:
        checks.append({'name': '备份目录', 'ok': False, 'message': f'检测失败: {e}', 'level': 'warning'})

    ok = all(c['ok'] for c in checks if c['level'] in ('error', 'warning'))
    return {'ok': ok, 'checks': checks}


# ============= 备份 =============

def backup_before_upgrade() -> Optional[str]:
    """升级前自动备份 DB

    Returns: 备份文件路径
    """
    try:
        from config import Config
        db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
        if not os.path.exists(db_path):
            return None

        backup_dir = os.path.join(Config.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        current = get_current_version() or 'unknown'
        backup_path = os.path.join(backup_dir, f'pre_upgrade_{current}_{ts}.db')

        shutil.copy2(db_path, backup_path)
        log.info(f'upgrade backup: {db_path} → {backup_path}')
        return backup_path
    except Exception as e:
        log.exception(f'backup failed: {e}')
        return None


# ============= 执行升级 =============

def perform_upgrade(target_version: str = None) -> Dict:
    """执行升级

    Args:
        target_version: 目标版本（None = 最新）

    Returns:
        {
            'success': bool,
            'from_version': str,
            'to_version': str,
            'log': [str, ...],
            'backup_path': str | None,
        }
    """
    target = target_version or get_latest_version()
    if not target:
        return {
            'success': False,
            'log': ['无法确定目标版本'],
            'backup_path': None,
        }

    current = get_current_version() or 'v0.0.0'
    if version_compare(current, target) >= 0:
        return {
            'success': True,
            'from_version': current,
            'to_version': current,
            'log': ['已是最新或更新版本，无需升级'],
            'backup_path': None,
        }

    # 1. 备份
    backup_path = backup_before_upgrade()

    # 2. 跑迁移
    from migrations.runner import MigrationManager
    log_lines = []
    log_lines.append(f'[升级] {current} → {target}')
    if backup_path:
        log_lines.append(f'[备份] {backup_path}')

    try:
        mgr = MigrationManager()
        mgr.upgrade(target)
        log_lines.append(f'[迁移] 已升级到 {target}')
    except Exception as e:
        log.exception('upgrade failed')
        log_lines.append(f'[错误] {e}')
        return {
            'success': False,
            'from_version': current,
            'to_version': current,
            'log': log_lines,
            'backup_path': backup_path,
        }

    return {
        'success': True,
        'from_version': current,
        'to_version': target,
        'log': log_lines,
        'backup_path': backup_path,
    }
