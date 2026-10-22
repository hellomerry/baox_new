# Web 访问部署指南（v2.10.0e）

> 财务端 launcher_finance.py 默认同时启桌面 + Web（同进程双入口），
> 让其他角色（稽核员 / 报销人）也能通过浏览器访问本机系统。

---

## 一、能力概览

| 维度 | 桌面端（PyWebView） | Web 端（浏览器） |
|------|---------------------|------------------|
| 入口 | 桌面窗口（127.0.0.1） | 任意浏览器（同网段） |
| 角色绑定 | 严格：finance 客户端只能登录 finance 账号 | 白名单：默认 finance/auditor/reimburser 都可 |
| TLS | 自签证书（HTTPS） | 自签证书（HTTPS，必须） |
| 会话 | cookie（SESSION_COOKIE_SECURE=False） | cookie（SESSION_COOKIE_SECURE=True） |
| 限速 / 审计 | 同左 | 同左（IP 改为浏览器客户端 IP） |
| 进程锁 | C1 单实例（同一台机器同一客户端只允许一个） | 同左（浏览器多会话共存） |
| 端口 | 随机（find_free_port） | 5443（可在 `WEB_PORT` 环境变量改） |

---

## 二、准备：生成 TLS 证书

> 浏览器访问 **必须 HTTPS**（SESSION_COOKIE_SECURE=True，无 HTTPS 拿不到 cookie）。
> 自签证书会触发"不安全"提示，用户手动确认即可（生产建议对接企业 CA）。

```cmd
:: 进财务端目录
cd E:\dev_AI\minimax\jw\workspace\reimbursement-app

:: 自动检测本机 IP + hostname 加入 SAN
python generate_ssl.py

:: 或自定义 IP / hostname（推荐生产环境）
python generate_ssl.py --cn finance01.bx.local --ips 192.168.1.100,10.0.0.5 --hostnames finance.bx.local
```

证书位置：`ssl/cert.pem` + `ssl/key.pem`

> **重要**：证书 CN 必须是浏览器实际访问的 IP 或 hostname 之一。
> 自签证书 SAN 不含的地址，浏览器会直接拒绝访问。

---

## 三、启动：双模式财务端

```cmd
:: 默认同时启桌面 + Web（推荐）
python launcher_finance.py
```

启动后控制台会显示：

```
[1/6] 数据库迁移: 已是最新（v2.10.0d）
[2/6] 进程锁获取成功
[3/6] 数据库完整性: OK
[4/6] Flask 应用创建成功
[5/6] TLS 启用: ...\ssl\cert.pem
[6/6] 桌面 Flask 启动: 127.0.0.1:53412
[WEB] Web 模式已启用: https://0.0.0.0:5443
[WEB]   同网段浏览器访问: https://<本机IP>:5443
[WEB]   允许登录角色: ['finance', 'auditor', 'reimburser']
```

桌面窗口会弹出，Web 服务在后台运行（不阻塞）。

---

## 四、关闭 Web（仅桌面模式）

```cmd
set WEB_ENABLED=false
python launcher_finance.py
```

或：

```cmd
python launcher_finance.py --no-web    :: 需要后续在 launcher 加 --no-web 参数
```

（当前实现：仅通过环境变量控制；CLI 参数为后续 TODO）

---

## 五、配置项（环境变量）

| 环境变量 | 默认 | 含义 |
|----------|------|------|
| `WEB_ENABLED` | `true` | 是否启用 Web 模式（财务端 launcher 启动时） |
| `WEB_HOST` | `0.0.0.0` | Web 监听地址；改 `127.0.0.1` 等同关闭外网访问 |
| `WEB_PORT` | `5443` | Web 端口（需在防火墙放行） |
| `WEB_REQUIRE_HTTPS` | `true` | 是否要求 TLS；本地 dev 可设 false 但 cookie 拿不到 |
| `WEB_ALLOWED_ROLES` | `finance,auditor,reimburser` | 登录角色白名单（逗号分隔）；空 = 全部禁止 |
| `WEB_CORS_ORIGINS` | `*` | 跨域白名单；生产建议指定为具体 origin |

示例：限制 Web 模式只允许稽核员访问

```cmd
set WEB_ALLOWED_ROLES=auditor
python launcher_finance.py
```

---

## 六、防火墙 / 网络

### Windows 防火墙放行 5443 入站

```powershell
New-NetFirewallRule -DisplayName "报销 Web" -Direction Inbound `
    -LocalPort 5443 -Protocol TCP -Action Allow -Profile Domain,Private
```

> 仅放行内网（Profile=Domain,Private），公网（Public）不放行。
> 如要公网访问，必须配合企业 VPN / Nginx 反代 + 额外认证。

### 路由器 / 交换机

- 同 VLAN 内互通即可
- 跨网段需保证 5443 端口可达

---

## 七、用户使用

### 浏览器访问

1. 同网段用户打开浏览器
2. 地址栏输入 `https://<财务机IP>:5443`
3. 浏览器提示"您的连接不是私密连接" → 点"高级" → "继续前往"
4. 进入登录页（显示"Web 访问模式"标识）
5. 用财务/稽核员/报销人账号登录

### 同一台机器可同时

- 桌面窗口：财务版（强 O12 绑定，admin 登录）
- 浏览器：稽核员 / 报销人登录
- 互不冲突（同一进程、不同 Flask 实例、不同端口）

---

## 八、安全说明

| 项 | 状态 |
|----|------|
| TLS 1.2+ 自签证书 | ✅ 强制 |
| Session cookie HttpOnly | ✅ 桌面/Web 都开 |
| Session cookie Secure | ✅ Web 模式强制 True |
| Session cookie SameSite | ✅ Lax（不能跨站） |
| 登录限速 10/min/IP | ✅ 手写 ratelimit（utils/ratelimit.py） |
| 全局限速 60/min/IP | ✅ |
| 失败 5 次锁定 30 分钟 | ✅ |
| 审计日志 | ✅ AuditLog 表（IP 为浏览器客户端 IP） |
| 客户端-角色绑定 | 桌面保留 O12；Web 放宽为白名单 |
| CSRF Token | ⚠️ 当前未实现（见下文 TODO） |
| 双因子（UKey） | ⚠️ TODO |

### 已知 TODO（v2.10.0e 之后）

- [ ] CSRF Token（推荐加，浏览器 POST 防 CSRF）
- [ ] 双因子认证（UKey / 短信）
- [ ] Nginx 反向代理模板（生产推荐）
- [ ] launcher 加 `--web` / `--no-web` CLI 参数
- [ ] Web 模式登录页增加"首次使用指引"

---

## 九、验证清单（部署后必跑）

- [ ] `https://<本机IP>:5443/health` 返回 200，且 body 含 `"access_mode":"web"`
- [ ] `https://<本机IP>:5443/web-info` 返回 200
- [ ] 浏览器登录三种角色（finance / auditor / reimburser）都能成功
- [ ] 浏览器访问 `https://<本机IP>:5443/api/auth/login` OPTIONS 预检返回 CORS 头
- [ ] 桌面窗口仍然能正常打开（双模式不冲突）
- [ ] 关闭 Web 模式（`WEB_ENABLED=false`）后，桌面仍能正常运行
- [ ] 连续失败 5 次，账号锁定 30 分钟（验证限速）
- [ ] `audit_log` 表中能看到浏览器远端 IP（不是 127.0.0.1）

---

## 十、回退方案

如果 Web 模式出问题，回退到纯桌面：

```cmd
set WEB_ENABLED=false
python launcher_finance.py
```

桌面端功能完全不变。

---

## 十一、版本说明

- **v2.10.0e**：新增财务端 Web 访问（同进程双入口）
- 关联提交：见 git log "v2.10.0e-web-access"