"""
数据库初始化脚本
================
新部署请用：  python migrate.py upgrade
本脚本保留 init_base_data() 函数供测试 conftest.py 使用

用法：
    python init_db.py              # 等价于 python migrate.py upgrade
    python init_db.py --force      # 强制重新初始化（先备份！）
"""
import hashlib
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask

# 绿色版修复：把脚本所在目录加进 sys.path（嵌 Python 默认 cwd 不在 path）
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from config import Config
from models import db
from models.models import (
    SysUser, ExpenseProject, UserProject, AgentAuth,
    FinancialControlRule, ExpenseBill, ExpenseBillItem,
    AttendanceRecord, PositionLevel, UserPosition,
    ImportLog, AuditLog, FinanceAuditLog, SysConfig, ClientMeta,
    Notification, BillChangeLog, ErrorLog,
    ExpenseStandard,  # K9 决策新增
    Attachment,  # T5 补完新增
    ResearchAuditLog,  # D3 决策新增
)


def create_app():
    """创建 Flask 应用（供测试 + 命令行共用）"""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def init_base_data():
    """预置基础数据（供测试与正式环境共用）

    注意：新部署的正式环境用 python migrate.py upgrade
    这里保留是为了让 tests/conftest.py 仍能快速建库
    """
    # 2. 预置 4 条职务等级（A 决策）
    positions = [
        ('PROVINCIAL', '省级职务', '省部级正职及以上'),
        ('BUREAU', '厅局级职务', '厅局级正副职'),
        ('DIVISION', '处级职务', '处级正副职'),
        ('OTHER', '其他职务', '科级及以下'),
    ]
    for code, name, desc in positions:
        if not PositionLevel.query.filter_by(level_code=code).first():
            db.session.add(PositionLevel(level_code=code, level_name=name, description=desc))
    db.session.commit()

    # 3. 预置 10 条系统配置（A 决策 + L3 决策）
    configs = [
        ('audit_threshold_low', '5000', '小额报销阈值（元），低于此值稽核员审完即归档'),
        ('audit_threshold_high', '100000', '大额报销阈值（元），≥此值需双人会签'),
        ('overdue_warn_days', '3', '超期催办天数'),
        ('overdue_escalate_days', '7', '超期升级天数'),
        ('password_min_length', '10', '密码最小长度'),
        ('login_max_failures', '5', '登录最大失败次数'),
        ('lockout_minutes', '30', '账号锁定时长（分钟）'),
        ('budget_check_mode', 'warning', '预算校验模式: block/warning/off'),
        ('center_node_host', '127.0.0.1', '中心节点地址（财务客户端）'),
        ('center_node_port', '5443', '中心节点端口'),
    ]
    for key, value, name in configs:
        if not SysConfig.query.filter_by(config_key=key).first():
            db.session.add(SysConfig(config_key=key, config_value=value, config_name=name))
    db.session.commit()

    # 4. K9 决策：预置 12 条内置报销标准
    standards = [
        (1, '在编', '伙食', 200, '省部级正副职 伙食补助'),
        (1, '在编', '住宿', 800, '省部级正副职 住宿标准'),
        (2, '在编', '伙食', 150, '厅局级正副职 伙食补助'),
        (2, '在编', '住宿', 600, '厅局级正副职 住宿标准'),
        (3, '在编', '伙食', 100, '处级正副职 伙食补助'),
        (3, '在编', '住宿', 400, '处级正副职 住宿标准'),
        (4, '在编', '伙食', 80, '科级及以下 伙食补助'),
        (4, '在编', '住宿', 300, '科级及以下 住宿标准'),
        (None, '借调', '伙食', 70, '借调人员 伙食补助'),
        (None, '借调', '住宿', 250, '借调人员 住宿标准'),
        (None, '跟班', '伙食', 60, '跟班人员 伙食补助'),
        (None, '跟班', '住宿', 200, '跟班人员 住宿标准'),
    ]
    for pos_id, staff_type, subsidy_type, amount, remark in standards:
        existing = ExpenseStandard.query.filter_by(
            position_id=pos_id, staff_type=staff_type, subsidy_type=subsidy_type
        ).first()
        if not existing:
            db.session.add(ExpenseStandard(
                position_id=pos_id,
                staff_type=staff_type,
                subsidy_type=subsidy_type,
                amount=amount,
                valid_start=datetime.now().date(),
                remark=remark,
            ))
    db.session.commit()

    # 5. 默认财务账号 admin / admin@2026
    if not SysUser.query.filter_by(username='admin').first():
        admin = SysUser(
            username='admin',
            password_hash=hashlib.md5('admin@2026'.encode()).hexdigest(),
            real_name='系统管理员',
            role='finance',
            account_status='normal',
            staff_type='在编',
            valid_start_date=datetime.now().date(),
        )
        db.session.add(admin)
        db.session.commit()

    # 6. 默认客户端元信息
    if not ClientMeta.query.first():
        client = ClientMeta(
            client_id='finance-default-001',
            client_type='finance',
            client_name='报销稽核系统-财务版',
        )
        db.session.add(client)
        db.session.commit()


def init_database():
    """建表 + 预置数据（兼容旧接口，内部走 migrate.py）"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrations.runner import MigrationManager
    mgr = MigrationManager()
    mgr.upgrade()


if __name__ == '__main__':
    force = '--force' in sys.argv

    if force:
        db_path = Path('reimbursement.db')
        if db_path.exists():
            backup = Path('backup') / f'force_init_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(str(db_path), str(backup))
            print(f'⚠️ 已备份当前库到: {backup}')
            db_path.unlink()
            print('⚠️ 已删除当前库')

    print('=' * 60)
    print('初始化数据库（推荐用 migrate.py，本脚本已自动代理）')
    print('=' * 60)
    init_database()
