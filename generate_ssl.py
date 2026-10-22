"""
生成 TLS 自签证书（O1 决策）
- 用于内网传输加密
- 仅首次启动需要运行
- 默认 3650 天有效

v2.10.0e 增强（Web 模式）：
- 自动检测本机 IPv4 地址加入 SAN（浏览器访问 https://<本机IP>:5443 需要）
- 自动加入本机 hostname 到 SAN
- 支持 --cn / --ips / --hostnames 自定义

用法：
    python generate_ssl.py                # 自动检测 IP/hostname
    python generate_ssl.py --cn finance01 # 自定义 CN
    python generate_ssl.py --ips 192.168.1.100,10.0.0.5 --hostnames finance.bx.local
    python generate_ssl.py --force        # 强制覆盖现有证书
"""
import os
import sys
import socket
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Windows GBK 兜底（必须在 print 之前）
for _name in ('stdout', 'stderr'):
    _stream = getattr(sys, _name, None)
    if _stream is not None:
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress


BASE_DIR = Path(__file__).resolve().parent
SSL_DIR = BASE_DIR / 'ssl'
CERT_PATH = SSL_DIR / 'cert.pem'
KEY_PATH = SSL_DIR / 'key.pem'


def get_local_ips() -> list:
    """获取本机非回环 IPv4（用出网探测法，简单但够用）"""
    ips = ['127.0.0.1']
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('8.8.8.8', 80))
            ips.append(sock.getsockname()[0])
        except Exception:
            pass
        finally:
            sock.close()
    except Exception:
        pass
    # 去重保序
    seen = set()
    return [x for x in ips if not (x in seen or seen.add(x))]


def get_local_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ''


def parse_args():
    p = argparse.ArgumentParser(description='生成 TLS 自签证书')
    p.add_argument('--cn', default=None, help='证书 CN（Common Name），默认用本机 IP')
    p.add_argument('--ips', default='', help='额外 IP（逗号分隔）')
    p.add_argument('--hostnames', default='', help='额外 hostname（逗号分隔）')
    p.add_argument('--days', type=int, default=3650, help='有效天数，默认 3650')
    p.add_argument('--force', action='store_true', help='强制覆盖已存在证书')
    return p.parse_args()


def main():
    print('=' * 60)
    print('TLS 证书生成器（O1 决策 · v2.10.0e Web 增强）')
    print('=' * 60)

    args = parse_args()

    if CERT_PATH.exists() and KEY_PATH.exists() and not args.force:
        print(f'证书已存在：{CERT_PATH}')
        print(f'私钥已存在：{KEY_PATH}')
        ans = input('是否重新生成？(y/N): ').strip().lower()
        if ans != 'y':
            print('已跳过生成')
            return

    # 1. 生成私钥
    print('\n[1/4] 生成 RSA 2048 私钥...')
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    print('    ✅ 私钥已生成')

    # 2. 构造 SAN
    print('[2/4] 收集 SAN 列表...')
    san_list = [x509.DNSName('localhost')]

    local_ips = get_local_ips()
    extra_ips = [x.strip() for x in args.ips.split(',') if x.strip()]
    all_ips = list(dict.fromkeys(local_ips + extra_ips))  # 去重保序
    for ip_str in all_ips:
        try:
            san_list.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
            print(f'    + IP: {ip_str}')
        except ValueError:
            print(f'    ! 跳过非法 IP: {ip_str}')

    hostname = get_local_hostname()
    if hostname and hostname != 'localhost':
        san_list.append(x509.DNSName(hostname))
        print(f'    + DNS: {hostname}')
    extra_hosts = [x.strip() for x in args.hostnames.split(',') if x.strip()]
    for h in extra_hosts:
        san_list.append(x509.DNSName(h))
        print(f'    + DNS: {h}')

    # 3. 构造证书
    print('[3/4] 构造自签证书...')
    cn = args.cn or (all_ips[0] if all_ips else '127.0.0.1')
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, '报销稽核系统'),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, '信创环境内网 / Web 访问'),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=args.days))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    print(f'    ✅ 证书已签发（CN={cn}, {args.days} 天）')

    # 4. 写入文件
    print('[4/4] 写入文件...')
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
    print(f'  SAN:')
    san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    for entry in san_ext:
        print(f'    - {entry}')
    print()
    print('下一步：')
    print('  启动 launcher_finance.py 时会自动检测证书并启用 TLS')
    print('  Web 浏览器访问 https://<本机IP>:5443（自签需手动确认）')
    print('  Web 模式默认端口 5443，可在 WEB_PORT 环境变量修改')


if __name__ == '__main__':
    main()