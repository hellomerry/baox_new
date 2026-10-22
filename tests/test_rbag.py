"""
T3 .rbag 数据包测试
"""
import os
import json
import zipfile
import io
import pytest

from utils.crypto import (
    encrypt_field, decrypt_field,
    sha256_bytes, sha256_file, sha256_dict
)
from utils.rbag import (
    build_package, parse_package, desensitize_payload,
    desensitize_user_data
)


class TestCrypto:
    def test_encrypt_decrypt_round_trip(self):
        text = '13800138000'
        enc = encrypt_field(text)
        dec = decrypt_field(enc)
        assert dec == text
        assert enc != text  # 加密后不是原文

    def test_encrypt_id_card(self):
        ic = '110101199001011234'
        enc = encrypt_field(ic)
        # 脱敏显示应是 110101********1234
        desensitized = desensitize_user_data({'id_card': ic})['id_card']
        assert desensitized == '110101********1234'

    def test_encrypt_empty(self):
        assert encrypt_field('') == ''
        assert decrypt_field('') == ''

    def test_decrypt_invalid_returns_empty(self):
        assert decrypt_field('not-base64!@#$') == ''

    def test_sha256_bytes(self):
        h = sha256_bytes(b'hello')
        assert len(h) == 64  # SHA256 64 字符

    def test_sha256_dict_canonical(self):
        d1 = {'a': 1, 'b': 2}
        d2 = {'b': 2, 'a': 1}
        # 排序后哈希相同
        assert sha256_dict(d1) == sha256_dict(d2)

    def test_sha256_file(self, tmp_path):
        f = tmp_path / 'test.txt'
        f.write_bytes(b'content')
        h = sha256_file(str(f))
        assert len(h) == 64
        assert h == sha256_bytes(b'content')


class TestRbag:
    def test_build_basic(self):
        pkg = build_package(
            package_type='test',
            payload={'data': 'hello'},
            creator_account='tester',
            creator_role='auditor',
            source_client='auditor-001',
            target_role='finance',
            desensitize=True,
        )
        assert len(pkg) > 0

    def test_build_then_parse(self):
        payload = {'user_data': {'real_name': '张三', 'id_card': '110101199001011234'}}
        pkg = build_package(
            package_type='test', payload=payload,
            creator_account='tester', creator_role='auditor',
            source_client='a', target_role='finance',
            desensitize=True,
        )
        parsed = parse_package(pkg)
        assert parsed['valid'] is True
        assert parsed['manifest']['package_type'] == 'test'
        # 脱敏后 id_card 应是 110101********1234
        assert parsed['payload']['user_data']['id_card'] == '110101********1234'

    def test_tamper_detection(self):
        """篡改包内容应被检测"""
        pkg = build_package(
            package_type='test', payload={'a': 1},
            creator_account='t', creator_role='r', source_client='c', target_role='finance',
        )
        # 篡改
        buf = io.BytesIO(pkg)
        out_buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'r') as zin, zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.namelist():
                if item == 'data.json':
                    # 修改内容
                    data = zin.read(item).replace(b'1', b'2')
                    zout.writestr(item, data)
                else:
                    zout.writestr(item, zin.read(item))
        tampered = out_buf.getvalue()

        parsed = parse_package(tampered)
        assert parsed['valid'] is False
        assert parsed['error'] is not None

    def test_desensitize_id_card(self):
        d = desensitize_user_data({'id_card': '110101199001011234'})
        assert d['id_card'] == '110101********1234'

    def test_desensitize_phone(self):
        d = desensitize_user_data({'phone': '13800138000'})
        assert d['phone'] == '138****8000'

    def test_desensitize_bank_card(self):
        d = desensitize_user_data({'bank_card': '6222021234567890'})
        assert d['bank_card'] == '****'

    def test_no_desensitize(self):
        """不脱敏时原文保留"""
        pkg = build_package(
            package_type='test', payload={'user_data': {'id_card': '110101199001011234'}},
            creator_account='t', creator_role='r', source_client='c', target_role='finance',
            desensitize=False,
        )
        parsed = parse_package(pkg)
        assert parsed['payload']['user_data']['id_card'] == '110101199001011234'

    def test_manifest_includes_desensitize_flag(self):
        pkg = build_package(
            package_type='test', payload={},
            creator_account='t', creator_role='r', source_client='c', target_role='finance',
            desensitize=True,
        )
        parsed = parse_package(pkg)
        assert parsed['manifest']['desensitized'] is True

    def test_unique_package_id(self):
        ids = set()
        for _ in range(5):
            pkg = build_package(
                package_type='test', payload={},
                creator_account='t', creator_role='r', source_client='c', target_role='finance',
            )
            parsed = parse_package(pkg)
            ids.add(parsed['manifest']['package_id'])
        assert len(ids) == 5  # 5 个唯一 ID
