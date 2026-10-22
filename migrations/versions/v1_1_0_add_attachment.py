"""
v1.1.0 — T5 补完新增 Attachment 表
- 单据附件（发票照片/PDF）
- SHA256 校验
"""
from datetime import datetime

revision = 'v1.1.0'
down_revision = 'v1.0.0'
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    from sqlalchemy import inspect
    from models import db
    from models.models import Attachment

    insp = inspect(db.engine)

    # 检查表是否已存在
    if 'attachment' in insp.get_table_names():
        print('  [v1.1.0] attachment 表已存在，跳过')
        return

    # 用 SQLAlchemy ORM 创建（如果 model 已定义）
    try:
        Attachment.__table__.create(db.engine, checkfirst=True)
        print('  [v1.1.0] 已建 attachment 表')
    except Exception as e:
        # ORM 失败时用 raw SQL
        print(f'  [v1.1.0] ORM 创建失败 ({e})，使用 raw SQL')
        with engine.connect() as conn:
            conn.execute(db.text('''
                CREATE TABLE attachment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bill_id INTEGER NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_hash VARCHAR(64) NOT NULL,
                    mime_type VARCHAR(100),
                    uploader_id INTEGER,
                    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bill_id) REFERENCES expense_bill(id) ON DELETE CASCADE,
                    FOREIGN KEY (uploader_id) REFERENCES sys_user(id)
                )
            '''))
            conn.execute(db.text('CREATE INDEX idx_attachment_bill ON attachment(bill_id)'))
            conn.execute(db.text('CREATE INDEX idx_attachment_hash ON attachment(file_hash)'))
            conn.commit()
        print('  [v1.1.0] 已建 attachment 表（raw SQL）')


def downgrade(engine, session_factory):
    from sqlalchemy import inspect
    from models import db

    insp = inspect(db.engine)
    if 'attachment' not in insp.get_table_names():
        print('  [v1.1.0] attachment 表不存在，跳过')
        return

    with engine.connect() as conn:
        conn.execute(db.text('DROP TABLE IF EXISTS attachment'))
        conn.commit()
    print('  [v1.1.0] 已删除 attachment 表')
