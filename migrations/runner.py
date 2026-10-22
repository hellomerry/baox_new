"""
数据库迁移管理器
====================
版本控制 + 自动顺序执行 + 可回滚

设计：
- 每个迁移是一个 .py 文件，在 versions/ 目录下
- 命名：v<major>_<minor>_<patch>_<description>.py
- 包含 upgrade() 和 downgrade() 函数
- 用 schema_migration 表记录已执行版本
- 按 down_revision 链式顺序执行

用法：
    python migrate.py status          # 查看当前版本 + 待执行
    python migrate.py upgrade         # 升级到最新
    python migrate.py upgrade v1.2.0  # 升级到指定版本
    python migrate.py downgrade v1.0.0  # 降级到指定版本（会执行中间所有 downgrade）
    python migrate.py current         # 当前版本
    python migrate.py history         # 完整历史
"""
import os
import sys
import importlib
from pathlib import Path
from datetime import datetime

# 把项目根加到 path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import inspect, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from config import Config
from models import db


MIGRATIONS_DIR = Path(__file__).parent / 'versions'
MIGRATION_TABLE = 'schema_migration'


class MigrationManager:
    """迁移管理器"""

    def __init__(self):
        self.app = None
        self._ensure_app()
        self.versions = self._load_versions()

    def _ensure_app(self):
        """确保 Flask app + db 已初始化"""
        from flask import Flask
        self.app = Flask(__name__)
        self.app.config.from_object(Config)
        db.init_app(self.app)
        # 在 app context 里推一下，让 SQLAlchemy 引擎初始化
        with self.app.app_context():
            self._engine = db.engine  # 缓存 engine 引用
        self.engine = self._engine
        self.SessionFactory = sessionmaker(bind=self.engine)
        with self.app.app_context():
            self.Session = scoped_session(self.SessionFactory)
            self._ctx_session = self.Session()

    def _ensure_migration_table(self):
        """确保 schema_migration 表存在"""
        insp = inspect(self.engine)
        if MIGRATION_TABLE in insp.get_table_names():
            return

        with self.engine.connect() as conn:
            conn.execute(db.text(f'''
                CREATE TABLE {MIGRATION_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version VARCHAR(50) UNIQUE NOT NULL,
                    description TEXT,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    execution_time_ms INTEGER,
                    status VARCHAR(20) DEFAULT 'applied',
                    down_revision VARCHAR(50)
                )
            '''))
            conn.execute(db.text(f'CREATE INDEX idx_migration_version ON {MIGRATION_TABLE}(version)'))
            conn.commit()

    def _load_versions(self):
        """加载所有迁移文件，按拓扑排序"""
        if not MIGRATIONS_DIR.exists():
            return {}

        versions = {}
        for f in MIGRATIONS_DIR.glob('v*.py'):
            if f.name == '__init__.py':
                continue
            mod_name = f'migrations.versions.{f.stem}'
            try:
                mod = importlib.import_module(mod_name)
                # 验证必需字段
                if not hasattr(mod, 'revision'):
                    print(f'⚠️ {f.name}: 缺少 revision 字段')
                    continue
                if not hasattr(mod, 'upgrade'):
                    print(f'⚠️ {f.name}: 缺少 upgrade() 函数')
                    continue
                versions[mod.revision] = {
                    'module': mod,
                    'down_revision': getattr(mod, 'down_revision', None),
                    'description': getattr(mod, 'description', ''),
                    'file': f,
                }
            except Exception as e:
                print(f'❌ 加载 {f.name} 失败: {e}')
        return versions

    def _topological_sort(self, target=None):
        """拓扑排序：返回从 head 到 target 的升级路径 / target 到 None 的降级路径"""
        if not self.versions:
            return []

        # down_revision[v] = v 的前置版本
        down_rev = {v: info['down_revision'] for v, info in self.versions.items()}
        # children[v] = 所有以 v 为前置的版本
        children = {v: [] for v in self.versions}
        for v, dr in down_rev.items():
            if dr and dr in children:
                children[dr].append(v)

        # head = 没有 child 的（即 chain 顶端）
        all_revs = set(self.versions.keys())
        heads = [v for v in all_revs if not children.get(v)]

        if target:
            if target not in all_revs:
                raise ValueError(f'未知版本: {target}')

            # BFS 找从 target 沿 down_revision 链到 root（或到任何 head 不可达节点）
            # 但升级是从 root → target，所以是反过来
            # 先 BFS 找从 target 反向沿 down_revision 走到 root
            path = []
            cur = target
            seen = set()
            while cur is not None and cur not in seen:
                path.append(cur)
                seen.add(cur)
                cur = down_rev.get(cur)
            path.reverse()  # 现在是从 root 到 target
            return path

        # 升级到最新：从 root 沿 children 走到所有 head
        # 找 root（无 down_revision 的）
        roots = [v for v, dr in down_rev.items() if dr is None]
        if not roots:
            # 没 root（异常）
            return sorted(all_revs, key=self._version_key)

        # BFS 从 root 沿 children 走
        from collections import deque
        all_reachable = set()
        queue = deque(roots)
        while queue:
            cur = queue.popleft()
            if cur in all_reachable:
                continue
            all_reachable.add(cur)
            for child in children.get(cur, []):
                if child not in all_reachable:
                    queue.append(child)

        # 按版本号排序
        reachable_sorted = sorted(all_reachable, key=self._version_key)
        applied = self.get_applied_versions()
        applied_set = set(applied)
        return [v for v in reachable_sorted if v not in applied_set]

    def _downgrade_path(self, target):
        """降级路径：从 current 到 target（要 downgrade 哪些）"""
        applied = self.get_applied_versions()
        if target not in applied:
            if target not in self.versions:
                raise ValueError(f'未知版本: {target}')
            # 目标版本未应用，无法降级到
            raise ValueError(f'目标版本 {target} 未应用，无法降级')

        # 找从 current 到 target 的链
        # current = 最后一个应用的
        current = applied[-1] if applied else None
        if current == target:
            return []

        # 从 current 沿 down_revision 走到 target
        path = []
        cur = current
        while cur != target:
            path.append(cur)
            cur = self.versions[cur]['down_revision']
            if cur is None:
                raise ValueError(f'无法从 {current} 降级到 {target}（链断了）')
        path.append(target)  # 包含 target（标记为停止点）
        return path

    def _version_key(self, v):
        """版本号排序 key: v1.0.0 -> (1, 0, 0)"""
        try:
            parts = v.lstrip('v').split('.')
            return tuple(int(p) for p in parts)
        except Exception:
            return (0, 0, 0)

    def get_applied_versions(self):
        """已应用版本（按顺序）"""
        self._ensure_migration_table()
        with self.engine.connect() as conn:
            result = conn.execute(db.text(
                f'SELECT version FROM {MIGRATION_TABLE} WHERE status="applied" ORDER BY applied_at'
            ))
            return [row[0] for row in result]

    def status(self):
        """显示状态"""
        self._ensure_migration_table()
        applied = self.get_applied_versions()
        pending = self._topological_sort()

        print('=' * 60)
        print('数据库迁移状态')
        print('=' * 60)
        print(f'已应用: {len(applied)} 个版本')
        if applied:
            current = applied[-1]
            print(f'当前版本: {current}')
        else:
            print('当前版本: 无（数据库未初始化）')

        print(f'\n待执行: {len(pending)} 个版本')
        for v in pending:
            info = self.versions.get(v, {})
            desc = info.get('description', '')
            print(f'  - {v}  {desc}')

        print(f'\n所有版本: {len(self.versions)} 个')
        for v in sorted(self.versions.keys(), key=self._version_key):
            marker = '✓' if v in applied else ' '
            info = self.versions.get(v, {})
            print(f'  [{marker}] {v}  (down={info.get("down_revision")})')

    def upgrade(self, target=None):
        """升级到 target（默认最新）"""
        self._ensure_migration_table()

        if target is None:
            # 升级到最新
            pending = self._topological_sort()
            if not pending:
                print('✓ 已是最新版本')
                return
            target = pending[-1]

        if target not in self.versions:
            raise ValueError(f'未知版本: {target}')

        # 计算升级路径
        path = self._topological_sort(target=target)
        applied = set(self.get_applied_versions())

        to_run = [v for v in path if v not in applied]
        if not to_run:
            print(f'✓ 目标版本 {target} 已应用')
            return

        print(f'开始升级: {" -> ".join(to_run)}')
        print('=' * 60)

        for version in to_run:
            self._run_upgrade(version)

        print('=' * 60)
        print(f'✅ 升级完成，当前版本: {to_run[-1]}')

    def downgrade(self, target):
        """降级到 target"""
        self._ensure_migration_table()

        path = self._downgrade_path(target)
        if not path:
            print(f'✓ 已在版本 {target}')
            return

        # path = [current, ..., target]，要 downgrade 的是 current 到 target+1
        versions_to_undo = path[:-1]  # 不含 target
        print(f'开始降级: {" -> ".join(reversed(versions_to_undo))} -> {target}')
        print('=' * 60)

        for version in reversed(versions_to_undo):
            self._run_downgrade(version)

        print('=' * 60)
        print(f'✅ 降级完成，当前版本: {target}')

    def _run_upgrade(self, version):
        info = self.versions[version]
        mod = info['module']
        desc = info.get('description', '')

        print(f'\n>>> 升级到 {version} {desc}')
        start = datetime.now()
        try:
            # 在 app context 里跑（让 model 可用）
            with self.app.app_context():
                mod.upgrade(self.engine, self.SessionFactory)
            duration = (datetime.now() - start).total_seconds() * 1000

            # 记录（如果已存在 rolled_back 记录，先删掉）
            # 用显式事务保证 DELETE + INSERT 原子
            from sqlalchemy.orm import Session
            with Session(self.engine) as session:
                # 先删旧的（无论状态）
                session.execute(db.text(
                    f'DELETE FROM {MIGRATION_TABLE} WHERE version=:v'
                ), {'v': version})
                # 再插新的
                session.execute(db.text(
                    f'''INSERT INTO {MIGRATION_TABLE} (version, description, execution_time_ms, status, down_revision)
                        VALUES (:v, :d, :t, 'applied', :dr)'''
                ), {
                    'v': version,
                    'd': desc,
                    't': int(duration),
                    'dr': info['down_revision'],
                })
                session.commit()
            print(f'✓ {version} 升级完成（{int(duration)}ms）')
        except Exception as e:
            import traceback
            print(f'❌ {version} 升级失败: {e}')
            traceback.print_exc()
            # 记录失败
            try:
                with self.engine.connect() as conn:
                    conn.execute(db.text(
                        f'''INSERT OR REPLACE INTO {MIGRATION_TABLE} (version, description, status, down_revision)
                            VALUES (:v, :d, 'failed', :dr)'''
                    ), {
                        'v': version,
                        'd': str(e),
                        'dr': info['down_revision'],
                    })
                    conn.commit()
            except Exception:
                pass
            raise

    def _run_downgrade(self, version):
        info = self.versions[version]
        mod = info['module']

        print(f'\n<<< 从 {version} 降级')
        try:
            with self.app.app_context():
                mod.downgrade(self.engine, self.SessionFactory)
            # 标记为已回滚
            with self.engine.connect() as conn:
                conn.execute(db.text(
                    f'''UPDATE {MIGRATION_TABLE} SET status='rolled_back' WHERE version=:v'''
                ), {'v': version})
                conn.commit()
            print(f'✓ {version} 降级完成')
        except Exception as e:
            import traceback
            print(f'❌ {version} 降级失败: {e}')
            traceback.print_exc()
            raise

    def current(self):
        """显示当前版本"""
        applied = self.get_applied_versions()
        if applied:
            print(applied[-1])
        else:
            print('(none)')

    def history(self):
        """完整历史"""
        self._ensure_migration_table()
        with self.engine.connect() as conn:
            result = conn.execute(db.text(
                f'SELECT version, description, applied_at, execution_time_ms, status, down_revision '
                f'FROM {MIGRATION_TABLE} ORDER BY applied_at'
            ))

            print('=' * 80)
            print(f'{"版本":<10} {"状态":<12} {"耗时(ms)":<10} {"前置":<10} {"时间"}')
            print('-' * 80)
            for row in result:
                v, d, t, ms, s, dr = row
                print(f'{v:<10} {s:<12} {ms or "-":<10} {dr or "-":<10} {t}')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    mgr = MigrationManager()

    if cmd == 'status':
        mgr.status()
    elif cmd == 'current':
        mgr.current()
    elif cmd == 'history':
        mgr.history()
    elif cmd == 'upgrade':
        target = sys.argv[2] if len(sys.argv) > 2 else None
        mgr.upgrade(target)
    elif cmd == 'downgrade':
        if len(sys.argv) < 3:
            print('用法: python migrate.py downgrade <version>')
            sys.exit(1)
        mgr.downgrade(sys.argv[2])
    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
