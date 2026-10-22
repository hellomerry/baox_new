# 部署说明（v2.10.0d）

> 报销稽核系统部署全流程速查 — 财务 / 稽核员 / 报销员三客户端
> 详细子文档：[docs/deploy/Windows打包指南.md](./docs/deploy/Windows打包指南.md) · [docs/deploy/信创部署指南.md](./docs/deploy/信创部署指南.md)

---

## 〇、版本速查

| 角色 | 客户端 | 部署产物 | 大小 | 入口 |
|------|--------|---------|------|------|
| 财务 | `launcher_finance.py` | `reimbursement-app-windows-green-v2100d-finance.zip` | ~122MB | `启动财务版.bat` |
| 稽核员 | `launcher_auditor.py` | `reimbursement-app-windows-green-v2100d-auditor.zip` | ~122MB | `启动稽核员版.bat` |
| 报销员 | `launcher_reimburser.py` | `reimbursement-app-windows-green-v2100d-reimburser.zip` | ~122MB | `启动报销人版.bat` |

> **v2.10.0d 关键变化**：v2.10.0 起，**客户端分发由财务自动打包**，不再分别给三个 .zip。具体见第五章。

---

## 一、部署模式选择

按机构规模和信创要求，**三种模式**可选：

### 模式 A：单机部署（≤10 人）
- 一台机器跑财务端（中心节点）
- 报销员/稽核员用同一台机器的客户端切换
- **不推荐**用于生产，仅测试/试用

### 模式 B：LAN 三客户端（10-100 人）
- 财务端做中心节点（必开）
- 稽核员/报销员端从中心节点拉数据
- 适合基层单位/机关

### 模式 C：混合部署（v2.10.0d 推荐，任意规模）⭐
- 部分报销员由稽核员**全权代办**（无客户端）
- 部分报销员**自助**登录客户端
- 系统根据 `agent_auth` 自动判定每个报销员的模式
- **最贴近真实场景**，按需生成客户端，省部署/维护成本

详细见 [USER_MANUAL.html §8.4 模式 C 混合部署](./docs/USER_MANUAL.html)

---

## 二、Windows 绿色版（最简单，5 分钟上线）

### 适用场景
- 临时试点 · 个人试用 · 不想装 Python
- 仅 Windows 7/10/11 x86_64

### 步骤
1. **下载** `reimbursement-app-windows-green-v2100d.zip`（122MB）
2. **解压**到任意目录（建议 `D:\报销稽核系统\`）
3. **双击**对应角色 .bat：
   - `启动财务版.bat` → admin 登录
   - `启动稽核员版.bat` → audit001 登录
   - `启动报销人版.bat` → reimb001 登录
4. **首次启动**会自动检查依赖（~30 秒），弹出 PyWebView 窗口
5. **完成** ✅

### 默认账号
```
财务：admin / NewP@ss123
稽核员：audit001 / Audit@001!
报销员：reimb001 / Reimb@001!
```

### 目录结构
```
windows_green/
├── python/                    # 21MB Python 解释器（embeddable）
│   ├── python.exe
│   └── Lib/site-packages/     # 285MB 依赖
├── workspace/reimbursement-app/
├── 启动财务版.bat
├── 启动稽核员版.bat
├── 启动报销人版.bat
└── 使用说明.txt
```

> 详细：[docs/deploy/Windows打包指南.md](./docs/deploy/Windows打包指南.md)

---

## 三、信创部署（麒麟 V10 / UOS 1050）

### 适用场景
- 政府/国企等保合规
- 国产化要求

### 麒麟 V10 部署
```bash
# 1. 安装系统依赖
sudo yum install -y python3.11 python3-pip python3-gobject gtk3 \
    webkit2gtk3 webkit2gtk3-devel gcc python3-devel

# 2. 上传并解压绿色版
unzip reimbursement-app-windows-green-v2100d.zip
# （注：麒麟用 Linux wheel，单独打包，见 docs/deploy/信创部署指南.md）

# 3. 启动
cd windows_green/workspace/reimbursement-app
python3.11 launcher_finance.py
```

> 详细：[docs/deploy/信创部署指南.md](./docs/deploy/信创部署指南.md)

---

## 四、源码部署（开发者）

### 4.1 环境要求
- Python 3.11+
- SQLite 3.40+
- pip 23+

### 4.2 克隆 & 安装
```bash
git clone https://github.com/hellomerry/baox_new.git
cd baox_new
pip install -r requirements.txt
```

### 4.3 初始化数据库
```bash
python init_db.py
# 会创建：1 个 admin 财务 + 1 个 audit001 稽核员 + 1 个 reimb001 报销员
```

### 4.4 启动
```bash
# 财务端（中心节点）
python launcher_finance.py

# 稽核员端（另一终端）
python launcher_auditor.py

# 报销员端（另一终端）
python launcher_reimburser.py
```

### 4.5 测试
```bash
pytest tests/ -p no:cacheprovider -q
# 期望：267+ passed（v2.8 调令 OCR 沙箱适配问题无关）
```

---

## 五、客户端分发（v2.10.0d 推荐流程）⭐

> 财务不再分发预打包的 .zip，而是**在系统内一键生成**每个稽核员/报销员的客户端。

### 5.1 流程图
```
[财务端] → 人员账号 → 选用户 → [📦 下发稽核员端] / [📦 下发报销员端]
   ↓
数据裁剪（services/client_distribution_service.py）：
   1. DELETE FROM sys_user WHERE id NOT IN (本角色可见)
   2. DELETE FROM expense_bill WHERE user_id NOT IN (...)
   3. DELETE FROM agent_auth WHERE ...
   ↓
模板复制（services/client_packager.py）：
   1. shutil.copy(green_client_template, {role}_{uid}_{ts}/)
   2. 替换 db
   3. zip 打包
   ↓
[download URL 给用户]
```

### 5.2 API
| 路由 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/api/distribution/build/auditor/<id>` | POST | 财务 | 生成稽核员客户端 |
| `/api/distribution/build/reimburser/<id>` | POST | 财务 | 生成报销员客户端（模式 C 拦截） |
| `/api/distribution/build/finance` | POST | 财务 | 生成财务客户端 |
| `/api/distribution/download/<id>` | GET | 财务 | 下载已生成的客户端 |
| `/api/distribution/list` | GET | 财务 | 已生成的客户端列表 |
| `/api/distribution/check-reimburser/<id>` | GET | 财务/稽核员 | 检查报销员部署模式 |

### 5.3 模式 C 自动拦截
- 报销员处于 `agent_c` 模式（完全被代理）→ 自动跳过，不生成客户端
- 报销员处于 `partial` 模式（部分被代理）→ 仍生成客户端
- 报销员处于 `self` 模式（无代理）→ 生成客户端
- 报销员处于 `orphan` 模式（无项目）→ 提示"未绑定项目"

---

## 六、网络 & 中心节点

### 6.1 端口
| 端口 | 用途 | 是否必须 |
|------|------|---------|
| 5443 | 财务中心节点 HTTPS | 是 |
| 5444 | 客户端分发 | 是 |
| 443 | TLS | 是 |

### 6.2 TLS 证书
- 首次启动会自动生成自签名证书（`generate_ssl.py`）
- 生产环境替换为 CA 签名证书
- 客户端连接时需要信任该证书

### 6.3 防火墙（信创环境）
```bash
# 麒麟/UOS
sudo firewall-cmd --permanent --add-port=5443/tcp
sudo firewall-cmd --permanent --add-port=5444/tcp
sudo firewall-cmd --reload
```

---

## 七、升级流程

### 7.1 应用内升级（v2.4+）
- 财务端"应用升级"菜单
- 上传新版本 zip → 自动备份旧 db → 解压 → 启动
- 失败时回滚到 `backups/pre_upgrade_{version}_{ts}.db`

### 7.2 手动升级
```bash
# 1. 停服务
# 2. 备份
cp reimbursement.db backups/reimbursement_{date}.db

# 3. 替换
unzip -o reimbursement-app-windows-green-v2100d.zip -d /tmp/new
cp -r /tmp/new/* /path/to/old/

# 4. 跑迁移
python migrate.py

# 5. 启动
python launcher_finance.py
```

### 7.3 跨大版本升级
v2.x → v2.10.0d 的迁移会自动执行 `migrations/versions/v2_*.py`。
详见 [USER_MANUAL.html 附录 D 版本历史](./docs/USER_MANUAL.html)

---

## 八、备份与恢复

### 8.1 自动备份
- 每日 02:00 自动备份到 `backups/reimbursement_YYYYMMDD.db`
- 保留最近 7 天

### 8.2 手动备份
```bash
sqlite3 reimbursement.db ".backup 'backups/manual_$(date +%Y%m%d_%H%M%S).db'"
```

### 8.3 恢复
```bash
# 停服务 → 备份文件覆盖 → 启动
cp backups/reimbursement_20260825.db reimbursement.db
python launcher_finance.py
```

---

## 九、监控 & 日志

| 日志 | 路径 | 说明 |
|------|------|------|
| 应用日志 | `logs/app.log` | INFO 级，自动滚动 |
| 审计日志 | `audit_log` 表 | 所有敏感操作 |
| 错误日志 | `logs/error.log` | ERROR 级，含堆栈 |
| 性能日志 | `logs/perf.log` | 慢查询 >500ms |

### Prometheus 指标（可选）
```bash
pip install prometheus-flask-exporter
# 见 docs/deploy/信创部署指南.md § 十一
```

---

## 十、常见部署问题

### 10.1 PyWebView 启动白屏
```bash
# 麒麟：检查 webkit2gtk
sudo yum install -y webkit2gtk3 webkit2gtk3-devel

# Windows：检查 VC++ Redistributable
# 下载：https://aka.ms/vs/17/release/vc_redist.x64.exe
```

### 10.2 OCR 报"模型找不到"
- 绿色版已内置 `ch_PP-OCRv4` 模型，正常无需处理
- 源码部署需 `pip install rapidocr_onnxruntime` 自动下载模型

### 10.3 客户端连不上中心节点
1. 检查财务端是否启动（5443 端口）
2. 检查防火墙
3. 检查 `sys_config.center_node_host` 配置

### 10.4 模式 C 报销员打不出客户端
正常行为。该报销员已被稽核员全权代理，无需客户端。
可在 `/api/distribution/check-reimburser/<id>` 查看状态。

### 10.5 数据库锁等待
SQLite 单写多读，并发高时偶发。已用 WAL 模式优化。极端情况下重启服务。

---

## 十一、生产部署 checklist

- [ ] TLS 证书替换为 CA 签名
- [ ] 防火墙规则收敛
- [ ] 备份策略启用（每日 02:00 + 异地）
- [ ] 审计日志定期归档
- [ ] 升级流程演练（应用内升级）
- [ ] 应急预案（数据恢复 <30 分钟）
- [ ] 等保二级测评（密码复杂度/限速/审计）

---

## 十二、文档导航

| 文档 | 路径 | 适用人群 |
|------|------|---------|
| 用户手册 | [docs/USER_MANUAL.html](./docs/USER_MANUAL.html) | 财务/稽核员/报销员 |
| Windows 打包 | [docs/deploy/Windows打包指南.md](./docs/deploy/Windows打包指南.md) | 打包工程师 |
| 信创部署 | [docs/deploy/信创部署指南.md](./docs/deploy/信创部署指南.md) | 系统管理员 |
| **本文件** | [DEPLOY.md](./DEPLOY.md) | 部署总入口 |
| README | [README.md](./README.md) | 开发者/项目介绍 |
| CI/CD | [.github/workflows/](./.github/workflows/) | 持续集成 |

---

**文档版本**：v2.10.0d ｜ **最后更新**：2026-08-25 ｜ **维护**：Mavis Agent
