# Dependabot 自动依赖更新

> 启用 GitHub Dependabot 自动监控 `requirements.txt` 和 GitHub Actions 版本，生成 PR 等待人工 review。

## 1. 启用方式

配置已就位：`.github/dependabot.yml`

无需手工启用 — 推送到 GitHub 后自动生效（**Settings → Code security → Dependabot → Version updates = Enabled**）。

## 2. 监控范围

| 类型 | 范围 | 频率 | PR 上限 |
|------|------|------|---------|
| pip | `requirements.txt` | 每周一 09:00 (Asia/Shanghai) | 5 |
| github-actions | `.github/workflows/*.yml` | 每周一 10:00 (Asia/Shanghai) | 3 |

## 3. PR 分组策略

为避免 PR 风暴（一次 30+ 依赖更新），按功能分组：

| 分组 | 涵盖包 | 更新理由 |
|------|--------|----------|
| `flask` | Flask / SQLAlchemy / Werkzeug / Jinja2 / ... | Web 框架层 |
| `desktop` | pywebview / pyinstaller | 桌面壳 + 打包 |
| `crypto` | cryptography | 安全敏感，需谨慎 review |
| `db` | SQLAlchemy / greenlet | 数据访问层 |
| `report` | reportlab / xlsxwriter | 报表导出 |
| `testing` | pytest / pytest-flask / requests / flask-limiter | 测试相关 |

## 4. 标签策略

每个 Dependabot PR 自动加 2 个标签：
- `dependencies`
- `python` 或 `ci`

## 5. 处理流程

```
Dependabot 创建 PR
  ↓
CI 自动跑测试（.github/workflows/ci.yml）
  ↓
人工 review
  ├─ 测试通过 → squash merge
  └─ 测试失败 → 看错误 → 锁定版本或修补代码
```

### 5.1 关键 review 检查点

- **cryptography 更新** → 是否影响 AES-256 加密？解密存量数据是否兼容？
- **Flask / Werkzeug 更新** → 是否有 breaking change？session / cookie 行为变化？
- **pywebview 更新** → 是否需对应 webview 运行时？
- **pyinstaller 更新** → 打包脚本 `--windowed` 行为是否变？
- **SQLAlchemy 更新** → 2.x 新语法兼容？（项目用 1.x legacy API）

## 6. 自动合并（可选）

如果信任 Dependabot 通过的版本，可启用 **Settings → Allow auto-merge**：

- ✅ `flask` / `desktop` / `db` / `report` / `testing` 分组
- ❌ `crypto` 分组（需人工 review 加密变更）

## 7. 沙箱注意

**沙箱无外网** — Dependabot 在线运行，GitHub 自动完成。沙箱本地依赖经常被清空：
```bash
# 沙箱手工重装
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

## 8. 配置变更历史

| 日期 | 变更 |
|------|------|
| 2026-08-25 | 启用：每周监控 + 6 分组 + 标签 + PR 模板 |
