"""v2.3.0 数据导入向导测试"""
import io
import pytest
import requests
import openpyxl
from utils.ratelimit import _limiter
from services.data_import_service import do_import
from models.models import db, SysUser, ExpenseProject, ExpenseStandard, DataImportLog


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def _clear():
    _limiter.clear()


def _make_xlsx_bytes(rows_data, sheet_name='用户'):
    """生成测试用 xlsx bytes"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows_data:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============= 模板下载 =============

def test_list_templates(live_url, app, project, auditor, reimburser):
    """DI-1: 列出所有模板元信息"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/templates')
    assert r.json()['code'] == 0
    types = {t['type'] for t in r.json()['data']}
    assert 'user' in types
    assert 'project' in types
    assert 'standard' in types


def test_download_template(live_url, app, project, auditor, reimburser):
    """DI-2: 下载 user 模板"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/template/user')
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('application/vnd.openxml')


def test_download_invalid_template(live_url, app, project, auditor, reimburser):
    """DI-3: 下载未知类型 → 400"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/template/xxx')
    assert r.json()['code'] != 0


def test_auditor_cannot_download(live_url, app, project, auditor, reimburser):
    """DI-4: 稽核员不能下载模板"""
    _clear()
    s = login(live_url, 'audit001', 'Audit@001!')
    r = s.get(f'{live_url}/api/data-import/template/user')
    assert r.status_code == 403


# ============= 预览（解析）=============

def test_preview_valid_users(live_url, app, project, auditor, reimburser):
    """DI-5: 预览合法用户数据"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    xlsx = _make_xlsx_bytes([
        ['username', 'real_name', 'role', 'staff_type', 'phone'],
        ['zhangsan', '张三', 'reimburser', '在编', '13800138000'],
        ['lisi', '李四', 'auditor', '在编', '13900139000'],
    ], sheet_name='用户')
    files = {'file': ('test.xlsx', xlsx, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    data = {'import_type': 'user'}
    r = s.post(f'{live_url}/api/data-import/preview', files=files, data=data)
    assert r.json()['code'] == 0, r.json()
    res = r.json()['data']
    assert res['total_rows'] == 2
    assert res['valid_count'] == 2
    assert res['invalid_count'] == 0


def test_preview_invalid_role(live_url, app, project, auditor, reimburser):
    """DI-6: 非法角色 → 错误"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    xlsx = _make_xlsx_bytes([
        ['username', 'real_name', 'role', 'staff_type'],
        ['baduser', '非法', 'superuser', '在编'],
    ], sheet_name='用户')
    files = {'file': ('test.xlsx', xlsx, 'application/octet-stream')}
    data = {'import_type': 'user'}
    r = s.post(f'{live_url}/api/data-import/preview', files=files, data=data)
    res = r.json()['data']
    assert res['invalid_count'] >= 1
    assert any('角色' in e for r in res['rows'] for e in r['_errors'])


def test_preview_missing_required(live_url, app, project, auditor, reimburser):
    """DI-7: 缺必填 → 错误"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    xlsx = _make_xlsx_bytes([
        ['username', 'real_name', 'role', 'staff_type'],
        ['', '无名', 'reimburser', '在编'],  # username 空
    ], sheet_name='用户')
    files = {'file': ('test.xlsx', xlsx, 'application/octet-stream')}
    r = s.post(f'{live_url}/api/data-import/preview', files=files, data={'import_type': 'user'})
    res = r.json()['data']
    assert res['invalid_count'] == 1
    assert any('必填' in e for e in res['rows'][0]['_errors'])


def test_preview_invalid_type(live_url, app, project, auditor, reimburser):
    """DI-8: 未知 import_type → 400"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    xlsx = _make_xlsx_bytes([['a']], sheet_name='x')
    files = {'file': ('test.xlsx', xlsx, 'application/octet-stream')}
    r = s.post(f'{live_url}/api/data-import/preview', files=files, data={'import_type': 'xxx'})
    assert r.json()['code'] != 0


# ============= 确认导入 =============

def test_commit_users(live_url, app, project, auditor, reimburser):
    """DI-9: 提交导入用户"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    rows = [
        {
            'username': 'newuser1', 'real_name': '新用户1',
            'role': 'reimburser', 'staff_type': '在编',
            'phone': '13800000001', '_row': 2, '_valid': True, '_errors': [],
        },
        {
            'username': 'newuser2', 'real_name': '新用户2',
            'role': 'auditor', 'staff_type': '在编',
            '_row': 3, '_valid': True, '_errors': [],
        },
    ]
    r = s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'user',
        'rows': rows,
        'file_hash': 'abc123',
        'file_size': 1024,
        'file_name': 'test.xlsx',
    })
    assert r.json()['code'] == 0, r.json()
    log = r.json()['data']
    assert log['success_count'] == 2
    assert log['failed_count'] == 0
    assert log['status'] == 'success'

    # 验证 user 真的建了
    r = s.get(f'{live_url}/api/users/list')
    usernames = {u['username'] for u in r.json()['data']}
    assert 'newuser1' in usernames
    assert 'newuser2' in usernames


def test_commit_duplicate_user(live_url, app, project, auditor, reimburser):
    """DI-10: 重复用户名 → 失败"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    rows = [{
        'username': 'reimb001',  # 已存在
        'real_name': '重复',
        'role': 'reimburser', 'staff_type': '在编',
        '_row': 2, '_valid': True, '_errors': [],
    }]
    r = s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'user',
        'rows': rows, 'file_hash': 'h', 'file_size': 0, 'file_name': 'x.xlsx',
    })
    assert r.json()['code'] == 0
    log = r.json()['data']
    assert log['success_count'] == 0
    assert log['failed_count'] == 1
    assert log['status'] == 'failed'


def test_commit_projects(live_url, app, project, auditor, reimburser):
    """DI-11: 导入项目"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    rows = [
        {
            'project_code': 'BULK001', 'project_name': '批量项目1',
            'project_type': '科研', 'start_date': '2026-01-01',
            'end_date': '2026-12-31', 'finance_username': 'admin',
            '_row': 2, '_valid': True, '_errors': [],
        },
    ]
    r = s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'project', 'rows': rows,
        'file_hash': 'h', 'file_size': 0, 'file_name': 'x.xlsx',
    })
    assert r.json()['code'] == 0, r.json()
    assert r.json()['data']['success_count'] == 1


def test_commit_standards(live_url, app, project, auditor, reimburser):
    """DI-12: 导入标准"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    rows = [
        {
            'position_code': 'BUREAU', 'staff_type': '在编',
            'subsidy_type': '交通', 'amount': 200, 'remark': '测试',
            '_row': 2, '_valid': True, '_errors': [],
        },
    ]
    r = s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'standard', 'rows': rows,
        'file_hash': 'h', 'file_size': 0, 'file_name': 'x.xlsx',
    })
    assert r.json()['code'] == 0, r.json()
    assert r.json()['data']['success_count'] == 1


def test_commit_empty_rows(live_url, app, project, auditor, reimburser):
    """DI-13: 空 rows → 400"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'user', 'rows': [],
        'file_hash': 'h', 'file_size': 0, 'file_name': 'x.xlsx',
    })
    assert r.json()['code'] != 0


# ============= 历史 =============

def test_history_list(live_url, app, project, auditor, reimburser):
    """DI-14: 导入历史列表"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    # 先做一次
    rows = [{'username': 'h_user1', 'real_name': 'H', 'role': 'reimburser',
             'staff_type': '在编', '_row': 2, '_valid': True, '_errors': []}]
    s.post(f'{live_url}/api/data-import/commit', json={
        'import_type': 'user', 'rows': rows,
        'file_hash': 'h', 'file_size': 0, 'file_name': 'x.xlsx',
    })

    r = s.get(f'{live_url}/api/data-import/history?limit=10')
    assert r.json()['code'] == 0
    items = r.json()['data']
    assert any(i['file_name'] == 'x.xlsx' for i in items)


def test_history_filter_by_type(live_url, app, project, auditor, reimburser):
    """DI-15: 按类型过滤"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/history?import_type=user')
    assert r.json()['code'] == 0
    assert all(i['import_type'] == 'user' for i in r.json()['data'])


def test_history_detail(live_url, app, project, auditor, reimburser):
    """DI-16: 历史详情"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/history?limit=1')
    items = r.json()['data']
    if not items:
        return
    log_id = items[0]['id']
    r = s.get(f'{live_url}/api/data-import/history/{log_id}')
    assert r.json()['code'] == 0
    assert r.json()['data']['id'] == log_id


def test_history_detail_not_found(live_url, app, project, auditor, reimburser):
    """DI-17: 历史不存在 → 404"""
    _clear()
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/data-import/history/99999')
    assert r.json()['code'] != 0


# ============= 权限 =============

def test_reimburser_cannot_preview(live_url, app, project, auditor, reimburser):
    """DI-18: 报销人不能上传预览"""
    _clear()
    s = login(live_url, 'reimb001', 'Reimb@001!')
    xlsx = _make_xlsx_bytes([['a', 'b']], sheet_name='x')
    files = {'file': ('test.xlsx', xlsx, 'application/octet-stream')}
    r = s.post(f'{live_url}/api/data-import/preview', files=files, data={'import_type': 'user'})
    assert r.status_code == 403
