"""
v2.2.0 - 公告/通知系统（升级版）

变更：
- notification 加列：sender_id / bill_id / priority
- 新建 notification_template 表 + 预置 7 个模板
"""
revision = 'v2.2.0'
down_revision = 'v2.1.0'
branch_labels = None
depends_on = None
description = '公告/通知系统：扩展 notification + 模板表'


def upgrade(engine, session_factory):
    from models import db

    with engine.connect() as conn:
        # 1. 探测列是否存在
        existing = {r[1] for r in conn.execute(db.text("PRAGMA table_info(notification)")).fetchall()}

        if 'sender_id' not in existing:
            conn.execute(db.text("ALTER TABLE notification ADD COLUMN sender_id INTEGER REFERENCES sys_user(id) ON DELETE SET NULL"))
        if 'bill_id' not in existing:
            conn.execute(db.text("ALTER TABLE notification ADD COLUMN bill_id INTEGER REFERENCES expense_bill(id) ON DELETE SET NULL"))
        if 'priority' not in existing:
            conn.execute(db.text("ALTER TABLE notification ADD COLUMN priority VARCHAR(16) NOT NULL DEFAULT 'normal'"))

        # 2. 索引
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_notification_user ON notification(user_id, is_read, created_at)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_notification_bill ON notification(bill_id)"))

        # 3. 模板表
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS notification_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type VARCHAR(32) NOT NULL UNIQUE,
                title_template VARCHAR(200) NOT NULL,
                content_template TEXT NOT NULL,
                default_priority VARCHAR(16) NOT NULL DEFAULT 'normal',
                enabled BOOLEAN NOT NULL DEFAULT 1,
                description VARCHAR(500),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 4. 预置模板（7 个）
        templates = [
            ('bill_approved', '报销单已批准', '您的报销单 {bill_no}（¥{amount}）已通过财务终审，等待归档。', 'normal'),
            ('bill_rejected', '报销单被驳回', '您的报销单 {bill_no} 被{operator}驳回：{reason}。请修改后重新提交。', 'high'),
            ('bill_auditor_rejected', '报销单初审未通过', '您的报销单 {bill_no} 被稽核员驳回：{reason}。请修改后重新提交。', 'high'),
            ('bill_pending_dual', '大额报销待双签', '报销单 {bill_no}（¥{amount}）主财务已通过，等待您作为第二签人批准。', 'high'),
            ('bill_overridden', '报销单状态被强制修改', '您的报销单 {bill_no} 状态由财务强制修改为 {new_status}。原因：{reason}。', 'urgent'),
            ('bill_dual_rejected', '双签被拒绝', '您作为主财务的报销单 {bill_no} 被第二签人拒绝：{reason}。', 'urgent'),
            ('system', '系统通知', '{content}', 'normal'),
        ]
        for t_type, title, content, prio in templates:
            r = conn.execute(db.text("""
                INSERT OR IGNORE INTO notification_template
                (type, title_template, content_template, default_priority, enabled, description)
                VALUES (:t, :ti, :c, :p, 1, :d)
            """), {'t': t_type, 'ti': title, 'c': content, 'p': prio, 'd': f'预置模板：{t_type}'})

        # 立即验证
        rows = conn.execute(db.text("SELECT COUNT(*) FROM notification_template")).fetchall()
        print(f'  [v2.2.0] in-tx count = {rows}')

        conn.commit()


def downgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text("DROP TABLE IF EXISTS notification_template"))
        try:
            conn.execute(db.text("ALTER TABLE notification DROP COLUMN sender_id"))
        except Exception:
            pass
        try:
            conn.execute(db.text("ALTER TABLE notification DROP COLUMN bill_id"))
        except Exception:
            pass
        try:
            conn.execute(db.text("ALTER TABLE notification DROP COLUMN priority"))
        except Exception:
            pass
        conn.commit()
