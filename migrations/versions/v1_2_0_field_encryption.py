"""
v1.2.0 — N1 决策：敏感字段加密
- sys_user.id_card / bank_card / phone 改为加密存储
- 注意：存量数据需要外部脚本处理（此迁移只处理 schema）
"""
revision = 'v1.2.0'
down_revision = 'v1.1.0'
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    """N1 加密字段升级 — SQLite 下不强制 schema 变更（已是 VARCHAR(255)）"""
    from models import db

    # 字段长度扩展 — SQLite 不支持 ALTER COLUMN，但 VARCHAR(255) 已足够
    # 这里只做记录性升级，业务层加 encrypt_field/decrypt_field 调用
    # 真正的加密在 save_user / get_user 时自动处理
    print('  [v1.2.0] N1 加密：业务层已使用 encrypt_field/decrypt_field，schema 无需变更')
    print('  [v1.2.0] 存量数据迁移请运行 tools/encrypt_existing_user_data.py')


def downgrade(engine, session_factory):
    print('  [v1.2.0] 降级：业务层恢复明文（不推荐）')
    print('  [v1.2.0] 注意：已加密数据将无法被旧版解密！')
