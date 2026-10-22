"""
v1.0.0 初始迁移 — 首次部署
对应 init_db.py 的初始建表 + 预置数据
"""
from datetime import datetime
import hashlib

# revision identifiers
revision = 'v1.0.0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    """升级：建表 + 预置基础数据"""
    from sqlalchemy import inspect
    from models import db
    from models.models import (
        SysUser, PositionLevel, SysConfig, ExpenseStandard, ClientMeta,
    )

    # 1. 建表（create_all 不影响已存在的表）
    db.create_all()
    insp = inspect(db.engine)
    tables = insp.get_table_names()
    print(f'  [v1.0.0] 已建表 {len(tables)} 张')

    session = session_factory()

    # 2. 预置 4 条职务等级
    positions = [
        ('PROVINCIAL', '省级职务', '省部级正职及以上'),
        ('BUREAU', '厅局级职务', '厅局级正副职'),
        ('DIVISION', '处级职务', '处级正副职'),
        ('OTHER', '其他职务', '科级及以下'),
    ]
    for code, name, desc in positions:
        if not session.query(PositionLevel).filter_by(level_code=code).first():
            session.add(PositionLevel(level_code=code, level_name=name, description=desc))
    session.commit()
    print('  [v1.0.0] 预置 4 条职务等级')

    # 3. 预置 10 条系统配置
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
        if not session.query(SysConfig).filter_by(config_key=key).first():
            session.add(SysConfig(config_key=key, config_value=value, config_name=name))
    session.commit()
    print('  [v1.0.0] 预置 10 条系统配置')

    # 4. K9 决策：预置 12 条报销标准
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
    count = 0
    for pos_id, staff_type, subsidy_type, amount, remark in standards:
        existing = session.query(ExpenseStandard).filter_by(
            position_id=pos_id, staff_type=staff_type, subsidy_type=subsidy_type
        ).first()
        if not existing:
            session.add(ExpenseStandard(
                position_id=pos_id,
                staff_type=staff_type,
                subsidy_type=subsidy_type,
                amount=amount,
                valid_start=datetime.now().date(),
                remark=remark,
            ))
            count += 1
    session.commit()
    print(f'  [v1.0.0] 新增 {count} 条报销标准（共 12 条）')

    # 5. 默认财务账号 admin
    if not session.query(SysUser).filter_by(username='admin').first():
        admin = SysUser(
            username='admin',
            password_hash=hashlib.md5('admin@2026'.encode()).hexdigest(),
            real_name='系统管理员',
            role='finance',
            account_status='normal',
            staff_type='在编',
            valid_start_date=datetime.now().date(),
        )
        session.add(admin)
        session.commit()
    print('  [v1.0.0] 创建默认 admin（首次登录强制改密）')

    # 6. 默认客户端元信息
    if not session.query(ClientMeta).first():
        client = ClientMeta(
            client_id='finance-default-001',
            client_type='finance',
            client_name='报销稽核系统-财务版',
        )
        session.add(client)
        session.commit()
    print('  [v1.0.0] 创建默认客户端元信息')

    session.close()


def downgrade(engine, session_factory):
    """降级：删除所有表（危险！）"""
    from models import db
    print('  [v1.0.0] 警告：即将删除所有表...')
    db.drop_all()
    print('  [v1.0.0] 已删除所有表')
