# 报销稽核系统

> 桌面三客户端应用 · 麒麟/UOS/Windows 信创兼容 · 等保二级合规


## CI/CD 状态

![CI](https://github.com/hellomerry/baox_new/workflows/CI/badge.svg)
![Build Windows](https://github.com/hellomerry/baox_new/workflows/Build%20Windows/badge.svg)
![Build Linux](https://github.com/hellomerry/baox_new/workflows/Build%20Linux/badge.svg)
![Dependabot](https://img.shields.io/badge/Dependabot-enabled-02569B?logo=dependabot&logoColor=white)
![GitHub release](https://img.shields.io/github/v/release/hellomerry/baox_new)
![License](https://img.shields.io/github/license/hellomerry/baox_new)


## 一、项目定位

**本项目是一个用于**"基层单位报销"全流程**的离线优先桌面应用**。三类客户端共享一套 SQLite 数据库，按角色分配不同功能：

| 客户端 | 角色 | 主要职责 |
|--------|------|----------|
| **财务版** (`finance`) | 财务人员 | 项目台账、人员管理、终审复核、统计报表、审计日志、跨网摆渡（`.rbag` 包） |
| **稽核员版** (`auditor`) | 稽核员 | 单据初审、操作日志、代填报销（机关场景） |
| **报销人版** (`reimburser`) | 基层报销人 | 个人单据录入、考勤记录、资料维护 |

**适用场景**：差旅报销、日常开支、项目分摊、自然人合并识别（同一身份证号下的多个账号）、冲红记账、审批终结。

**核心特点**：
- 🔒 **离线优先**：所有操作本地 SQLite 完成，跨网用 `.rbag` 加密包摆渡
- 🛡️ **等保二级**：AES-256 字段加密、Scrypt 派生、登录限速、审计日志
- 💻 **信创兼容**：Python 3.11 + PyWebView，可在麒麟 V10/UOS/Windows 部署
- 📦 **PyInstaller 打包**：三个客户端独立打包，无需安装 Python 环境即可运行
- 🧪 **测试覆盖**：284 个 pytest 用例覆盖认证/单据/附件/包/审计/OCR/代理/通知/决策链/导入导出核心链路

---

## 二、目录结构

```
reimbursement-app/
├── app.py                     # Flask app 工厂（finance/auditor/reimburser 客户端类型）
├── config.py                  # 配置（DB 路径、TLS、限速参数）
├── init_db.py                 # 初始化基线数据（admin / 4 岗位级别 / 12 报销标准）
├── generate_ssl.py            # 自签 TLS 证书（3650 天）
├── center_node.py             # 独立中心节点服务（跨网数据汇总）
├── build.py                   # PyInstaller 三客户端打包脚本
│
├── launcher_finance.py        # 财务版桌面启动器（PyWebView 壳）
├── launcher_auditor.py        # 稽核员版启动器
├── launcher_reimburser.py     # 报销人版启动器
│
├── models/                    # SQLAlchemy 模型（19 张表 + sys_config / position_level / expense_standard）
├── routes/                    # 11 个蓝图：auth, bills, users, projects, attendance, packages, sync, attachments, audit, reports, standards
├── services/                  # 业务服务：bill_service, user_service, project_service, attendance_service, redrush_service, natural_person_service, attachment_service, sync_service, report_service
├── utils/                     # 通用：crypto (AES-256), rbag (包), validators, ratelimit (手写限速), backup, bill_number
│
├── templates/
│   └── dashboard.html         # 三客户端共用 SPA 入口（role-based 切换）
├── static/                    # app.js (38KB), style.css (9.5KB)
│
├── tests/                     # 284 个 pytest 用例
│   ├── conftest.py            # fixtures：app, live_url, admin_user, project, auditor, reimburser
│   ├── test_transfer_ocr.py   # 61 个 OCR 识别/摆渡测试
│   ├── test_bills.py          # 25 个单据流转测试
│   ├── test_agents_api.py     # 20 个代理关系测试
│   ├── test_data_import.py    # 18 个数据导入测试
│   ├── test_client_distribution.py  # 18 个客户端分发测试
│   ├── test_rbag.py           # 16 个 .rbag 包测试
│   ├── test_notifications.py  # 16 个通知测试
│   ├── test_auth.py           # 14 个认证测试
│   ├── test_research_audit.py # 13 个稽核研究测试
│   ├── test_agent_full_mode.py  # 13 个代理全流程测试
│   ├── test_validators.py     # 12 个验证器单元测试
│   ├── test_upgrade.py        # 12 个升级/版本测试
│   ├── test_decision_chain.py # 12 个决策链测试
│   ├── test_excel_export.py   # 10 个 Excel 导出测试
│   ├── test_word_export.py    # 7 个 Word 制式单据导出测试
│   └── …（packages/attachments/encrypt 等共 11 个）
│
├── uploads/bill_<id>/         # 附件存储（按 bill_id 分目录）
├── backup/                    # 自动备份目录（启动时滚动）
├── logs/                      # ErrorLog + OperationLog
├── rbag_temp/                 # .rbag 解包临时目录
├── reimbursement.db           # 主数据库（启动时自动创建）
└── requirements.txt
```

---

## 三、技术栈

| 类别 | 选型 | 备注 |
|------|------|------|
| 后端 | Flask 3.1 + SQLAlchemy 2 + SQLite | 严格不用 FastAPI |
| 桌面壳 | PyWebView 6.2 | 跨平台，无需 Electron |
| 加密 | cryptography | AES-256-CBC + Scrypt 派生 |
| 报表 | reportlab / python-docx | PDF 导出（STSong-Light 中文字体）+ Word 制式单据导出（黑体/宋体） |
| 打包 | PyInstaller 6 | 三客户端独立 .exe |
| 前端 | 原生 HTML / JS / CSS | **不用 Vue/React** |
| 测试 | pytest 9 + pytest-flask | live_url 走真实 HTTP 避免 session 共享问题 |

---

## 四、快速开始（开发模式）

### 1. 安装依赖

```bash
# 推荐使用国内源（信创/无外网环境）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 或
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python init_db.py
# 创建 19 张表 + 默认 admin/财务/4 岗位级别/12 报销标准
# 默认 admin 密码：admin@2026（首次登录强制改密）
```

### 3. 启动任一客户端

```bash
# 财务版（推荐用 admin 登录）
python launcher_finance.py

# 稽核员版
python launcher_auditor.py

# 报销人版
python launcher_reimburser.py
```

每个启动器都会：
- 进程锁（同一台机器同一客户端只允许一个实例）
- 完整性校验（关键文件 SHA256）
- 启动时自动备份（保留最近 5 份）
- TLS 自签证书加载（已生成则复用）
- 起 Flask + PyWebView

### 4. 跑测试

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
# 69 passed in ~67s
```

---

## 五、生产部署（PyInstaller 打包）

### 1. 准备环境

```bash
pip install pyinstaller
python generate_ssl.py  # 生成自签证书（dist/certs/）
```

### 2. 打包三客户端

```bash
python build.py
# 产物在 dist/ 下：
#   dist/finance/finance.exe (~50MB)
#   dist/auditor/auditor.exe
#   dist/reimburser/reimburser.exe
```

### 3. 分发安装

将 `dist/<client>/` 整个目录拷贝到目标机器（Windows）或目标主机（麒麟/UOS），双击 `<client>` 即可。**首次运行**会自动：
- 创建 `%APPDATA%/reimbursement-app/` 或 `~/.config/reimbursement-app/` 工作目录
- 生成数据库 + 加载 TLS 证书
- 创建初始 admin 账号

### 4. 中心节点部署（多单位汇总场景）

```bash
# 在汇总端机器运行
python center_node.py
# 监听 0.0.0.0:5443（可改），支持 TLS
# 各单位客户端的"数据包"功能可上传到此节点
```

详见 [信创部署指南](docs/信创部署指南.md)（TODO）和 [运维手册](docs/运维手册.md)（TODO）。

---

## 六、核心业务规则（摘要）

完整 88+ 条决策见 `docs/decisions/`（A-P 系列），下面是高频引用：

| 决策 | 描述 |
|------|------|
| **C1 进程锁** | 同一台机器同一客户端只允许一个实例（Windows msvcrt / Linux fcntl） |
| **C4 自然人分离** | 同一身份证号下多个账号合并识别（SHA256(6位地区码+8位生日+4位尾号)） |
| **G1 身份铁律** | 财务/稽核员账号 **永远不能** 当报销人提交单据 |
| **G2 代填=已审** | 稽核员代填的报销单跳过初审环节 |
| **G3 项目总账** | `bill_type='project_total'` 时 `user_id=NULL`（项目分摊场景） |
| **K1 三态返回** | 重复校验返回 `(status, message, conflicts)` 三态 |
| **L2 冲红** | `archived`/`approved` 状态可冲红，金额取负，状态=`submitted_finance` |
| **L5 单号格式** | `B{YYYYMMDD}-{project_code}-{5位序号}` |
| **N1 字段加密** | `id_card`/`bank_card`/`phone` 用 AES-256-CBC 加密存储 |
| **O1 TLS** | 自签证书 3650 天，所有内网 HTTP 走 HTTPS |
| **O2 限速** | 登录 10 次/分钟，全局 60 次/分钟（**手写限速**，因 flask-limiter 装不上） |
| **O5 会话超时** | 8 小时自动登出 |
| **O12 客户端-角色绑定** | `finance` 客户端只接受 `finance` 角色登录 |

---

## 七、API 概览（11 个蓝图，50+ 端点）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/auth/login` | POST | 登录（含客户端类型校验） |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/change-password` | POST | 改密（首次登录强制） |
| `/api/bills/create` | POST | 创建报销单 |
| `/api/bills/<id>/submit` | POST | 提交至初审 |
| `/api/bills/<id>/audit` | POST | 初审通过/驳回 |
| `/api/bills/<id>/final-audit` | POST | 终审 |
| `/api/bills/<id>/red-rush` | POST | 冲红 |
| `/api/bills/check-duplicate` | POST | 重复校验（三态返回） |
| `/api/bills/<id>/pdf` | GET | 导出 PDF |
| `/api/attachments/upload/<bill_id>` | POST | 上传附件 |
| `/api/attachments/<id>/verify` | GET | 完整性校验（SHA256 对比） |
| `/api/packages/export` | POST | 导出 .rbag 加密包 |
| `/api/packages/import` | POST | 导入 .rbag 包 |
| `/api/audit/logs` | GET | 审计日志 |
| `/api/reports/monthly` | GET | 月度统计 |
| `/api/users/<id>/same-natural` | GET | 同自然人查询 |
| `/api/sync/upload` | POST | 上传至中心节点 |
| `/api/sync/download` | GET | 从中心节点下载 |

---

## 八、安全合规

### 8.1 等保二级要求落实

| 项 | 实现 |
|----|------|
| 身份鉴别 | 用户名+密码（PBKDF2/Scrypt）+ 失败锁定（5次/30分钟） |
| 访问控制 | RBAC（finance/auditor/reimburser）+ 客户端-角色绑定 |
| 安全审计 | `operation_log` + `error_log` 两张表 + 不可篡改 |
| 数据完整性 | 附件 SHA256 + .rbag HMAC-SHA256 |
| 数据保密性 | 敏感字段 AES-256-CBC 加密 + 传输 TLS 1.2+ |
| 通信保密 | HTTPS 强制（自签 3650 天证书） |

### 8.2 加密体系

- **字段加密**：`utils/crypto.py` → `encrypt_field(plaintext)` / `decrypt_field(ciphertext)`
- **派生函数**：Scrypt（密码→key，n=32768）
- **算法**：AES-256-CBC + 随机 IV
- **编码**：base64

### 8.3 限速

`utils/ratelimit.py` 手写内存滑动窗口：
- `limit_login`：登录端点，10 次/分钟/IP
- `limit_global`：全局，60 次/分钟/IP

---

## 九、测试

```bash
# 全量
PYTHONPATH=. python3 -m pytest tests/ -v
# 69 passed in ~67s

# 单模块
PYTHONPATH=. python3 -m pytest tests/test_auth.py -v
PYTHONPATH=. python3 -m pytest tests/test_bills.py -v
PYTHONPATH=. python3 -m pytest tests/test_rbag.py -v

# 覆盖率（可选）
PYTHONPATH=. python3 -m pytest tests/ --cov=. --cov-report=html
```

测试覆盖：
- 认证：14 用例（登录/登出/改密/锁定/客户端绑定/Token 失效）
- 单据：15 用例（创建/提交/初审/终审/冲红/重复校验/PDF）
- .rbag 包：16 单元 + 6 路由
- 附件：6 用例（上传/列表/下载/校验/篡改检测/自然人查询）
- 验证器：12 单元（三层准入/状态机/防重复/高标准）

---

## 十、已知限制 / 后续可做

- [ ] 完整信创部署指南（麒麟 V10 SP3/UOS 1050）
- [ ] 终审独立审计日志 PDF 导出
- [ ] Excel 报表导出（xlsxwriter）
- [ ] 真实短信/邮件通知（当前仅审计日志）
- [ ] 双因子认证（UKey）
- [ ] 完整的 docker-compose 部署

---

## 十一、版本与变更

- **v2.11.0** (2026-10-22) — 合入 v2.10.0e（财务端桌面+Web 双模式、Windows GBK 编码修复）+ 报销单 Word 制式单据导出，284 用例全过
- **v1.0** (T0→T5 + 加固) — 核心链路完成，69 用例通过
- 决策文档：88+ 条（A-P 系列）保存在 `docs/decisions/`

---

## 十二、License

内部使用。
