"""
生成 TLS 自签证书（O1 决策）
- 用于内网传输加密
- 仅首次启动需要运行
- 3650 天有效

用法：
    python generate_ssl.py
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


BASE_DIR = Path(__file__).resolve().parent
SSL_DIR = BASE_DIR / 'ssl'
CERT_PATH = SSL_DIR / 'cert.pem'
KEY_PATH = SSL_DIR / 'key.pem'


def main():
    print('=' * 50)
    print('TLS 证书生成器（O1 决策）')
    print('=' * 50)

    if CERT_PATH.exists() and KEY_PATH.exists():
        print(f'证书已存在：{CERT_PATH}')
        print(f'私钥已存在：{KEY_PATH}')
        ans = input('是否重新生成？(y/N): ').strip().lower()
        if ans != 'y':
            print('已跳过生成')
            return

    # 1. 生成私钥
    print('\n[1/3] 生成 RSA 2048 私钥...')
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    print('    ✅ 私钥已生成')

    # 2. 构造证书
    print('[2/3] 构造自签证书（3650 天有效）...')
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, '报销稽核系统'),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, '信创环境内网'),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('localhost'),
                x509.DNSName('127.0.0.1'),
                x509.IPAddress(__import__('ipaddress').ip_address('127.0.0.1')),
            ]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    print('    ✅ 证书已签发')

    # 3. 写入文件
    print('[3/3] 写入文件...')
    SSL_DIR.mkdir(parents=True, exist_ok=True)

    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # 限制私钥权限（Linux）
    if sys.platform != 'win32':
        os.chmod(KEY_PATH, 0o600)
        os.chmod(CERT_PATH, 0o644)

    print(f'    ✅ 证书: {CERT_PATH}')
    print(f'    ✅ 私钥: {KEY_PATH}')
    print()
    print('证书信息：')
    print(f'  Subject: {cert.subject.rfc4514_string()}')
    print(f'  Issuer:  {cert.issuer.rfc4514_string()}')
    print(f'  Serial:  {cert.serial_number}')
    print(f'  Not Before: {cert.not_valid_before}')
    print(f'  Not After:  {cert.not_valid_after}')
    print(f'  SAN: {cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value}')
    print()
    print('下一步：')
    print('  启动 launcher 时会自动检测证书并启用 TLS')
    print('  浏览器会提示"不受信任"（因为是自签），选择"继续访问"即可')


if __name__ == '__main__':
    main()
