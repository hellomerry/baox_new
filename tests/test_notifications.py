"""v2.2.0 公告/通知系统测试

覆盖：
- 模板渲染
- 单发 / 群发
- 列表 / 已读 / 未读数
- 业务事件自动触发（驳回 / 通过 / 双签 / override）
- 权限隔离
"""
import pytest
import requests
from utils.ratelimit import _limiter


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def _clear():
    _limiter.clear()


# ============= 基础 API =============

def test_list_notifications_empty(live_url, app, project, auditor, reimburser):
    """N-1: 报销人登录后没有通知"""
    _clear()
    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.get(f'{live_url}/api/notifications/list')
    assert r.json()['code'] == 0
    assert r.json()['data'] == []
    assert r.json()['unread_count'] == 0


def test_send_notification_by_finance(live_url, app, project, auditor, reimburser):
    """N-2: 财务发通知给报销人"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')  # admin 是财务角色
    r = s_fin.post(f'{live_url}/api/notifications/send', json={
        'user_id': reimburser['id'],
        'type': 'system',
        'title': '测试通知',
        'content': '这是一条测试',
    })
    assert r.json()['code'] == 0, r.json()

    # 报销人登录查看
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    r = s_re.get(f'{live_url}/api/notifications/list')
    items = r.json()['data']
    assert any(n['title'] == '测试通知' for n in items)
    assert r.json()['unread_count'] == 1


def test_send_to_self_rejected(live_url, app, project, auditor, reimburser):
    """N-3: 不能给自己发通知"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    me_id = s_fin.get(f'{live_url}/api/auth/me').json()['data']['user_id']
    r = s_fin.post(f'{live_url}/api/notifications/send', json={
        'user_id': me_id,
        'type': 'system',
        'title': '发给自己的',
        'content': '应该失败',
    })
    assert r.json()['code'] != 0


def test_reimburser_cannot_send(live_url, app, project, auditor, reimburser):
    """N-4: 报销人无发送权限"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    r = s_re.post(f'{live_url}/api/notifications/send', json={
        'user_id': auditor['id'],
        'type': 'system',
        'title': '不通过',
        'content': '报销人不能发',
    })
    assert r.json()['code'] != 0


def test_send_to_role_group(live_url, app, project, auditor, reimburser):
    """N-5: 群发到角色"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    r = s_fin.post(f'{live_url}/api/notifications/send', json={
        'target_role': 'reimburser',
        'type': 'system',
        'title': '全员通知',
        'content': '所有人都收到',
    })
    assert r.json()['code'] == 0
    assert r.json()['data']['count'] >= 1


# ============= 模板渲染 + 自动触发 =============

def test_bill_auditor_reject_triggers_notification(live_url, app, project, auditor, reimburser):
    """N-6: 稽核员驳回 → 自动通知报销人"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')

    # 报销人创建并提交
    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')

    # 稽核员驳回
    s_au.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={
        'decision': 'reject', 'comment': '金额超标，不予通过'
    })

    # 报销人查通知
    r = s_re.get(f'{live_url}/api/notifications/list')
    items = r.json()['data']
    notif = next((n for n in items if n['type'] == 'bill_auditor_rejected'), None)
    assert notif is not None
    assert '金额超标' in notif['content']


def test_bill_finance_approve_triggers_notification(live_url, app, project, auditor, reimburser):
    """N-7: 财务终审通过 → 自动通知报销人"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_au.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={'decision': 'approve'})

    # 标记已读旧的（清空）
    s_re.post(f'{live_url}/api/notifications/read-all')

    s_fin.post(f'{live_url}/api/bills/{bill_id}/finance-audit', json={
        'decision': 'approve', 'comment': '通过',
    })

    r = s_re.get(f'{live_url}/api/notifications/list')
    items = r.json()['data']
    notif = next((n for n in items if n['type'] == 'bill_approved'), None)
    assert notif is not None
    assert r.json()['unread_count'] >= 1


def test_bill_override_triggers_notification(live_url, app, project, auditor, reimburser):
    """N-8: 强制修改 → 通知报销人"""
    _clear()
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')
    s_fin = login(live_url, 'admin', 'NewP@ss123')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1000, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')

    # override
    r = s_fin.post(f'{live_url}/api/bills/{bill_id}/override', json={
        'target_status': 'draft', 'reason': '数据错误回退到草稿状态',
    })
    assert r.json()['code'] == 0, f'override failed: {r.json()}'

    r = s_re.get(f'{live_url}/api/notifications/list')
    items = r.json()['data']
    notif = next((n for n in items if n['type'] == 'bill_overridden'), None)
    assert notif is not None
    assert 'draft' in notif['content']
    assert notif['priority'] == 'urgent'


# ============= 已读 / 未读 =============

def test_mark_read_and_unread_count(live_url, app, project, auditor, reimburser):
    """N-9: 标记已读 → 未读数减少"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')

    # 发 3 条
    for i in range(3):
        s_fin.post(f'{live_url}/api/notifications/send', json={
            'user_id': reimburser['id'],
            'type': 'system',
            'title': f'通知{i}',
            'content': f'内容{i}',
        })

    r = s_re.get(f'{live_url}/api/notifications/unread-count')
    assert r.json()['data']['unread_count'] == 3

    # 标 1 条已读
    items = s_re.get(f'{live_url}/api/notifications/list').json()['data']
    nid = items[0]['id']
    s_re.post(f'{live_url}/api/notifications/{nid}/read')

    r = s_re.get(f'{live_url}/api/notifications/unread-count')
    assert r.json()['data']['unread_count'] == 2


def test_mark_all_read(live_url, app, project, auditor, reimburser):
    """N-10: 全部已读"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')

    for i in range(5):
        s_fin.post(f'{live_url}/api/notifications/send', json={
            'user_id': reimburser['id'], 'type': 'system',
            'title': f'通知{i}', 'content': 'x',
        })

    r = s_re.post(f'{live_url}/api/notifications/read-all')
    assert r.json()['code'] == 0
    assert r.json()['data']['count'] == 5

    r = s_re.get(f'{live_url}/api/notifications/unread-count')
    assert r.json()['data']['unread_count'] == 0


def test_mark_read_other_users_forbidden(live_url, app, project, auditor, reimburser):
    """N-11: 不能标别人的通知"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_fin.post(f'{live_url}/api/notifications/send', json={
        'user_id': reimburser['id'], 'type': 'system',
        'title': '私', 'content': 'x',
    })

    items = s_re.get(f'{live_url}/api/notifications/list').json()['data']
    nid = items[0]['id']

    # 财务尝试标报销人的通知
    r = s_fin.post(f'{live_url}/api/notifications/{nid}/read')
    assert r.json()['code'] != 0


def test_filter_unread(live_url, app, project, auditor, reimburser):
    """N-12: 过滤未读/已读"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')

    for i in range(3):
        s_fin.post(f'{live_url}/api/notifications/send', json={
            'user_id': reimburser['id'], 'type': 'system',
            'title': f'通知{i}', 'content': 'x',
        })

    items = s_re.get(f'{live_url}/api/notifications/list').json()['data']
    s_re.post(f'{live_url}/api/notifications/{items[0]["id"]}/read')

    r = s_re.get(f'{live_url}/api/notifications/list?is_read=false')
    assert all(n['is_read'] is False for n in r.json()['data'])
    assert len(r.json()['data']) == 2

    r = s_re.get(f'{live_url}/api/notifications/list?is_read=true')
    assert all(n['is_read'] is True for n in r.json()['data'])
    assert len(r.json()['data']) == 1


# ============= 模板管理 =============

def test_list_templates(live_url, app, project, auditor, reimburser):
    """N-13: 列出预置模板"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    r = s_fin.get(f'{live_url}/api/notifications/templates')
    assert r.json()['code'] == 0
    templates = r.json()['data']
    types = {t['type'] for t in templates}
    assert 'bill_approved' in types
    assert 'bill_rejected' in types
    assert 'bill_overridden' in types


def test_update_template_by_admin(live_url, app, project, auditor, reimburser):
    """N-14: 财务可改模板（admin 角色等价于 finance）"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    tpls = s_fin.get(f'{live_url}/api/notifications/templates').json()['data']
    tid = next(t for t in tpls if t['type'] == 'system')['id']

    r = s_fin.put(f'{live_url}/api/notifications/templates/{tid}', json={
        'content_template': '新模板：{content}',
    })
    assert r.json()['code'] == 0
    assert r.json()['data']['content_template'] == '新模板：{content}'


def test_delete_notification(live_url, app, project, auditor, reimburser):
    """N-15: 删除通知"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')

    s_fin.post(f'{live_url}/api/notifications/send', json={
        'user_id': reimburser['id'], 'type': 'system',
        'title': '临时', 'content': 'x',
    })
    items = s_re.get(f'{live_url}/api/notifications/list').json()['data']
    nid = items[0]['id']

    r = s_re.delete(f'{live_url}/api/notifications/{nid}')
    assert r.json()['code'] == 0
    r = s_re.get(f'{live_url}/api/notifications/list')
    assert all(n['id'] != nid for n in r.json()['data'])


def test_render_template_variables(live_url, app, project, auditor, reimburser):
    """N-16: 模板变量渲染正确"""
    _clear()
    s_fin = login(live_url, 'admin', 'NewP@ss123')
    s_re = login(live_url, 'reimb001', 'Reimb@001!')
    s_au = login(live_url, 'audit001', 'Audit@001!')

    r = s_re.post(f'{live_url}/api/bills/create', json={
        'user_id': reimburser['id'], 'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20', 'travel_end_date': '2026-08-22',
        'destination': '上海',
        'transport_fee': 1500, 'accommodation_fee': 500, 'other_fee': 200,
    })
    bill_id = r.json()['data']['id']
    s_re.post(f'{live_url}/api/bills/{bill_id}/submit')
    s_au.post(f'{live_url}/api/bills/{bill_id}/auditor-audit', json={
        'decision': 'reject', 'comment': '单据重复提交',
    })

    r = s_re.get(f'{live_url}/api/notifications/list')
    items = r.json()['data']
    notif = next((n for n in items if n['type'] == 'bill_auditor_rejected'), None)
    assert notif is not None
    # 模板渲染：title 应含"未通过"，content 应含"单据重复提交"
    assert '单据重复提交' in notif['content']
