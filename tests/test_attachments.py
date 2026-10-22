"""
附件 + 自然人测试
- 使用 live_url
"""
import io
import os
import pytest
import requests
from datetime import date
from threading import Thread
import time
from werkzeug.serving import make_server

from models import db
from models.models import (
    SysUser, ExpenseProject, UserProject, ExpenseBill, Attachment,
    AgentAuth, PositionLevel, UserPosition
)
from werkzeug.security import generate_password_hash
from config import Config


@pytest.fixture
def live_url(app):
    from threading import Thread
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, app)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    yield f'http://127.0.0.1:{port}'
    server.shutdown()


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


def create_bill_for_test(app, project_id, creator_id, total=1000):
    """在 app 上下文里直接创建 bill，返回 bill_id"""
    with app.app_context():
        b = ExpenseBill(
            bill_no=f'B-TEST-{int(time.time() * 1000) % 100000}',
            user_id=creator_id, project_id=project_id, bill_type='personal',
            travel_start_date=date(2026, 1, 1), travel_end_date=date(2026, 1, 2),
            destination='北京', total_amount=total, capital_amount='壹仟元整',
            status='draft', creator_id=creator_id,
        )
        db.session.add(b)
        db.session.commit()
        return b.id


def test_attach_upload(live_url, app, project):
    """附件上传"""
    bill_id = create_bill_for_test(app, project['id'], 1)

    s = login(live_url, 'admin', 'NewP@ss123')
    fake_data = b'fake png content'
    r = s.post(
        f'{live_url}/api/attachments/upload/{bill_id}',
        files={'file': ('test.png', io.BytesIO(fake_data), 'image/png')},
    )
    assert r.json()['code'] == 0, r.json()


def test_attach_list(live_url, app, project):
    """列出附件"""
    bill_id = create_bill_for_test(app, project['id'], 1)

    s = login(live_url, 'admin', 'NewP@ss123')
    for i in range(2):
        r = s.post(
            f'{live_url}/api/attachments/upload/{bill_id}',
            files={'file': (f'f{i}.png', io.BytesIO(b'\x89PNG\r\n\x1a\n' + f'content {i}'.encode() * 10), 'image/png')},
        )
        assert r.json()['code'] == 0, r.json()

    r = s.get(f'{live_url}/api/attachments/list/{bill_id}')
    assert r.json()['code'] == 0
    assert len(r.json()['data']) == 2


def test_attach_verify_intact(live_url, app, project):
    """附件完整性校验：未被篡改"""
    bill_id = create_bill_for_test(app, project['id'], 1)

    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.post(
        f'{live_url}/api/attachments/upload/{bill_id}',
        files={'file': ('a.png', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'original' * 100), 'image/png')},
    )
    assert r.json()['code'] == 0, r.json()
    att_id = r.json()['data']['id']

    r = s.get(f'{live_url}/api/attachments/{att_id}/verify')
    assert r.json()['code'] == 0
    assert r.json()['data']['valid'] is True


def test_attach_verify_tampered(live_url, app, project):
    """附件完整性校验：被篡改"""
    bill_id = create_bill_for_test(app, project['id'], 1)

    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.post(
        f'{live_url}/api/attachments/upload/{bill_id}',
        files={'file': ('b.png', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'original' * 100), 'image/png')},
    )
    assert r.json()['code'] == 0, r.json()
    att_id = r.json()['data']['id']

    # 直接改文件
    with app.app_context():
        att = Attachment.query.get(att_id)
        full_path = Config.BASE_DIR / att.file_path
        full_path.write_bytes(b'tampered content!')

    r = s.get(f'{live_url}/api/attachments/{att_id}/verify')
    # 篡改 → code=1, valid=False
    assert r.json()['data']['valid'] is False
    assert '篡改' in r.json()['message']


def test_natural_person_key():
    """C4：自然人 key 一致性"""
    from services.natural_person_service import compute_natural_person_key
    k1 = compute_natural_person_key('110101199001011234')
    k2 = compute_natural_person_key('110101199001011234')
    assert k1 == k2
    assert len(k1) == 64

    # 不同人 → 不同 key
    k3 = compute_natural_person_key('110101199001011235')
    assert k1 != k3

    # 短身份证返回空
    k_short = compute_natural_person_key('12345')
    assert k_short == ''

    # 空
    assert compute_natural_person_key('') == ''


def test_same_natural_person_query(live_url, app):
    """C4：同一自然人查询"""
    from services.natural_person_service import compute_natural_person_key
    from utils.ratelimit import _limiter
    with app.app_context():
        # 重置 admin + 清空限速
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = generate_password_hash('NewP@ss123')
        admin.failure_count = 0
        admin.locked_until = None
        _limiter.clear()
        db.session.commit()

        shared_key = compute_natural_person_key('110101199001011234')
        u1 = SysUser(
            username='r_a', real_name='A', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('A@001!'),
            natural_person_key=shared_key,
        )
        u2 = SysUser(
            username='r_b', real_name='B', role='reimburser', staff_type='在编',
            account_status='normal', password_hash=generate_password_hash('B@001!'),
            natural_person_key=shared_key,
        )
        db.session.add_all([u1, u2])
        db.session.commit()
        u1_id = u1.id

    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.get(f'{live_url}/api/users/{u1_id}/same-natural')
    assert r.json()['code'] == 0
    assert len(r.json()['data']) == 1
    assert r.json()['data'][0]['username'] == 'r_b'
