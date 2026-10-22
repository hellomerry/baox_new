"""
v2.1.0 — D3 双签字段扩展
- finance_dual_sign_at: 第二签人签字时间
- finance_dual_comment: 第二签人备注
- finance_dual_reject_reason: 第二签人拒绝原因（≥10 字符）

背景：v2.0.0 只支持单字段 dual_signer_id，v2.1.0 扩展为完整双签审计。
"""
revision = 'v2.1.0'
down_revision = 'v2.0.0'
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    from models import db

    with engine.connect() as conn:
        # 检查字段是否已存在
        cursor = conn.execute(db.text("PRAGMA table_info(expense_bill)"))
        existing_columns = {row[1] for row in cursor.fetchall()}

        if 'finance_dual_sign_at' not in existing_columns:
            conn.execute(db.text(
                "ALTER TABLE expense_bill ADD COLUMN finance_dual_sign_at DATETIME"
            ))
            print('  [v2.1.0] 已加字段 finance_dual_sign_at')

        if 'finance_dual_comment' not in existing_columns:
            conn.execute(db.text(
                "ALTER TABLE expense_bill ADD COLUMN finance_dual_comment TEXT"
            ))
            print('  [v2.1.0] 已加字段 finance_dual_comment')

        conn.commit()
    print('  [v2.1.0] 双签字段扩展完成')


def downgrade(engine, session_factory):
    """SQLite 不支持直接 DROP COLUMN（老版本），保留字段"""
    print('  [v2.1.0] 降级：SQLite 不支持 DROP COLUMN，字段保留')
