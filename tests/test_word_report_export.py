"""
Word 报表导出测试（v2.11.0：项目/报销人/月度/单据明细/综合）
"""
import io
import zipfile
from datetime import date

import pytest
import requests

from models import db
from models.models import SysUser, ExpenseBill
from werkzeug.security import generate_password_hash


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
        u = SysUser(
            username='r_wdocx', real_name='李四', role='reimburser',
            staff_type='在编', account_status='normal',
            department='研发部',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(u)
        db.session.flush()

        for i in range(5):
            bill = ExpenseBill(
                bill_no=f'B-WDOCX-{i:03d}', user_id=u.id, project_id=project['id'],
                bill_type='personal', travel_start_date=date(2026, 1, 1),
                travel_end_date=date(2026, 1, 3), destination='北京',
                total_amount=1000 * (i + 1), capital_amount='壹仟',
                status='final_approved' if i % 2 == 0 else 'submitted',
                creator_id=u.id,
            )
            db.session.add(bill)
        db.session.commit()


def _docx_xml(data: bytes) -> str:
    """校验 docx 字节流并返回 document.xml 文本"""
    assert data[:2] == b'PK'
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert 'word/document.xml' in zf.namelist()
        return zf.read('word/document.xml').decode('utf-8')


# ============= 单元测试 =============

def test_project_summary_docx(app, admin_user, report_data):
    with app.app_context():
        from utils.word_report import export_project_summary_docx
        xml = _docx_xml(export_project_summary_docx())
        assert '项目维度' in xml
        assert '项目编号' in xml and '项目名称' in xml
        assert 'TEST01' in xml  # conftest 项目编码
        assert '合计' in xml


def test_user_summary_docx(app, admin_user, report_data):
    with app.app_context():
        from utils.word_report import export_user_summary_docx
        xml = _docx_xml(export_user_summary_docx())
        assert '报销人维度' in xml
        assert '李四' in xml and '研发部' in xml
        assert '合计' in xml


def test_monthly_summary_docx(app, admin_user, report_data):
    with app.app_context():
        from utils.word_report import export_monthly_summary_docx
        xml = _docx_xml(export_monthly_summary_docx(2026))
        # 12 个月补全 + 合计
        for m in range(1, 13):
            assert f'2026-{m:02d}' in xml
        assert '合计' in xml


def test_bill_detail_docx(app, admin_user, report_data):
    with app.app_context():
        from utils.word_report import export_bill_detail_docx
        xml = _docx_xml(export_bill_detail_docx())
        assert 'B-WDOCX-000' in xml
        assert '单据编号' in xml and '状态' in xml
        assert '共 5 单' in xml

        # 状态过滤
        xml2 = _docx_xml(export_bill_detail_docx(status='final_approved'))
        assert '共 3 单' in xml2


def test_comprehensive_docx(app, admin_user, report_data):
    with app.app_context():
        from utils.word_report import export_comprehensive_docx
        xml = _docx_xml(export_comprehensive_docx(year=2026))
        for sec in ('项目汇总', '报销人汇总', '月度汇总', '状态分布', '单据明细'):
            assert sec in xml
        assert '综合报表' in xml


def test_empty_data_no_crash(app, admin_user):
    """空数据时也能导出"""
    with app.app_context():
        from utils.word_report import (
            export_project_summary_docx, export_user_summary_docx,
            export_monthly_summary_docx, export_bill_detail_docx,
            export_comprehensive_docx,
        )
        for fn in (export_project_summary_docx, export_user_summary_docx,
                   export_bill_detail_docx):
            xml = _docx_xml(fn())
            assert '无数据' in xml
        _docx_xml(export_monthly_summary_docx(2026))
        _docx_xml(export_comprehensive_docx(year=2026))


# ============= API 端点测试 =============

def test_api_export_projects_docx(live_url, app, admin_user, report_data):
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/projects.docx')
    assert r.status_code == 200
    assert 'wordprocessingml' in r.headers['content-type']
    assert r.content[:2] == b'PK'


def test_api_export_bills_docx_with_filter(live_url, app, admin_user, report_data):
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/bills.docx?status=final_approved')
    assert r.status_code == 200
    assert r.content[:2] == b'PK'


def test_api_export_comprehensive_docx(live_url, app, admin_user, report_data):
    s = login(live_url)
    r = s.get(f'{live_url}/api/reports/export/comprehensive.docx?year=2026')
    assert r.status_code == 200
    assert r.content[:2] == b'PK'
    xml = _docx_xml(r.content)
    assert '单据明细' in xml


def test_api_docx_forbidden_for_reimburser(live_url, app):
    """非财务不能导出"""
    with app.app_context():
        from utils.ratelimit import _limiter
        _limiter.clear()
        r_user = SysUser(
            username='r_wdocx_export', real_name='R', role='reimburser',
            staff_type='在编', account_status='normal',
            password_hash=generate_password_hash('Test@001'),
        )
        db.session.add(r_user)
        db.session.commit()

    s = requests.Session()
    r = s.post(f'{live_url}/api/auth/login',
               json={'username': 'r_wdocx_export', 'password': 'Test@001'})
    assert r.json()['code'] == 0

    r = s.get(f'{live_url}/api/reports/export/projects.docx')
    assert r.status_code == 403
