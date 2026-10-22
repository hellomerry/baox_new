"""
v2.4.0 — 应用内升级向导

变更：
- 新建 app_version 表：所有发布的版本 + changelog
- 预置 v1.0.0 ~ v2.3.0 共 8 个版本
"""
revision = 'v2.4.0'
down_revision = 'v2.3.0'
branch_labels = None
depends_on = None
description = '应用内升级向导：app_version 表 + 8 个版本 changelog'


def upgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        # app_version 表
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS app_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version VARCHAR(20) NOT NULL UNIQUE,
                release_date DATE NOT NULL,
                min_required_version VARCHAR(20),
                title VARCHAR(200) NOT NULL,
                changelog TEXT NOT NULL,
                mandatory BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_app_version_date ON app_version(release_date)"))

        # 预置 8 个版本 changelog
        versions = [
            ('v1.0.0', '2026-08-20', None, '报销稽核系统首发', '''# 报销稽核系统 v1.0.0

## ✨ 核心功能
- T0-T5 全链路业务流（创建/提交/初审/终审/归档/冲红）
- 19 张数据库表 + 12 个 service + 11 个蓝图
- 原生 HTML/JS 前端（无 Vue/React 依赖）
- 财务 / 稽核员 / 报销人三角色客户端

## 🔒 安全
- N1 AES-256 字段加密
- O1 TLS 1.2+
- 离线优先 + .rbag 摆渡''', 0),
            ('v1.1.0', '2026-08-21', 'v1.0.0', '附件上传 + 项目总账', '''# v1.1.0

## ✨ 新增
- 附件管理（图片/PDF，SHA-256 去重）
- 项目总账（L7 决策）
- 代填报销（G2 决策）''', 0),
            ('v1.2.0', '2026-08-21', 'v1.0.0', 'N1 加密：业务层透明', '''# v1.2.0

## 🔒 安全
- N1 AES-256 字段加密（身份证/银行卡/电话）
- 加密/解密 API 业务层透明调用
- 提供存量数据加密工具''', 0),
            ('v1.3.0', '2026-08-22', None, '手写限速 + 会话控制', '''# v1.3.0

## ⚙️ 性能
- O2 手写限速（登录 10/分钟，全局 60/分钟）
- O5 会话超时 8 小时
- 失败锁定 30 分钟''', 0),
            ('v2.0.0', '2026-08-22', 'v1.3.0', 'D3 决策：终审独立审计', '''# v2.0.0

## 🔍 审计
- research_audit_log 表：终审独立审计通道
- 区别于 finance_audit_log（财务双人会签）
- PDF 报告导出（reportlab + SHA-256 哈希）''', 0),
            ('v2.1.0', '2026-08-23', 'v2.0.0', 'D3 决策：真双签', '''# v2.1.0

## 🤝 双签
- 大额报销（≥10 万）必须两人分别操作
- 主财务 approve → pending_dual_sign
- 第二签人必须实际登录批准
- finance_dual_signer_id + finance_dual_signed 字段''', 0),
            ('v2.2.0', '2026-08-24', 'v2.1.0', '公告/通知系统', '''# v2.2.0

## 🔔 通知
- 站内通知（顶部红点 + 列表 + 已读/未读）
- 7 个预置模板（approved/rejected/pending_dual/...）
- 业务事件自动触发
- 财务/稽核员/管理员可发''', 0),
            ('v2.3.0', '2026-08-25', 'v2.2.0', '数据导入向导', '''# v2.3.0

## 📥 导入
- 从 Excel 批量导入用户/项目/标准
- 模板下载 + 预览校验 + 错误报告
- 3 种类型 + 事务回滚
- 18 个测试''', 0),
            ('v2.4.0', '2026-08-25', 'v2.3.0', 'D3 UI 加强：决策链', '''# v2.4.0

## 🔍 D3 加强
- 决策链 API：合并 3 个审计表
- 单据详情页 + 决策链弹窗
- 终审审计页面：筛选 + 详情弹窗
- 12 个测试''', 0),
        ]
        for ver, date, min_req, title, log, mand in versions:
            conn.execute(db.text("""
                INSERT OR IGNORE INTO app_version
                (version, release_date, min_required_version, title, changelog, mandatory)
                VALUES (:v, :d, :mr, :t, :c, :m)
            """), {'v': ver, 'd': date, 'mr': min_req, 't': title, 'c': log, 'm': mand})

        conn.commit()


def downgrade(engine, session_factory):
    from models import db
    with engine.connect() as conn:
        conn.execute(db.text("DROP TABLE IF EXISTS app_version"))
        conn.commit()
