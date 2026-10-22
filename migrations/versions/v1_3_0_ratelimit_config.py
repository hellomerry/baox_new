"""
v1.3.0 — O2 决策：限速参数化
- 把硬编码的限速值搬到 sys_config
- 已有 audit_threshold_low / audit_threshold_high 等，新增限速相关
"""
revision = 'v1.3.0'
down_revision = 'v1.2.0'
branch_labels = None
depends_on = None


def upgrade(engine, session_factory):
    from models.models import SysConfig
    session = session_factory()

    new_configs = [
        ('ratelimit_login_per_minute', '10', '登录端点限速（次/分钟/IP）'),
        ('ratelimit_global_per_minute', '60', '全局 API 限速（次/分钟/IP）'),
        ('session_timeout_hours', '8', '会话超时（小时）'),
    ]

    added = 0
    for key, value, name in new_configs:
        if not session.query(SysConfig).filter_by(config_key=key).first():
            session.add(SysConfig(config_key=key, config_value=value, config_name=name))
            added += 1
    session.commit()
    print(f'  [v1.3.0] 新增 {added} 条限速/会话配置')
    session.close()


def downgrade(engine, session_factory):
    from models.models import SysConfig
    session = session_factory()
    keys = ['ratelimit_login_per_minute', 'ratelimit_global_per_minute', 'session_timeout_hours']
    deleted = session.query(SysConfig).filter(SysConfig.config_key.in_(keys)).delete(synchronize_session=False)
    session.commit()
    print(f'  [v1.3.0] 删除 {deleted} 条限速/会话配置')
    session.close()
