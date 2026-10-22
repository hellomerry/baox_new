"""
T3 .rbag 包 API 测试
- 使用 live_url 支持上传文件
"""
import io
import os
import zipfile
import pytest
import requests
from threading import Thread
import time
from werkzeug.serving import make_server

from utils.rbag import build_package


# live_url 改用 conftest.py 的（已带 admin reset）


def login(base_url, username, password):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login', json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


@pytest.fixture
def package_data():
    return build_package(
        package_type='test',
        payload={'data': 'hello', 'user_data': {'id_card': '110101199001011234'}},
        creator_account='tester',
        creator_role='auditor',
        source_client='auditor-001',
        target_role='finance',
        desensitize=True,
    )


def test_export_package(live_url, package_data):
    """导出 .rbag 包"""
    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.post(f'{live_url}/api/packages/export', json={
        'package_type': 'test',
        'payload': {'data': 'hello'},
        'target_role': 'finance',
    })
    assert r.json()['code'] == 0
    assert 'file_path' in r.json()['data']


def test_import_package(live_url, package_data, tmp_path):
    """导入 .rbag 包"""
    file_path = tmp_path / 'test.rbag'
    file_path.write_bytes(package_data)

    s = login(live_url, 'admin', 'NewP@ss123')
    with open(file_path, 'rb') as f:
        r = s.post(
            f'{live_url}/api/packages/import',
            files={'file': (file_path.name, f, 'application/octet-stream')},
        )
    assert r.json()['code'] == 0, r.json()
    assert 'package_id' in r.json()['data']


def test_import_duplicate(live_url, package_data, tmp_path):
    """重复导入被拒"""
    file_path = tmp_path / 'test.rbag'
    file_path.write_bytes(package_data)

    s = login(live_url, 'admin', 'NewP@ss123')
    with open(file_path, 'rb') as f:
        r1 = s.post(
            f'{live_url}/api/packages/import',
            files={'file': (file_path.name, f, 'application/octet-stream')},
        )
    assert r1.json()['code'] == 0

    with open(file_path, 'rb') as f:
        r2 = s.post(
            f'{live_url}/api/packages/import',
            files={'file': (file_path.name, f, 'application/octet-stream')},
        )
    assert r2.json()['code'] == 1
    assert '已导入' in r2.json()['message']


def test_import_wrong_extension(live_url, tmp_path):
    """非 .rbag 文件被拒"""
    file_path = tmp_path / 'test.txt'
    file_path.write_text('hello')

    s = login(live_url, 'admin', 'NewP@ss123')
    with open(file_path, 'rb') as f:
        r = s.post(
            f'{live_url}/api/packages/import',
            files={'file': (file_path.name, f, 'application/octet-stream')},
        )
    assert r.json()['code'] == 1


def test_list_imported(live_url, package_data, tmp_path):
    """列出已导入"""
    file_path = tmp_path / 'test.rbag'
    file_path.write_bytes(package_data)

    s = login(live_url, 'admin', 'NewP@ss123')
    with open(file_path, 'rb') as f:
        s.post(
            f'{live_url}/api/packages/import',
            files={'file': (file_path.name, f, 'application/octet-stream')},
        )

    r = s.get(f'{live_url}/api/packages/list')
    assert r.json()['code'] == 0
    assert r.json()['data']['total'] >= 1


def test_import_tampered_rejected(live_url, tmp_path):
    """篡改的包被拒"""
    pkg = build_package(
        package_type='test', payload={'a': 1},
        creator_account='t', creator_role='r', source_client='c', target_role='finance',
    )
    buf = io.BytesIO(pkg)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, 'r') as zin, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item == 'data.json':
                data = zin.read(item).replace(b'1', b'2')
                zout.writestr(item, data)
            else:
                zout.writestr(item, zin.read(item))
    tampered_path = tmp_path / 'tampered.rbag'
    tampered_path.write_bytes(out.getvalue())

    s = login(live_url, 'admin', 'NewP@ss123')
    with open(tampered_path, 'rb') as f:
        r = s.post(
            f'{live_url}/api/packages/import',
            files={'file': (tampered_path.name, f, 'application/octet-stream')},
        )
    assert r.json()['code'] == 1
    assert '校验失败' in r.json()['message']
