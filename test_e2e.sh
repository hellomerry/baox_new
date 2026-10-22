#!/bin/bash
# 报销稽核系统 e2e 测试（沙箱内一键运行）
# Usage: bash test_e2e.sh

set -e
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
pass() { PASS=$((PASS+1)); echo -e "${GREEN}[OK]${NC} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "${RED}[FAIL]${NC} $1"; }
warn() { WARN=$((WARN+1)); echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "========================================="
echo " 报销稽核系统 v2.10.0d e2e 测试"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# 1. Python 依赖
echo
echo "## 1. Python 依赖"
for pkg in flask flask_sqlalchemy sqlalchemy webview cryptography openpyxl reportlab xlsxwriter rapidocr_onnxruntime onnxruntime pythonnet clr_loader bottle proxy_tools flask_limiter colorama; do
  python3 -c "import importlib; importlib.import_module('${pkg//-/_}')" 2>/dev/null \
    && pass "$pkg" \
    || warn "$pkg (沙箱可缺，Windows 嵌 Python 必须有)"
done

# 2. .py 语法
echo
echo "## 2. .py 语法"
PY_COUNT=0
for py in $(find . -name "*.py" -not -path "./templates/green_client_template/*" -not -path "./dist_clients/*" -not -path "./backups/*" -not -path "./logs/*" -not -path "./__pycache__/*" -not -path "./.git/*"); do
  python3 -c "import ast; ast.parse(open('$py').read())" 2>/dev/null \
    && pass "$py" \
    || fail "$py"
  PY_COUNT=$((PY_COUNT+1))
done
echo "  (共 $PY_COUNT 个)"

# 3. JS 语法
echo
echo "## 3. JS 语法"
if [ -f static/js/app.js ]; then
  node -c static/js/app.js 2>/dev/null \
    && pass "static/js/app.js ($(wc -l < static/js/app.js) 行)" \
    || fail "static/js/app.js"
fi

# 4. 端到端功能
echo
echo "## 4. 端到端功能（启动 + 模板 + 路由 + API + 菜单）"
python3 << 'PYEOF'
import sys, os, tempfile, re
sys.path.insert(0, '.')

import config as cfg
tmpdb = tempfile.mktemp(suffix='.db')
cfg.Config.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmpdb}'
cfg.ProductionConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmpdb}'

from app import create_app
app = create_app('*')

P = F = W = 0
def ok(m): global P; P += 1; print(f'  [OK] {m}')
def bad(m): global F; F += 1; print(f'  [FAIL] {m}')
def warn(m): global W; W += 1; print(f'  [WARN] {m}')

with app.app_context():
    from init_db import init_database
    init_database()
    # 创建测试用户 audit001 + reimb001（init_database 只跑迁移，不创建用户）
    from models import db
    from models.models import SysUser
    from werkzeug.security import generate_password_hash
    if not SysUser.query.filter_by(username='audit001').first():
        a = SysUser(username='audit001', real_name='稽核员A', role='auditor',
                    account_status='normal', staff_type='在编',
                    password_hash=generate_password_hash('Audit@001!'))
        db.session.add(a)
    if not SysUser.query.filter_by(username='reimb001').first():
        r = SysUser(username='reimb001', real_name='张三', role='reimburser',
                    account_status='normal', staff_type='在编',
                    password_hash=generate_password_hash('Reimb@001!'))
        db.session.add(r)
    db.session.commit()
    ok('init_db + audit001/reimb001 创建')

with app.test_client() as c:
    body = c.get('/').data.decode('utf-8')
    if 'sidebar-menu' in body and 'login-view' in body and 'app.js' in body:
        ok(f'主页 HTML 完整 ({len(body)} bytes)')
    else:
        bad('主页缺关键元素')

routes = [(r.rule, ','.join(sorted(r.methods - {'OPTIONS', 'HEAD'})))
          for r in app.url_map.iter_rules() if r.endpoint != 'static']
ok(f'注册路由: {len(routes)}')

from config import ProductionConfig
app = create_app('*', config_class=ProductionConfig)
with app.app_context():
    from init_db import init_database
    init_database()

with app.test_client() as c:
    r = c.post('/api/auth/login', json={'username': 'admin', 'password': 'admin@2026'})
    if r.json['code'] == 0:
        ok(f'admin login: role={r.json["data"]["role"]}')
    else:
        bad(f'admin login: {r.json}')

finance_routes = [
    '/api/bills/list', '/api/projects/list', '/api/users/list',
    '/api/attendance/pending', '/api/agents/list',
    '/api/distribution/list', '/api/audit/list',
    '/api/notifications/list',
    '/api/reports/status', '/api/reports/projects',
    '/api/reports/users', '/api/reports/monthly',
]
ok_count = 0
with app.test_client() as c:
    c.post('/api/auth/login', json={'username': 'admin', 'password': 'admin@2026'})
    for path in finance_routes:
        r = c.get(path)
        if r.status_code == 200:
            ok(f'GET {path}')
            ok_count += 1
        else:
            bad(f'GET {path} -> {r.status_code}')

for user, pwd in [('audit001', 'Audit@001!'), ('reimb001', 'Reimb@001!')]:
    with app.test_client() as c:
        r = c.post('/api/auth/login', json={'username': user, 'password': pwd})
        if r.json['code'] == 0:
            ok(f'{user} login: role={r.json["data"]["role"]}')
        else:
            warn(f'{user} login: {r.json.get("message", "")[:50]}')

with open('static/js/app.js', encoding='utf-8') as f:
    js = f.read()
m = re.search(r'finance:\s*\[([\s\S]*?)\n\s*\],', js)
if m:
    items = re.findall(r"id:\s*'([^']+)',\s*label:\s*'([^']+)'", m.group(1))
    print(f'\n  finance 菜单 {len(items)} 项:')
    for id, label in items:
        print(f'    [{id:20s}] {label}')
    ids = [i for i, _ in items]
    dup = [x for x in set(ids) if ids.count(x) > 1]
    if dup:
        warn(f'重复 menu id: {dup}')
    else:
        ok('菜单 id 唯一')

print(f'\n  ## 4 总结: {P} OK, {F} FAIL, {W} WARN')
sys.exit(0 if F == 0 else 1)
PYEOF

# 总结
echo
echo "========================================="
echo " 总结"
echo "========================================="
echo -e "${GREEN}通过: $PASS${NC} | ${RED}失败: $FAIL${NC} | ${YELLOW}警告: $WARN${NC}"
[ $FAIL -eq 0 ] && echo -e "${GREEN}✓ 全部通过${NC}" && exit 0 || { echo -e "${RED}✗ 有失败${NC}"; exit 1; }
