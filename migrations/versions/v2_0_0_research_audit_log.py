"""
v2.0.0 — D3 决策：终审独立审计日志
- 新增 research_audit_log 表（终审专项审计）
- 区别于 audit_log（操作日志）和 finance_audit_log（财务双人会签）
"""
revision = 'v2.0.0'
down_revision = 'v1.3.0'
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    from sqlalchemy import inspect
    from models import db

    insp = inspect(db.engine)
    if 'research_audit_log' in insp.get_table_names():
        print('  [v2.0.0] research_audit_log 表已存在，跳过')
        return

    with engine.connect() as conn:
        conn.execute(db.text('''
            CREATE TABLE research_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL,
                auditor_id INTEGER NOT NULL,
                auditor_role VARCHAR(20) NOT NULL,
                action VARCHAR(50) NOT NULL,
                reason TEXT,
                original_status VARCHAR(50),
                new_status VARCHAR(50),
                ip_address VARCHAR(50),
                client_id VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bill_id) REFERENCES expense_bill(id),
                FOREIGN KEY (auditor_id) REFERENCES sys_user(id)
            )
        '''))
        conn.execute(db.text('CREATE INDEX idx_research_audit_bill ON research_audit_log(bill_id)'))
        conn.execute(db.text('CREATE INDEX idx_research_audit_auditor ON research_audit_log(auditor_id)'))
        conn.commit()
    print('  [v2.0.0] 已建 research_audit_log 表（终审独立审计）')


def downgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text('DROP TABLE IF EXISTS research_audit_log'))
        conn.commit()
    print('  [v2.0.0] 已删除 research_audit_log 表')
