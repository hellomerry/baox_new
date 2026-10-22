# 数据库迁移系统

> 类 Alembic 风格的轻量级迁移工具，按版本号顺序执行 upgrade / downgrade。

## 目录结构

```
migrations/
├── runner.py                  # 迁移管理器（核心）
├── README.md                  # 本文档
└── versions/                  # 所有迁移文件
    ├── __init__.py
    ├── v1_0_0_init.py        # 初始建表 + 预置数据
    ├── v1_1_0_add_attachment.py
    ├── v1_2_0_field_encryption.py
    ├── v1_3_0_ratelimit_config.py
    └── v2_0_0_research_audit_log.py
```

## 设计要点

- **版本号格式**：`v<major>.<minor>.<patch>`（如 `v1.2.0`）
- **链式依赖**：每个迁移声明 `down_revision` 指向前一版本
- **幂等性**：每个 upgrade 多次执行不会出错（用 `if not exists` 保护）
- **可回滚**：每个迁移提供 `downgrade()` 函数
- **执行历史**：写入 `schema_migration` 表（含耗时/状态）
- **失败恢复**：失败的迁移标记为 `failed`，下次再跑

## 用法

### 0. 首次部署（空数据库）

```bash
python migrate.py upgrade
# 自动建表 + 跑所有迁移 + 预置数据
```

### 1. 查看状态

```bash
python migrate.py status
```

输出：
```
============================================================
数据库迁移状态
============================================================
已应用: 1 个版本
当前版本: v1.0.0

待执行: 4 个版本
  - v1.1.0
  - v1.2.0
  - v1.3.0
  - v2.0.0

所有版本: 5 个
  [✓] v1.0.0  (down=None)
  [ ] v1.1.0  (down=v1.0.0)
  [ ] v1.2.0  (down=v1.1.0)
  [ ] v1.3.0  (down=v1.2.0)
  [ ] v2.0.0  (down=v1.3.0)
```

### 2. 升级到指定版本

```bash
python migrate.py upgrade v1.2.0
# 顺序跑 v1.1.0 -> v1.2.0
```

### 3. 升级到最新

```bash
python migrate.py upgrade
# 跑所有未执行的迁移
```

### 4. 降级

```bash
python migrate.py downgrade v1.0.0
# 从当前版本倒序 downgrade 到 v1.0.0
```

### 5. 查看历史

```bash
python migrate.py history
```

### 6. 当前版本

```bash
python migrate.py current
# 输出: v1.3.0
```

## 写新迁移

### 1. 命名

```
v<major>_<minor>_<patch>_<short_description>.py
```

例：`v1_4_0_add_notification_table.py`

### 2. 模板

```python
"""
v1.4.0 — 你的迁移说明
- 这次改了什么
- 影响了哪些表/字段
"""
revision = 'v1.4.0'
down_revision = 'v1.3.0'  # 前一版本
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    """升级逻辑"""
    from sqlalchemy import inspect
    from models import db

    insp = inspect(db.engine)
    if 'new_table' in insp.get_table_names():
        print('  [v1.4.0] new_table 已存在，跳过')
        return

    # 方式 1：纯 SQL（推荐用于大表/复杂变更）
    with engine.connect() as conn:
        conn.execute(db.text('''
            CREATE TABLE new_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ...
            )
        '''))
        conn.commit()

    # 方式 2：ORM（用 model 自动生成 schema）
    # from models.models import NewTable
    # NewTable.__table__.create(db.engine, checkfirst=True)

    print('  [v1.4.0] 已建 new_table')


def downgrade(engine, session_factory):
    """降级逻辑"""
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text('DROP TABLE IF EXISTS new_table'))
        conn.commit()
    print('  [v1.4.0] 已删除 new_table')
```

### 3. 关键原则

| 原则 | 做法 |
|------|------|
| **幂等** | `if exists` 检查，跳过已执行部分 |
| **小步** | 一次迁移只做一件事 |
| **可逆** | `downgrade()` 必须能完整回滚 |
| **备份** | 在 `upgrade()` 开头加一句"建议先备份" |
| **不破坏数据** | 删字段前先建新字段、双写一段时间 |
| **测试** | 在测试库跑过 + downgrade 验证 |

### 4. SQLite 限制

| 限制 | 影响 |
|------|------|
| 不支持 `ALTER COLUMN` | 改字段类型需新建表 + 数据迁移 |
| 不支持 `DROP COLUMN` (老版) | SQLite 3.35+ 支持，但仍要小心 |
| 不支持 `RENAME COLUMN` (老版) | 同上 |
| 不支持事务 DDL | 部分语句会隐式 commit |

**改造大表的标准做法**：
```sql
-- 1. 改表名
ALTER TABLE old RENAME TO old_backup;

-- 2. 重建新表（用新 schema）
CREATE TABLE new (...);

-- 3. 复制数据
INSERT INTO new SELECT ... FROM old_backup;

-- 4. 验证后删备份
DROP TABLE old_backup;
```

## 与 init_db.py 的关系

| 命令 | 旧 (init_db.py) | 新 (migrate.py) |
|------|-----------------|-----------------|
| 首次部署 | `python init_db.py` | `python migrate.py upgrade` |
| 升级 | 手动改库 | `python migrate.py upgrade` |
| 降级 | 无 | `python migrate.py downgrade v1.0.0` |
| 查看版本 | 无 | `python migrate.py status` |

**init_db.py 已废弃**，保留只作向后兼容。所有新部署用 `migrate.py`。

## 与生产环境集成

### 启动时自动迁移

在 `launcher_*.py` 里加：

```python
from migrations.runner import MigrationManager

# 在 create_app 后、init_db 前
mgr = MigrationManager()
mgr.upgrade()  # 自动跑到最新
```

### 中心节点

`center_node.py` 启动时：

```python
from migrations.runner import MigrationManager
mgr = MigrationManager()
mgr.upgrade()
```

## 应急操作

### 数据库损坏

```bash
# 1. 从最近备份恢复
cp backup/2026-08-23_*_reimbursement.db reimbursement.db

# 2. 重跑迁移（幂等）
python migrate.py upgrade
```

### 迁移卡死

```bash
# 1. 检查 schema_migration 表
sqlite3 reimbursement.db "SELECT * FROM schema_migration;"

# 2. 手动标记失败的为已回滚
sqlite3 reimbursement.db "UPDATE schema_migration SET status='rolled_back' WHERE version='v1.2.0';"

# 3. 重跑
python migrate.py upgrade
```

### 想跳过某个迁移

```sql
-- 标记为已跳过（不推荐，但有时必要）
UPDATE schema_migration SET status='skipped' WHERE version='v1.2.0';
```

## 决策对应

| 决策 | 迁移 |
|------|------|
| T0 数据库 Schema | v1.0.0 |
| T5 附件上传 | v1.1.0 |
| N1 字段加密 | v1.2.0 |
| O2 限速参数化 | v1.3.0 |
| D3 终审独立审计 | v2.0.0 |
