"""
报销标准地区档测试（主线④：职务等级×人员类型×地区 三维交叉）
"""
import json
from datetime import date

import pytest
import requests

from models import db
from models.models import (
    SysUser, ExpenseStandard, PositionLevel, UserPosition, SysConfig,
)
from werkzeug.security import generate_password_hash


def login(base_url, username='admin', password='NewP@ss123'):
    s = requests.Session()
    r = s.post(f'{base_url}/api/auth/login',
               json={'username': username, 'password': password})
    assert r.json()['code'] == 0, r.json()
    return s


# ============= 地区档解析 =============

def test_resolve_region_tier_default(app, admin_user):
    with app.app_context():
        from utils.region import resolve_region_tier
        assert resolve_region_tier('北京') == 'tier1'
        assert resolve_region_tier('上海市') == 'tier1'
        assert resolve_region_tier('乌鲁木齐市') == 'tier2'
        assert resolve_region_tier('青岛') == 'tier2'
        assert resolve_region_tier('某县') == 'tier3'
        assert resolve_region_tier('') == 'tier3'
        assert resolve_region_tier(None) == 'tier3'


def test_resolve_region_tier_config_override(app, admin_user):
    with app.app_context():
        from utils.region import resolve_region_tier
        db.session.add(SysConfig(
            config_key='region_tier_map_json',
            config_value=json.dumps({'tier1': ['三亚']}),
            config_name='地区档映射覆盖',
        ))
        db.session.commit()

        assert resolve_region_tier('三亚市') == 'tier1'
        # tier1 被覆盖后内置直辖市关键词不再生效
        assert resolve_region_tier('北京') == 'tier3'
        # tier2 未覆盖 → 仍用内置
        assert resolve_region_tier('成都') == 'tier2'


# ============= 三维交叉标准选择 =============

@pytest.fixture
def positioned_reimburser(app, admin_user, project, reimburser):
    """conftest 已挂 DIVISION（处级）职务；init_db 通用标准：伙食100/住宿400"""
    with app.app_context():
        pos = PositionLevel.query.filter_by(level_code='DIVISION').first()
        assert pos
        return dict(reimburser, position_id=pos.id)


def _add_std(position_id, subsidy_type, amount, region_tier=None):
    db.session.add(ExpenseStandard(
        position_id=position_id, staff_type='在编',
        subsidy_type=subsidy_type, amount=amount,
        valid_start=date.today(), region_tier=region_tier,
    ))


def test_get_max_standard_region_override(app, positioned_reimburser, project):
    """tier1 有住宿标准 → 住宿用地区档；伙食无地区档 → 回退通用"""
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 800, region_tier='tier1')
        db.session.commit()

        from utils.validators import get_max_standard
        stds = get_max_standard(positioned_reimburser['id'], [project['id']], '北京')
        assert float(stds['住宿'].amount) == 800
        assert stds['住宿'].region_tier == 'tier1'
        assert float(stds['伙食'].amount) == 100  # init_db 通用（处级）
        assert stds['伙食'].region_tier is None


def test_get_max_standard_fallback_when_no_region_row(app, positioned_reimburser, project):
    """目的地是 tier3 且无 tier3 标准 → 全部回退通用"""
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 800, region_tier='tier1')
        db.session.commit()

        from utils.validators import get_max_standard
        stds = get_max_standard(positioned_reimburser['id'], [project['id']], '某县')
        assert float(stds['住宿'].amount) == 400  # 通用（处级）
        stds_no_dest = get_max_standard(positioned_reimburser['id'], [project['id']])
        assert float(stds_no_dest['住宿'].amount) == 400


def test_get_max_standard_other_region_not_leaked(app, positioned_reimburser, project):
    """tier2 的地区档不影响 tier1 目的地"""
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 999, region_tier='tier2')
        db.session.commit()

        from utils.validators import get_max_standard
        stds = get_max_standard(positioned_reimburser['id'], [project['id']], '北京')
        assert float(stds['住宿'].amount) == 400  # tier1 无行 → 通用，不取 tier2 的 999


def test_calc_subsidy_with_destination(app, positioned_reimburser, project):
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 800, region_tier='tier1')
        db.session.commit()

        from services.bill_service import calc_subsidy_by_high_standard
        from datetime import date as d
        # 3 天北京：伙食 100（通用回退）+ 住宿 800（tier1）
        s = calc_subsidy_by_high_standard(
            positioned_reimburser['id'], project['id'], d(2026, 7, 1), d(2026, 7, 3), '北京')
        assert s == (100 + 800) * 3

        # 无目的地：400+100
        s2 = calc_subsidy_by_high_standard(
            positioned_reimburser['id'], project['id'], d(2026, 7, 1), d(2026, 7, 3))
        assert s2 == (100 + 400) * 3


# ============= 集成：创建单据 + K4 记录 + 预览 =============

def test_create_bill_uses_region_standard(live_url, app, positioned_reimburser, project):
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 800, region_tier='tier1')
        db.session.commit()

    s = login(live_url, 'reimb001', 'Reimb@001!')
    r = s.post(f'{live_url}/api/bills/create', json={
        'user_id': positioned_reimburser['id'],
        'project_id': project['id'],
        'bill_type': 'personal',
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
        'transport_fee': 100,
    })
    assert r.json()['code'] == 0
    bill_id = r.json()['data']['id']

    with app.app_context():
        from models.models import ExpenseBill
        bill = ExpenseBill.query.get(bill_id)
        # 补贴 = (100 伙食通用 + 800 住宿 tier1) × 3 天
        assert float(bill.subsidy_fee) == (100 + 800) * 3
        assert float(bill.total_amount) == 100 + (100 + 800) * 3
        # K4 标准来源记录地区档
        src = json.loads(bill.applied_standard_source)
        assert src['region_tier'] == 'tier1'
        assert src['destination'] == '北京'
        housing = next(i for i in src['items'] if i['subsidy_type'] == '住宿')
        assert housing['region_tier'] == 'tier1'


def test_standard_preview_api_with_region(live_url, app, positioned_reimburser, project):
    with app.app_context():
        _add_std(positioned_reimburser['position_id'], '住宿', 800, region_tier='tier1')
        db.session.commit()

    s = login(live_url, 'admin', 'NewP@ss123')
    r = s.post(f'{live_url}/api/bills/standard-preview', json={
        'user_id': positioned_reimburser['id'],
        'project_id': project['id'],
        'travel_start_date': '2026-08-20',
        'travel_end_date': '2026-08-22',
        'destination': '北京',
    })
    data = r.json()['data']
    assert data['region_tier'] == 'tier1'
    assert '一类地区' in data['region_tier_name']
    assert data['subsidy_fee'] == (100 + 800) * 3


def test_standards_crud_with_region(live_url, app, admin_user, project):
    s = login(live_url)
    r = s.post(f'{live_url}/api/standards/create', json={
        'position_id': None, 'staff_type': '在编', 'subsidy_type': '住宿',
        'amount': 500, 'region_tier': 'tier2',
    })
    assert r.json()['code'] == 0
    std_id = r.json()['data']['id']

    r = s.get(f'{live_url}/api/standards/list?region_tier=tier2')
    items = r.json()['data']
    assert any(i['id'] == std_id and i['region_tier'] == 'tier2'
               and '二类地区' in i['region_tier_name'] for i in items)

    # 更新为通用
    r = s.post(f'{live_url}/api/standards/{std_id}', json={'region_tier': None})
    assert r.json()['code'] == 0
    r = s.get(f'{live_url}/api/standards/list?region_tier=tier2')
    assert not any(i['id'] == std_id for i in r.json()['data'])
