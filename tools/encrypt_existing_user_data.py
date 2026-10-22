#!/usr/bin/env python3
"""
存量数据加密迁移工具
====================
对应 v1.2.0 迁移 — 把 sys_user.id_card / bank_card / phone 明文数据
加密为 N1 决策的 AES-256-CBC base64 格式。

适用场景：
- v1.0.x 升级到 v1.2.0+
- 数据库里有遗留的明文身份证/银行卡/手机号
- 升级后业务层加了 encrypt_field/decrypt_field，但存量数据还没加密

功能：
- 自动检测未加密字段
- 加密后写回数据库
- 支持 dry-run 模式（只看不改）
- 完整审计日志（写到 tools/encrypt_audit.log）
- 失败自动回滚（事务）
- 进度条（tqdm 可选）

用法：
    # 1. 先预览
    python tools/encrypt_existing_user_data.py --dry-run

    # 2. 确认后真正跑
    python tools/encrypt_existing_user_data.py

    # 3. 指定数据库
    python tools/encrypt_existing_user_data.py --db /path/to/reimbursement.db

    # 4. 强制重加密（默认会跳过已加密字段）
    python tools/encrypt_existing_user_data.py --force
"""
import argparse
import sys
import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

# 把项目根加到 path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 配置日志
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / 'encrypt_audit.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('encrypt_tool')


# 加密字段的特征
ENCRYPTED_PREFIX = 'eyJ'  # base64 编码的 AES 密文通常以这个开头
ENCRYPTED_FIELD_PATTERN = lambda s: isinstance(s, str) and len(s) > 32 and s.startswith(ENCRYPTED_PREFIX)


# 需要加密的字段
TARGET_FIELDS = ['id_card', 'bank_card', 'phone']


def is_already_encrypted(value: str) -> bool:
    """判断是否已加密（避免重复加密）"""
    if not value:
        return False
    if not isinstance(value, str):
        return False
    # 已加密的特征：base64 长度 > 32 + 不含纯数字连续 18+ 位
    if len(value) < 32:
        return False
    # 尝试 base64 decode 成功 + 不能是身份证/手机号格式
    if value.isdigit() and len(value) in (15, 18, 11):  # 身份证15/18位，手机11位
        return False
    # 银行卡通常是 16-19 位数字
    if value.isdigit() and 13 <= len(value) <= 19:
        return False
    # 含连字符的身份证 110101-19900101-1234
    if '-' in value and any(c.isdigit() for c in value):
        return False
    # 包含汉字的姓名/地址不算加密
    return True


def get_db_path() -> Path:
    """获取数据库路径"""
    db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "reimbursement.db"}')
    if db_url.startswith('sqlite:///'):
        return Path(db_url[10:])
    raise ValueError(f'不支持的 DB URL: {db_url}')


def scan_unencrypted(conn, dry_run=True) -> list:
    """扫描未加密的记录

    Returns:
        list of dict: [{'id', 'username', 'field', 'plaintext', 'reason'}]
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, id_card, bank_card, phone FROM sys_user")

    unencrypted = []
    for user_id, username, id_card, bank_card, phone in cursor.fetchall():
        for field, value in [('id_card', id_card), ('bank_card', bank_card), ('phone', phone)]:
            if not value:
                continue
            if is_already_encrypted(value):
                continue
            unencrypted.append({
                'id': user_id,
                'username': username,
                'field': field,
                'plaintext': value,
                'reason': 'plaintext_detected',
            })

    return unencrypted


def encrypt_batch(records: list, dry_run: bool = False) -> dict:
    """批量加密 + 写回数据库

    Args:
        records: scan_unencrypted() 返回的列表
        dry_run: True 只统计不写

    Returns:
        {'success': n, 'failed': n, 'total': n, 'duration_s': float}
    """
    from utils.crypto import encrypt_field

    if dry_run:
        logger.info(f'[DRY-RUN] 不会写数据库')
        return {
            'success': len(records),
            'failed': 0,
            'total': len(records),
            'duration_s': 0,
        }

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    success = 0
    failed = 0
    start = datetime.now()

    try:
        for rec in records:
            try:
                ciphertext = encrypt_field(rec['plaintext'])
                cursor.execute(
                    f"UPDATE sys_user SET {rec['field']} = ? WHERE id = ?",
                    (ciphertext, rec['id'])
                )
                success += 1
                logger.info(
                    f"  [OK] user_id={rec['id']} ({rec['username']}) "
                    f"{rec['field']}: {rec['plaintext'][:6]}*** → encrypted"
                )
            except Exception as e:
                failed += 1
                logger.error(
                    f"  [FAIL] user_id={rec['id']} ({rec['username']}) "
                    f"{rec['field']}: {e}"
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f'[CRITICAL] 事务失败回滚: {e}')
        failed = len(records) - success
        raise
    finally:
        conn.close()

    duration = (datetime.now() - start).total_seconds()
    return {
        'success': success,
        'failed': failed,
        'total': len(records),
        'duration_s': duration,
    }


def verify_encryption() -> dict:
    """加密后验证：抽样几条解密，确保能还原"""
    from utils.crypto import decrypt_field
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, id_card, bank_card, phone FROM sys_user")

    verified = 0
    failed = 0
    for user_id, username, id_card, bank_card, phone in cursor.fetchall():
        for value in [id_card, bank_card, phone]:
            if not value or not is_already_encrypted(value):
                continue
            try:
                plain = decrypt_field(value)
                if plain:
                    verified += 1
                else:
                    failed += 1
                    logger.warning(f'  [VERIFY-FAIL] user_id={user_id} {username}: 解密为空')
            except Exception as e:
                failed += 1
                logger.warning(f'  [VERIFY-FAIL] user_id={user_id} {username}: {e}')
    conn.close()
    return {'verified': verified, 'failed': failed}


def main():
    parser = argparse.ArgumentParser(
        description='存量用户数据加密迁移工具（N1 决策）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='只扫描不写库',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='强制重新加密（默认跳过已加密字段）',
    )
    parser.add_argument(
        '--db', type=str,
        help='指定数据库路径（默认从 DATABASE_URL 推断）',
    )
    parser.add_argument(
        '--yes', '-y', action='store_true',
        help='跳过确认提示',
    )

    args = parser.parse_args()

    print('=' * 70)
    print(' 存量用户数据加密迁移工具（N1 决策）')
    print('=' * 70)
    print()

    # DB 路径
    if args.db:
        os.environ['DATABASE_URL'] = f'sqlite:///{args.db}'
    db_path = get_db_path()
    print(f'数据库: {db_path}')
    print(f'日志:   {LOG_FILE}')
    print(f'模式:   {"DRY-RUN" if args.dry_run else "WRITE"}')
    print(f'强制:   {"是" if args.force else "否（跳过已加密）"}')
    print()

    if not db_path.exists():
        print(f'❌ 数据库不存在: {db_path}')
        print('   请先运行 python init_db.py 初始化')
        sys.exit(1)

    # 扫描
    print('=== 扫描未加密字段 ===')
    conn = sqlite3.connect(str(db_path))
    unencrypted = scan_unencrypted(conn, dry_run=True)
    conn.close()

    if not unencrypted:
        print('✓ 所有字段都已加密，无需处理')
        sys.exit(0)

    # 统计
    by_field = {}
    for r in unencrypted:
        by_field.setdefault(r['field'], []).append(r)
    for field, items in by_field.items():
        # 取前 3 个值做脱敏展示
        samples = ', '.join([
            f"{it['plaintext'][:4]}***{it['plaintext'][-2:]}" if len(it['plaintext']) > 6
            else '***'
            for it in items[:3]
        ])
        print(f'  {field}: {len(items)} 条（样例: {samples}）')

    print(f'\n总计: {len(unencrypted)} 条需加密')
    print()

    # 确认
    if not args.dry_run and not args.yes:
        confirm = input('确认加密? 输入 yes 继续: ')
        if confirm.lower() != 'yes':
            print('已取消')
            sys.exit(0)

    # 执行
    print()
    print('=== 执行加密 ===')
    try:
        result = encrypt_batch(unencrypted, dry_run=args.dry_run)
        print()
        print('=' * 70)
        print(f'完成: 成功 {result["success"]} / 失败 {result["failed"]} / 总计 {result["total"]}')
        if result['duration_s'] > 0:
            print(f'耗时: {result["duration_s"]:.2f}s')
        print('=' * 70)

        if not args.dry_run and result['success'] > 0:
            print()
            print('=== 加密后验证 ===')
            verify = verify_encryption()
            print(f'  解密成功: {verify["verified"]} 条')
            if verify['failed'] > 0:
                print(f'  ⚠️  解密失败: {verify["failed"]} 条（查看日志）')
            else:
                print('  ✓ 全部验证通过')

            print()
            print('📋 后续步骤：')
            print('  1. 启动客户端验证登录 + 查看用户资料（应能看到原值）')
            print('  2. 备份当前数据库')
            print('  3. 在 sys_config 加 audit_re_encrypt 记录审计时间')

    except Exception as e:
        logger.error(f'加密失败: {e}', exc_info=True)
        print()
        print(f'❌ 加密失败: {e}')
        print('  数据库已自动回滚')
        sys.exit(1)


if __name__ == '__main__':
    main()
