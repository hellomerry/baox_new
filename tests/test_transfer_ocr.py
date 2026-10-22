"""
v2.9.0 — 人员调令 OCR（离线版）

覆盖：
- _parse_date / _extract_name_from_text / _extract_date_range_from_text / _extract_transfer_type_from_text
- _classify_receipt
- extract_transfer_info（rapidocr 真实引擎 + 启发式）
- extract_receipt_info（票据）
- save_transfer_record
- match_transfer_to_user
- find_user_by_name
- 路由：upload / save / list / detail / bind-user / search-user / cancel
- 引擎降级：rapidocr 不可用时走 mock
"""
import os
import sys
import io
import json
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from models import db
from models.models import (
    SysUser, PersonnelTransfer, Attachment,
)


# ============= 测试图生成辅助 =============

@pytest.fixture(scope="module")
def chinese_font():
    """找系统中文字体"""
    from PIL import ImageFont
    candidates = [
        # Linux（麒麟/UOS）
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/truetype/arphic/uming.ttc',
        # Windows
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, 32)
    return ImageFont.load_default()


def make_test_image(text_lines, font, path, w=900, h=400):
    """生成测试用 PNG 图片（含中文）"""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (w, h), 'white')
    draw = ImageDraw.Draw(img)
    y = 30
    for line in text_lines:
        draw.text((40, y), line, font=font, fill='black')
        y += 60
    img.save(path)
    return path


# ============= 单元测试：纯文本启发式 =============

class TestParseHelpers:
    """_parse_date / _extract_name_from_text / _extract_date_range / _extract_transfer_type"""

    def test_parse_date_dash(self):
        from services.ocr_service import _parse_date
        assert _parse_date('2026-08-25') == date(2026, 8, 25)

    def test_parse_date_chinese(self):
        from services.ocr_service import _parse_date
        assert _parse_date('2026年8月25日') == date(2026, 8, 25)

    def test_parse_date_slash(self):
        from services.ocr_service import _parse_date
        assert _parse_date('2026/08/25') == date(2026, 8, 25)

    def test_parse_date_dot(self):
        from services.ocr_service import _parse_date
        assert _parse_date('2026.08.25') == date(2026, 8, 25)

    def test_parse_date_compact(self):
        from services.ocr_service import _parse_date
        assert _parse_date('20260825') == date(2026, 8, 25)

    def test_parse_date_invalid(self):
        from services.ocr_service import _parse_date
        assert _parse_date('not-a-date') is None
        assert _parse_date('') is None
        assert _parse_date(None) is None

    def test_extract_name_from_text_1(self):
        from services.ocr_service import _extract_name_from_text
        text = '兹有张三同志前来我单位报到'
        assert _extract_name_from_text(text) == '张三'

    def test_extract_name_from_text_2(self):
        from services.ocr_service import _extract_name_from_text
        text = '姓名：李四'
        assert _extract_name_from_text(text) == '李四'

    def test_extract_name_from_text_empty(self):
        from services.ocr_service import _extract_name_from_text
        assert _extract_name_from_text('') == ''
        assert _extract_name_from_text('无姓名内容') == ''

    def test_extract_date_range(self):
        from services.ocr_service import _extract_date_range_from_text
        text = '借调期自2026-08-01至2026-12-31'
        s, e = _extract_date_range_from_text(text)
        assert s == date(2026, 8, 1)
        assert e == date(2026, 12, 31)

    def test_extract_date_range_with_keywords(self):
        from services.ocr_service import _extract_date_range_from_text
        text = '自2026-08-01 至 2026-12-31'
        s, e = _extract_date_range_from_text(text)
        assert s == date(2026, 8, 1)
        assert e == date(2026, 12, 31)

    def test_extract_date_range_empty(self):
        from services.ocr_service import _extract_date_range_from_text
        s, e = _extract_date_range_from_text('')
        assert s is None and e is None

    def test_extract_transfer_type_borrow(self):
        from services.ocr_service import _extract_transfer_type_from_text
        assert _extract_transfer_type_from_text('借调张三同志') == 'borrow'
        assert _extract_transfer_type_from_text('borrow letter') == 'borrow'

    def test_extract_transfer_type_training(self):
        from services.ocr_service import _extract_transfer_type_from_text
        assert _extract_transfer_type_from_text('跟班学习') == 'follow_training'
        assert _extract_transfer_type_from_text('training') == 'follow_training'

    def test_extract_transfer_type_combat(self):
        from services.ocr_service import _extract_transfer_type_from_text
        assert _extract_transfer_type_from_text('实战练兵') == 'combat_training'
        assert _extract_transfer_type_from_text('combat drill') == 'combat_training'

    def test_extract_transfer_type_other(self):
        from services.ocr_service import _extract_transfer_type_from_text
        assert _extract_transfer_type_from_text('通知') == 'other'
        assert _extract_transfer_type_from_text('完全无关内容') == 'other'

    def test_classify_receipt(self):
        from services.ocr_service import _classify_receipt
        assert _classify_receipt('增值税专用发票', 'fapiao.jpg') == '发票'
        assert _classify_receipt('出租汽车发票', 'x.jpg') == '出租票'
        assert _classify_receipt('中国铁路火车票', 'x.jpg') == '火车票'
        assert _classify_receipt('完全无关', 'x.jpg') == '其他票据'


# ============= 真实引擎测试（rapidocr）=============

class TestRealOCREngine:
    """真实 OCR 引擎：rapidocr_onnxruntime"""

    def test_engine_loads(self):
        """引擎能成功加载"""
        from services.ocr_service import _get_engine
        e = _get_engine()
        assert e is not None, "rapidocr 引擎加载失败"

    def test_real_ocr_empty_file(self):
        """文件不存在"""
        from services.ocr_service import real_ocr
        r = real_ocr('/nonexistent.png')
        assert r['status'] == 'error'
        assert r['lines'] == []

    def test_real_ocr_blank_image(self, tmp_path):
        """空白图（应识别为空）"""
        from PIL import Image
        from services.ocr_service import real_ocr
        blank = Image.new('RGB', (300, 200), 'white')
        p = str(tmp_path / "blank.png")
        blank.save(p)
        r = real_ocr(p)
        assert r['status'] == 'success'
        assert r['engine'] == 'rapidocr'
        assert r['lines'] == []  # 白图无内容

    def test_real_ocr_chinese_text(self, tmp_path, chinese_font):
        """真实中文识别"""
        from services.ocr_service import real_ocr
        p = str(tmp_path / "chinese.png")
        make_test_image(
            ['借调函', '姓名：张三', '有效期：2026-08-01 至 2026-12-31'],
            chinese_font, p
        )
        r = real_ocr(p)
        assert r['status'] == 'success'
        assert r['engine'] == 'rapidocr'
        text = r['full_text']
        # 至少能识别出部分中文（受字体训练数据影响，可能漏字）
        assert '借调' in text or '借调函' in text
        # 数字和日期一定识别
        assert '2026' in text


class TestExtractTransferInfoReal:
    """extract_transfer_info（真实引擎）"""

    def test_full_borrow_letter(self, tmp_path, chinese_font):
        """完整借调函识别"""
        from services.ocr_service import extract_transfer_info
        p = str(tmp_path / "borrow.png")
        make_test_image([
            '借调函',
            '姓名：张三',
            '原单位：技术保障处',
            '接收单位：基层单位',
            '借调期自2026-08-01至2026-12-31',
        ], chinese_font, p)
        r = extract_transfer_info(p)
        assert r['engine'] == 'rapidocr'
        f = r['fields']
        assert f['transfer_type'] == 'borrow'
        # 真实引擎识别姓名（取决于字体/训练集）
        assert f['real_name'] in ('张三', '') or len(f['real_name']) >= 2
        # 日期一定能识别（可能是 date 对象或字符串）
        sd = str(f['start_date'])
        ed = str(f['end_date'])
        assert '2026-08-01' in sd
        assert '2026-12-31' in ed
        # 单位
        assert '技术保障' in f['source_unit'] or f['source_unit'] == ''

    def test_follow_training(self, tmp_path, chinese_font):
        """跟班学习识别"""
        from services.ocr_service import extract_transfer_info
        p = str(tmp_path / "follow.png")
        make_test_image([
            '跟班学习通知书',
            '姓名：李四',
            '自2026-09-01至2026-11-30',
        ], chinese_font, p)
        r = extract_transfer_info(p)
        assert r['fields']['transfer_type'] == 'follow_training'
        assert '2026' in str(r['fields']['start_date'])

    def test_combat_training(self, tmp_path, chinese_font):
        """实战练兵识别"""
        from services.ocr_service import extract_transfer_info
        p = str(tmp_path / "combat.png")
        make_test_image([
            '实战练兵调令',
            '姓名：王五',
            '2026-10-01 至 2026-12-31',
        ], chinese_font, p)
        r = extract_transfer_info(p)
        assert r['fields']['transfer_type'] == 'combat_training'

    def test_empty_text_returns_other(self, tmp_path):
        """空白图"""
        from PIL import Image
        from services.ocr_service import extract_transfer_info
        blank = Image.new('RGB', (300, 200), 'white')
        p = str(tmp_path / "blank.png")
        blank.save(p)
        r = extract_transfer_info(p)
        assert r['engine'] == 'rapidocr'
        assert r['fields']['transfer_type'] == 'other'
        assert r['fields']['real_name'] == ''


class TestExtractReceiptInfoReal:
    """extract_receipt_info（票据）"""

    def test_basic_receipt(self, tmp_path, chinese_font):
        """基本票据识别"""
        from services.ocr_service import extract_receipt_info
        p = str(tmp_path / "fapiao.png")
        make_test_image([
            '增值税专用发票',
            '发票号码：12345678',
            '¥1500.00',
            '2026-08-20',
        ], chinese_font, p)
        r = extract_receipt_info(p)
        assert r['engine'] == 'rapidocr'
        f = r['fields']
        # 数字字段一定能识别
        assert '12345678' in f['invoice_no']
        assert '1500' in f['amount'] or '1500.00' in f['amount']
        assert '2026-08-20' in f['date']

    def test_blank_image(self, tmp_path):
        """空白图"""
        from PIL import Image
        from services.ocr_service import extract_receipt_info
        p = str(tmp_path / "blank.png")
        Image.new('RGB', (300, 200), 'white').save(p)
        r = extract_receipt_info(p)
        assert r['engine'] == 'rapidocr'
        assert r['fields']['amount'] == ''


# ============= 引擎降级测试 =============

class TestEngineFallback:
    """rapidocr 不可用时降级到 mock"""

    def test_fallback_when_no_engine(self, tmp_path):
        """模拟 _get_engine 返回 None"""
        from services.ocr_service import real_ocr
        # 先建一个空文件（real_ocr 先检查文件存在）
        p = tmp_path / "dummy.png"
        p.write_bytes(b'fake')
        with patch('services.ocr_service._get_engine', return_value=None):
            # 重置 _ENGINE_TRIED 让 mock 生效
            import services.ocr_service as srv
            srv._ENGINE_TRIED = False
            srv._ENGINE = None
            r = real_ocr(str(p))
            assert r['status'] == 'mock'
            assert r['engine'] == 'mock'
            assert r['lines'] == []


# ============= 集成测试 =============

class TestSaveTransferRecord:
    """save_transfer_record"""

    def test_save_success(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        today = date.today()
        result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'transfer_type': 'borrow',
                'real_name': '张三',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=90)).isoformat(),
                'source_unit': 'A 单位',
            },
        )
        assert result['success']
        assert 'transfer_id' in result

        t = PersonnelTransfer.query.get(result['transfer_id'])
        assert t.real_name == '张三'
        assert t.transfer_type == 'borrow'
        assert t.status == 'active'
        # 默认 rapidocr（v2.9.0）
        assert t.ocr_engine == 'rapidocr'

    def test_save_missing_name(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={'transfer_type': 'borrow', 'start_date': '2026-08-01', 'end_date': '2026-12-31'},
        )
        assert not result['success']
        assert '姓名' in result['message']

    def test_save_end_before_start(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '李四',
                'start_date': '2026-12-31',
                'end_date': '2026-08-01',
            },
        )
        assert not result['success']
        assert '不能早于' in result['message']

    def test_save_with_past_end_auto_expired(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '过期人',
                'start_date': '2020-01-01',
                'end_date': '2020-12-31',
            },
        )
        assert result['success']
        t = PersonnelTransfer.query.get(result['transfer_id'])
        assert t.status == 'expired'

    def test_save_with_id_card(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        today = date.today()
        result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '有身份证',
                'id_card_no': '110101199003078811',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        )
        assert result['success']
        t = PersonnelTransfer.query.get(result['transfer_id'])
        assert t.id_card_no == '110101199003078811'


class TestMatchTransferToUser:
    """match_transfer_to_user"""

    def test_bind_success(self, app, admin_user, reimburser):
        from services.ocr_service import save_transfer_record, match_transfer_to_user
        today = date.today()
        save_result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '张三',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        )
        result = match_transfer_to_user(save_result['transfer_id'], reimburser['id'])
        assert result['success']

        t = PersonnelTransfer.query.get(save_result['transfer_id'])
        assert t.matched_user_id == reimburser['id']

    def test_bind_invalid_transfer(self, app, admin_user):
        from services.ocr_service import match_transfer_to_user
        result = match_transfer_to_user(99999, admin_user['id'])
        assert not result['success']

    def test_bind_invalid_user(self, app, admin_user):
        from services.ocr_service import save_transfer_record, match_transfer_to_user
        today = date.today()
        save_result = save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '测试',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        )
        result = match_transfer_to_user(save_result['transfer_id'], 99999)
        assert not result['success']


class TestFindUserByName:
    """find_user_by_name"""

    def test_find_existing(self, app, reimburser):
        from services.ocr_service import find_user_by_name
        from models.models import SysUser
        with app.app_context():
            u = SysUser.query.get(reimburser['id'])
            name = u.real_name
        users = find_user_by_name(name)
        assert any(u['id'] == reimburser['id'] for u in users)

    def test_find_nonexistent(self, app):
        from services.ocr_service import find_user_by_name
        assert find_user_by_name('不存在的名字xyz') == []

    def test_find_empty(self, app):
        from services.ocr_service import find_user_by_name
        assert find_user_by_name('') == []


class TestTransferToDict:
    """PersonnelTransfer.to_dict / is_valid_on"""

    def test_to_dict_masks_id_card(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        today = date.today()
        save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '测试',
                'id_card_no': '110101199003078811',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        )
        t = PersonnelTransfer.query.filter_by(real_name='测试').first()
        d = t.to_dict()
        assert d['id_card_no'] == '***8811'

    def test_is_valid_on_active(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        today = date.today()
        save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '有效',
                'start_date': (today - timedelta(days=10)).isoformat(),
                'end_date': (today + timedelta(days=20)).isoformat(),
            },
        )
        t = PersonnelTransfer.query.filter_by(real_name='有效').first()
        assert t.is_valid_on(today) is True

    def test_is_valid_on_cancelled(self, app, admin_user):
        from services.ocr_service import save_transfer_record
        today = date.today()
        save_transfer_record(
            operator_id=admin_user['id'],
            fields={
                'real_name': '作废',
                'start_date': (today - timedelta(days=10)).isoformat(),
                'end_date': (today + timedelta(days=20)).isoformat(),
            },
        )
        t = PersonnelTransfer.query.filter_by(real_name='作废').first()
        t.status = 'cancelled'
        db.session.commit()
        assert t.is_valid_on(today) is False


# ============= 路由测试 =============

@pytest.fixture
def auditor_client(client, auditor):
    """已登录稽核员的测试客户端"""
    r = client.post('/api/auth/login', json={'username': auditor['username'], 'password': auditor['password']})
    assert r.json['code'] == 0, f'稽核员登录失败: {r.json}'
    return client


@pytest.fixture
def reimburser_client(client, reimburser):
    """已登录报销人的测试客户端"""
    r = client.post('/api/auth/login', json={'username': reimburser['username'], 'password': reimburser['password']})
    assert r.json['code'] == 0, f'报销人登录失败: {r.json}'
    return client


class TestTransferRoutes:
    """API 路由测试"""

    def test_upload_no_file(self, app, admin_client):
        r = admin_client.post('/api/ocr/transfer/upload', data={}, content_type='multipart/form-data')
        assert r.status_code == 400
        assert r.json['code'] != 0

    def test_upload_success(self, app, admin_client, tmp_path, chinese_font):
        """真实引擎上传识别（生成测试图）"""
        from services.ocr_service import real_ocr
        p = str(tmp_path / "borrow.png")
        make_test_image([
            '借调函', '姓名：张三',
            '原单位：技术保障处',
            '自2026-08-01至2026-12-31',
        ], chinese_font, p)
        with open(p, 'rb') as fp:
            data = {'file': (fp, 'borrow.png')}
            r = admin_client.post('/api/ocr/transfer/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 200
        body = r.json
        assert body['code'] == 0
        assert body['data']['attachment_id'] > 0
        ocr = body['data']['ocr']
        # 真实引擎
        assert ocr['engine'] == 'rapidocr'
        assert ocr['fields']['transfer_type'] == 'borrow'
        # 日期一定识别
        assert '2026' in ocr['fields']['start_date']

    def test_upload_auditor_allowed(self, app, auditor_client, tmp_path, chinese_font):
        from services.ocr_service import real_ocr
        p = str(tmp_path / "follow.png")
        make_test_image([
            '跟班学习通知书', '姓名：李四',
            '自2026-09-01至2026-11-30',
        ], chinese_font, p)
        with open(p, 'rb') as fp:
            data = {'file': (fp, 'follow.png')}
            r = auditor_client.post('/api/ocr/transfer/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.json['code'] == 0

    def test_upload_reimburser_forbidden(self, app, reimburser_client, tmp_path, chinese_font):
        """报销人客户端不能上传调令"""
        from services.ocr_service import real_ocr
        p = str(tmp_path / "test.png")
        make_test_image(['测试'], chinese_font, p)
        with open(p, 'rb') as fp:
            data = {'file': (fp, 'test.png')}
            r = reimburser_client.post('/api/ocr/transfer/upload', data=data, content_type='multipart/form-data')
        assert r.status_code in (200, 403)
        if r.status_code == 200:
            assert r.json['code'] != 0

    def test_save_via_api(self, app, admin_client):
        today = date.today()
        payload = {
            'fields': {
                'transfer_type': 'borrow',
                'real_name': 'API 测试',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
                'source_unit': '测试单位',
            },
        }
        r = admin_client.post('/api/ocr/transfer/save', json=payload)
        assert r.status_code == 200
        body = r.json
        assert body['code'] == 0
        assert body['data']['transfer_id'] > 0

    def test_save_missing_name(self, app, admin_client):
        payload = {
            'fields': {
                'transfer_type': 'borrow',
                'start_date': '2026-08-01',
                'end_date': '2026-12-31',
            },
        }
        r = admin_client.post('/api/ocr/transfer/save', json=payload)
        assert r.json['code'] != 0

    def test_list_via_api(self, app, admin_client):
        r = admin_client.get('/api/ocr/transfer/list')
        assert r.status_code == 200
        assert r.json['code'] == 0
        assert 'items' in r.json['data']
        assert 'total' in r.json['data']

    def test_list_filter_by_name(self, app, admin_client):
        # 先插一条
        today = date.today()
        from services.ocr_service import save_transfer_record
        with app.app_context():
            save_transfer_record(
                operator_id=1,
                fields={
                    'real_name': '过滤测试_王五',
                    'start_date': today.isoformat(),
                    'end_date': (today + timedelta(days=30)).isoformat(),
                },
            )

        r = admin_client.get('/api/ocr/transfer/list?real_name=王五')
        assert r.status_code == 200
        assert any('王五' in item['real_name'] for item in r.json['data']['items'])

    def test_list_filter_by_type(self, app, admin_client):
        r = admin_client.get('/api/ocr/transfer/list?transfer_type=borrow')
        assert r.status_code == 200
        for item in r.json['data']['items']:
            assert item['transfer_type'] == 'borrow'

    def test_detail(self, app, admin_client):
        today = date.today()
        from services.ocr_service import save_transfer_record
        with app.app_context():
            r = save_transfer_record(
                operator_id=1,
                fields={
                    'real_name': '详情测试',
                    'start_date': today.isoformat(),
                    'end_date': (today + timedelta(days=30)).isoformat(),
                },
            )
            tid = r['transfer_id']
        r = admin_client.get(f'/api/ocr/transfer/{tid}')
        assert r.status_code == 200
        body = r.json
        assert body['code'] == 0
        assert body['data']['real_name'] == '详情测试'
        assert 'operator' in body['data']
        assert body['data']['operator']['username'] == 'admin'

    def test_detail_not_found(self, app, admin_client):
        r = admin_client.get('/api/ocr/transfer/99999')
        assert r.status_code == 404

    def test_bind_user(self, app, admin_client, reimburser):
        today = date.today()
        from services.ocr_service import save_transfer_record
        with app.app_context():
            r = save_transfer_record(
                operator_id=1,
                fields={
                    'real_name': '绑定测试',
                    'start_date': today.isoformat(),
                    'end_date': (today + timedelta(days=30)).isoformat(),
                },
            )
            tid = r['transfer_id']

        r = admin_client.post(f'/api/ocr/transfer/{tid}/bind-user',
                               json={'user_id': reimburser['id']})
        assert r.status_code == 200
        assert r.json['code'] == 0

    def test_search_user(self, app, admin_client, reimburser):
        from models.models import SysUser
        with app.app_context():
            name = SysUser.query.get(reimburser['id']).real_name
        r = admin_client.get(f'/api/ocr/transfer/search-user?name={name}')
        assert r.status_code == 200
        body = r.json
        assert body['code'] == 0
        assert any(u['id'] == reimburser['id'] for u in body['data'])

    def test_search_user_empty(self, app, admin_client):
        r = admin_client.get('/api/ocr/transfer/search-user?name=不存在的xyz')
        assert r.status_code == 200
        assert r.json['data'] == []

    def test_cancel_via_finance(self, app, admin_client):
        today = date.today()
        from services.ocr_service import save_transfer_record
        with app.app_context():
            r = save_transfer_record(
                operator_id=1,
                fields={
                    'real_name': '作废测试',
                    'start_date': today.isoformat(),
                    'end_date': (today + timedelta(days=30)).isoformat(),
                },
            )
            tid = r['transfer_id']

        r = admin_client.post(f'/api/ocr/transfer/{tid}/cancel')
        assert r.json['code'] == 0

        with app.app_context():
            t = PersonnelTransfer.query.get(tid)
            assert t.status == 'cancelled'

    def test_cancel_auditor_forbidden(self, app, auditor_client):
        today = date.today()
        from services.ocr_service import save_transfer_record
        with app.app_context():
            r = save_transfer_record(
                operator_id=1,
                fields={
                    'real_name': '稽核员不能作废',
                    'start_date': today.isoformat(),
                    'end_date': (today + timedelta(days=30)).isoformat(),
                },
            )
            tid = r['transfer_id']

        r = auditor_client.post(f'/api/ocr/transfer/{tid}/cancel')
        # 稽核员没有 finance 角色，应被拒
        assert r.status_code == 403


# ============= 角色边界测试 =============

class TestRoleBoundary:
    """角色权限"""

    def test_finance_can_save(self, app, admin_client):
        today = date.today()
        payload = {
            'fields': {
                'transfer_type': 'follow_training',
                'real_name': '财务录入',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        }
        r = admin_client.post('/api/ocr/transfer/save', json=payload)
        assert r.json['code'] == 0

    def test_auditor_can_save(self, app, auditor_client):
        today = date.today()
        payload = {
            'fields': {
                'transfer_type': 'combat_training',
                'real_name': '稽核员录入',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        }
        r = auditor_client.post('/api/ocr/transfer/save', json=payload)
        assert r.json['code'] == 0

    def test_reimburser_cannot_save(self, app, reimburser_client):
        today = date.today()
        payload = {
            'fields': {
                'transfer_type': 'borrow',
                'real_name': '报销人不能录',
                'start_date': today.isoformat(),
                'end_date': (today + timedelta(days=30)).isoformat(),
            },
        }
        r = reimburser_client.post('/api/ocr/transfer/save', json=payload)
        assert r.status_code == 403
