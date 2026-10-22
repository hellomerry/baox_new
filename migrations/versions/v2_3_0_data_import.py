"""
v2.3.0 — 数据导入向导

变更：
- 新建 data_import_log 表：Excel 批量导入日志
- 预置 3 种导入类型：user / project / standard
"""
revision = 'v2.3.0'
down_revision = 'v2.2.0'
branch_labels = None
depends_on = None
description = '数据导入向导：Excel 批量导入用户/项目/标准'


def upgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        # data_import_log 表
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS data_import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_type VARCHAR(20) NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_hash VARCHAR(64) NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                total_rows INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_report TEXT,
                imported_by INTEGER NOT NULL,
                imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (imported_by) REFERENCES sys_user(id)
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_data_import_type ON data_import_log(import_type, imported_at)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_data_import_status ON data_import_log(status)"))
        conn.commit()


def downgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text("DROP TABLE IF EXISTS data_import_log"))
        conn.commit()
