"""
v2.11.2 — 报销标准地区档（主线④：职务等级×人员类型×地区 三维交叉）

变更：
- expense_standard 表新增 region_tier 列（VARCHAR(20)，NULL=通用/不限地区）
- 档位：tier1 直辖市/一线、tier2 省会/计划单列市、tier3 其他
- 地区特定标准按费用类型优先，缺失类型回退通用标准（region_tier IS NULL）
"""
revision = 'v2.11.2'
down_revision = 'v2.8.0'
branch_labels = None
depends_on = None
description = '报销标准地区档：expense_standard.region_tier'


def upgrade(engine, session_factory):
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE expense_standard ADD COLUMN region_tier VARCHAR(20)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_expense_standard_region "
            "ON expense_standard (region_tier)"
        ))
        conn.commit()


def downgrade(engine, session_factory):
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "DROP INDEX IF EXISTS idx_expense_standard_region"
        ))
        # SQLite 删列需重建表；region_tier 为可选列，直接保留不影响回滚后运行
        conn.commit()
