"""
v2.8.0 — 人员调令 OCR（借调/跟班学习/实战练兵）

变更：
- 新建 personnel_transfer 表：调令信息 + OCR 元数据
- 调令类型：借调 / 跟班学习 / 实战练兵 / 其他
- 核心字段：真实姓名 + 有效期时段（start_date / end_date）
- 与 sys_user / attachment 关联
"""
revision = 'v2.8.0'
down_revision = 'v2.4.0'  # 注意：跳号了，v2.5~v2.7 没有迁移文件
branch_labels = None
depends_on = None
description = '人员调令 OCR：personnel_transfer 表 + 调令识别/绑定/列表'


def upgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        # personnel_transfer 表
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS personnel_transfer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transfer_type VARCHAR(30) NOT NULL,
                real_name VARCHAR(50) NOT NULL,
                id_card_no VARCHAR(64),
                transfer_no VARCHAR(50),
                source_unit VARCHAR(200),
                target_unit VARCHAR(200),
                issuer VARCHAR(200),
                issue_date DATE,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                attachment_id INTEGER,
                raw_text TEXT,
                confidence INTEGER NOT NULL DEFAULT 0,
                ocr_engine VARCHAR(50) NOT NULL DEFAULT 'mock',
                matched_user_id INTEGER,
                operator_id INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                remark TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(attachment_id) REFERENCES attachment(id),
                FOREIGN KEY(matched_user_id) REFERENCES sys_user(id),
                FOREIGN KEY(operator_id) REFERENCES sys_user(id)
            )
        """))

        # 索引
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_type ON personnel_transfer(transfer_type)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_name ON personnel_transfer(real_name)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_start ON personnel_transfer(start_date)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_end ON personnel_transfer(end_date)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_matched ON personnel_transfer(matched_user_id)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_operator ON personnel_transfer(operator_id)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_status ON personnel_transfer(status)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_pt_created ON personnel_transfer(created_at)"))

        conn.commit()


def downgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text("DROP TABLE IF EXISTS personnel_transfer"))
        conn.commit()
