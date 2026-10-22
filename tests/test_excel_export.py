"""
报表 Excel 导出测试
"""
import io
import zipfile
import pytest
import requests
from threading import Thread
import time
from werkzeug.serving import make_server
from werkzeug.security import generate_password_hash
from datetime import date, datetime

from models import db
from models.models import SysUser, ExpenseProject, ExpenseBill


def login(base_url, username='admin', password='NewP@ss123'):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login',
               json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


@pytest.fixture
def report_data(app, admin_user, project):
    """测试用单据数据"""
    with app.app_context():
        # 创建报销人
        u = SysUser(
            username='r_xlsx', real_name='李四', role='reimburser',
            staff_type='在编', account_status='normal',
            department='研发部',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(u)
        db.session.flush()

        # 创建 5 张单据
        for i in range(5):
            bill = ExpenseBill(
                bill_no=f'B-XLSX-{i:03d}', user_id=u.id, project_id=project['id'],
                bill_type='personal', travel_start_date=date(2026, 1, 1),
                travel_end_date=date(2026, 1, 3), destination='北京',
                total_amount=1000 * (i + 1), capital_amount='壹仟',
                status='final_approved' if i % 2 == 0 else 'submitted',
                creator_id=u.id,
            )
            db.session.add(bill)
        db.session.commit()


def test_excel_export_project_summary(app, admin_user, report_data):
    """Excel 导出：项目汇总"""
    from services.report_service import export_project_summary_xlsx

    with app.app_context():
        data = export_project_summary_xlsx()
        assert len(data) > 0
        # xlsx 是 zip 格式
        assert data[:2] == b'PK'  # ZIP 文件头
        # 用 zipfile 验证是有效 xlsx
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert 'xl/workbook.xml' in names
            assert any('xl/worksheets/sheet1.xml' in n for n in names)


def test_excel_export_user_summary(app, admin_user, report_data):
    """Excel 导出：报销人汇总"""
    from services.report_service import export_user_summary_xlsx

    with app.app_context():
        data = export_user_summary_xlsx()
        assert data[:2] == b'PK'
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert 'xl/workbook.xml' in zf.namelist()


def test_excel_export_monthly_summary(app, admin_user, report_data):
    """Excel 导出：月度汇总"""
    from services.report_service import export_monthly_summary_xlsx

    with app.app_context():
        data = export_monthly_summary_xlsx(2026)
        assert data[:2] == b'PK'


def test_excel_export_bill_detail(app, admin_user, report_data):
    """Excel 导出：单据明细"""
    from services.report_service import export_bill_detail_xlsx

    with app.app_context():
        data = export_bill_detail_xlsx()
        assert data[:2] == b'PK'
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # 检查是否包含 sharedStrings（中文表头）
            assert 'xl/sharedStrings.xml' in zf.namelist()


def test_excel_export_comprehensive(app, admin_user, report_data):
    """Excel 导出：综合报表（多 sheet）"""
    from services.report_service import export_comprehensive_report

    with app.app_context():
        data = export_comprehensive_report(year=2026)
        assert data[:2] == b'PK'
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            # 5 个 sheet
            sheets = [n for n in names if n.startswith('xl/worksheets/sheet')]
            assert len(sheets) >= 5


def test_excel_api_endpoint_projects(live_url, app, admin_user, report_data):
    """API 端点：项目汇总 Excel"""
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/projects.xlsx')
    assert r.status_code == 200
    assert 'spreadsheetml' in r.headers['content-type']
    assert r.content[:2] == b'PK'  # xlsx = zip


def test_excel_api_endpoint_bills(live_url, app, admin_user, report_data):
    """API 端点：单据明细 Excel（带过滤）"""
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/bills.xlsx?status=final_approved')
    assert r.status_code == 200
    assert r.content[:2] == b'PK'


def test_excel_api_endpoint_comprehensive(live_url, app, admin_user, report_data):
    """API 端点：综合报表"""
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/comprehensive.xlsx?year=2026')
    assert r.status_code == 200
    assert r.content[:2] == b'PK'
    # 验证多 sheet
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        sheets = [n for n in zf.namelist() if n.startswith('xl/worksheets/sheet')]
        assert len(sheets) >= 5


def test_excel_api_forbidden_for_reimburser(live_url, app):
    """非财务不能导出"""
    with app.app_context():
        from utils.ratelimit import _limiter
        from werkzeug.security import generate_password_hash
        _limiter.clear()
        admin = SysUser.query.filter_by(username='admin').first()
        admin.password_hash = generate_password_hash('NewP@ss123')
        admin.failure_count = 0
        # 报销人
        r_user = SysUser(
            username='r_export', real_name='R', role='reimburser',
            staff_type='在编', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(r_user)
        db.session.commit()

    s = requests.Session()
    r = s.post(f'{live_url}/api/auth/login',
               json={'username': 'r_export', 'password': 'Test@001'})
    assert r.json()['code'] == 0

    r = s.get(f'{live_url}/api/reports/export/projects.xlsx')
    assert r.status_code == 403
    assert r.json()['code'] == 1


def test_excel_export_empty_data(app, admin_user):
    """空数据时也能导出（不会崩）"""
    from services.report_service import (
        export_project_summary_xlsx,
        export_user_summary_xlsx,
        export_bill_detail_xlsx,
    )

    with app.app_context():
        for fn in (export_project_summary_xlsx, export_user_summary_xlsx, export_bill_detail_xlsx):
            data = fn()
            assert data[:2] == b'PK'  # 仍能生成合法 xlsx
