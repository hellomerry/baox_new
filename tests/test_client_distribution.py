"""
v2.10.0 — 客户端分发测试

覆盖：
- export_auditor_db / export_reimburser_db / export_finance_db 数据裁剪
- build_auditor_client_package / build_reimburser_client_package 打包
- 路由：build / download / list / delete
- 角色边界：稽核员只能给自己代理的报销员打包
"""
import os
import io
import json
import zipfile
from datetime import date, timedelta

import pytest

from models import db
from models.models import (
    SysUser, ExpenseProject, ExpenseBill, UserProject, AgentAuth,
)


# ============= 单元测试：数据裁剪 =============

class TestExportAuditorDb:
    """财务 → 稽核员：数据裁剪"""

    def test_export_creates_db(self, app, tmp_path, admin_user, auditor, reimburser):
        from services.client_distribution_service import export_auditor_db
        target = str(tmp_path / "auditor_target.db")
        result = export_auditor_db(auditor['id'], target, include_finance_id=admin_user['id'])
        assert result['success']
        assert os.path.exists(target)
        assert result['users'] >= 3  # 财务 + 稽核员 + 报销人
        assert result['db_size'] > 0

    def test_export_keeps_auditor_and_reimburser(self, app, tmp_path, admin_user, auditor, reimburser):
        from services.client_distribution_service import export_auditor_db
        target = str(tmp_path / "auditor_target2.db")
        export_auditor_db(auditor['id'], target, include_finance_id=admin_user['id'])

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        user_ids = [r[0] for r in cur.execute('SELECT id FROM sys_user').fetchall()]
        assert auditor['id'] in user_ids
        assert reimburser['id'] in user_ids
        assert admin_user['id'] in user_ids  # 财务
        conn.close()

    def test_export_keeps_bills(self, app, tmp_path, admin_user, auditor, reimburser, project):
        from services.client_distribution_service import export_auditor_db
        from services.bill_service import BillService
        # 创建一张单据
        with app.app_context():
            ok, msg, bill = BillService().create_bill(
                operator_id=reimburser['id'],
                bill_data={
                    'user_id': reimburser['id'],
                    'project_id': project['id'],
                    'travel_start_date': str(date.today()),
                    'travel_end_date': str(date.today()),
                    'destination': '北京', 'transport_fee': 100,
                    'accommodation_fee': 200, 'subsidy_fee': 50,
                    'other_fee': 0, 'total_amount': 350,
                }
            )
            assert ok, f'创建单据失败: {msg}'

        target = str(tmp_path / "auditor_target3.db")
        export_auditor_db(auditor['id'], target, include_finance_id=admin_user['id'])

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        bill_count = cur.execute('SELECT COUNT(*) FROM expense_bill').fetchone()[0]
        assert bill_count >= 1
        conn.close()


class TestExportReimburserDb:
    """稽核员 → 报销员：数据裁剪"""

    def test_export_creates_db(self, app, tmp_path, auditor, reimburser):
        from services.client_distribution_service import export_reimburser_db
        target = str(tmp_path / "reimburser_target.db")
        result = export_reimburser_db(reimburser['id'], target, include_auditor_id=auditor['id'])
        assert result['success']
        assert os.path.exists(target)
        assert result['users'] == 2  # 报销员 + 稽核员

    def test_export_keeps_self_and_auditor(self, app, tmp_path, auditor, reimburser):
        from services.client_distribution_service import export_reimburser_db
        target = str(tmp_path / "reimburser_target2.db")
        export_reimburser_db(reimburser['id'], target, include_auditor_id=auditor['id'])

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        user_ids = [r[0] for r in cur.execute('SELECT id FROM sys_user').fetchall()]
        assert reimburser['id'] in user_ids
        assert auditor['id'] in user_ids
        conn.close()

    def test_export_keeps_own_bills(self, app, tmp_path, auditor, reimburser, project):
        from services.client_distribution_service import export_reimburser_db
        from services.bill_service import BillService
        with app.app_context():
            ok, msg, bill = BillService().create_bill(
                operator_id=reimburser['id'],
                bill_data={
                    'user_id': reimburser['id'],
                    'project_id': project['id'],
                    'travel_start_date': str(date.today()),
                    'travel_end_date': str(date.today()),
                    'destination': '上海', 'transport_fee': 50,
                    'accommodation_fee': 100, 'subsidy_fee': 30,
                    'other_fee': 0, 'total_amount': 180,
                }
            )
            assert ok, f'创建单据失败: {msg}'

        target = str(tmp_path / "reimburser_target3.db")
        export_reimburser_db(reimburser['id'], target, include_auditor_id=auditor['id'])

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        bills = cur.execute('SELECT user_id FROM expense_bill').fetchall()
        # 所有单据都属于自己
        for (uid,) in bills:
            assert uid == reimburser['id']
        conn.close()


class TestExportFinanceDb:
    """财务 → 财务（完整）"""

    def test_export_keeps_all(self, app, tmp_path, admin_user, auditor, reimburser):
        from services.client_distribution_service import export_finance_db
        target = str(tmp_path / "finance_target.db")
        result = export_finance_db(admin_user['id'], target)
        assert result['success']

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        user_ids = [r[0] for r in cur.execute('SELECT id FROM sys_user').fetchall()]
        assert admin_user['id'] in user_ids
        assert auditor['id'] in user_ids
        assert reimburser['id'] in user_ids
        conn.close()


# ============= 单元测试：客户端打包 =============

class TestBuildClientPackage:
    """build_auditor_client_package / build_reimburser_client_package"""

    def test_build_auditor_data_only(self, app, tmp_path, admin_user, auditor, reimburser):
        """仅测数据裁剪部分（避免复制 300MB 模板）"""
        from services.client_distribution_service import export_auditor_db
        target_db = str(tmp_path / "build_auditor_test.db")
        result = export_auditor_db(auditor['id'], target_db, include_finance_id=admin_user['id'])
        assert result['success']
        assert os.path.exists(target_db)
        assert result['db_size'] > 4096  # 至少 4KB

    def test_build_reimburser_data_only(self, app, tmp_path, auditor, reimburser):
        from services.client_distribution_service import export_reimburser_db
        target_db = str(tmp_path / "build_reimburser_test.db")
        result = export_reimburser_db(reimburser['id'], target_db, include_auditor_id=auditor['id'])
        assert result['success']
        assert result['users'] == 2


# ============= 路由测试 =============

@pytest.fixture
def auditor_client(client, auditor):
    """已登录稽核员的测试客户端"""
    r = client.post('/api/auth/login', json={'username': auditor['username'], 'password': auditor['password']})
    assert r.json['code'] == 0, f'稽核员登录失败: {r.json}'
    return client


class TestDistributionRoutes:
    """API 路由测试"""

    def test_build_auditor_unauthorized_for_auditor(self, app, auditor_client, auditor):
        """稽核员无权限生成稽核员端"""
        r = auditor_client.post(f'/api/distribution/build/auditor/{auditor["id"]}')
        assert r.status_code == 403

    def test_build_auditor_not_found(self, app, admin_client):
        r = admin_client.post('/api/distribution/build/auditor/99999')
        assert r.status_code == 404

    def test_build_auditor_wrong_role(self, app, admin_client, reimburser):
        """对报销员调用稽核员接口应失败"""
        r = admin_client.post(f'/api/distribution/build/auditor/{reimburser["id"]}')
        assert r.status_code == 400
        assert '不是稽核员' in r.json['message']

    def test_list_packages(self, app, admin_client):
        r = admin_client.get('/api/distribution/list')
        assert r.status_code == 200
        assert r.json['code'] == 0
        assert 'items' in r.json['data']

    def test_delete_not_found(self, app, admin_client):
        r = admin_client.post('/api/distribution/delete/不存在的xxx.zip')
        assert r.status_code == 404

    def test_download_invalid_filename(self, app, admin_client):
        r = admin_client.get('/api/distribution/download/../../etc/passwd')
        # secure_filename 会过滤掉 ../  → 变成 'etc_passwd'，找不到 → 404
        assert r.status_code == 404

    def test_auditor_build_reimburser_not_managed(self, app, auditor_client):
        """稽核员给非自己代理的报销员打包应被拒"""
        from werkzeug.security import generate_password_hash
        from models import db
        from models.models import SysUser
        with app.app_context():
            # 创建一个不属于该稽核员的报销员
            other = SysUser(
                username='reimb_other_for_test',
                real_name='非代理',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Other@001!'),
            )
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        r = auditor_client.post(f'/api/distribution/build/reimburser/{other_id}')
        assert r.status_code == 403

    def test_finance_build_reimburser(self, app, admin_client):
        """财务可以给无代理关系的报销员打包"""
        from werkzeug.security import generate_password_hash
        from models import db
        from models.models import SysUser
        with app.app_context():
            solo = SysUser(
                username='solo_for_build',
                real_name='独立打包',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Solo@001!'),
            )
            db.session.add(solo)
            db.session.commit()
            solo_id = solo.id

        r = admin_client.post(f'/api/distribution/build/reimburser/{solo_id}')
        # 模板不存在 → 500；用户存在 → 200
        assert r.status_code in (200, 500)
        if r.status_code == 500:
            assert '模板' in r.json.get('message', '')


# ============= 数据隔离验证 =============

class TestDataIsolation:
    """验证裁剪后的数据严格隔离"""

    def test_auditor_does_not_see_unmanaged_reimbursers_bills(self, app, tmp_path, admin_user, auditor, project, reimburser):
        """稽核员裁剪的数据不应该包含未代理报销人的单据"""
        # 创建第二个报销员（不在稽核员代理下）
        from werkzeug.security import generate_password_hash
        with app.app_context():
            other = SysUser(
                username='reimb_other',
                real_name='其他报销人',
                role='reimburser',
                staff_type='在编',
                account_status='normal',
                password_hash=generate_password_hash('Other@001!'),
            )
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        from services.client_distribution_service import export_auditor_db
        target = str(tmp_path / "auditor_isolation.db")
        export_auditor_db(auditor['id'], target, include_finance_id=admin_user['id'])

        import sqlite3
        conn = sqlite3.connect(target)
        cur = conn.cursor()
        # other_id 不应该在 sys_user 中
        in_user = cur.execute('SELECT 1 FROM sys_user WHERE id = ?', (other_id,)).fetchone()
        assert in_user is None
        conn.close()
