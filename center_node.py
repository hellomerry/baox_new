"""
中心节点服务端（M3 决策）
- 接收 .rbag 上传
- 分发给目标客户端
- TLS 1.2+ 强制

用法：
    python center_node.py [port=5443]

需要先生成 SSL 证书：
    python generate_ssl.py
"""
import os
import sys
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename

from config import BASE_DIR


CENTER_DIR = BASE_DIR / 'center_data'
UPLOAD_DIR = CENTER_DIR / 'uploads'
INDEX_FILE = CENTER_DIR / 'index.json'


def init_dirs():
    CENTER_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text('{}', encoding='utf-8')


def load_index() -> dict:
    if not INDEX_FILE.exists():
        init_dirs()
    return json.loads(INDEX_FILE.read_text(encoding='utf-8'))


def save_index(idx: dict):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding='utf-8')


# 启动时初始化
init_dirs()


app = Flask(__name__)


@app.route('/api/center/ping')
def ping():
    """心跳"""
    return jsonify({
        'code': 0,
        'data': {
            'server': 'center_node',
            'version': '1.0.0',
            'time': datetime.now().isoformat(),
        }
    })


@app.route('/api/center/packages/upload', methods=['POST'])
def upload_package():
    """接收 .rbag 上传"""
    if 'file' not in request.files:
        data = request.get_data()
        if not data:
            return jsonify({'code': 1, 'message': '无文件'}), 400
        package_bytes = data
        filename = request.headers.get('X-Package-Filename', f'upload_{uuid.uuid4().hex[:8]}.rbag')
    else:
        f = request.files['file']
        package_bytes = f.read()
        filename = secure_filename(f.filename or 'upload.rbag')

    # 校验 .rbag 后缀
    if not filename.endswith('.rbag'):
        filename = filename + '.rbag'

    # 校验内容（必须是 zip）
    import zipfile
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as zf:
            if 'manifest.json' not in zf.namelist():
                return jsonify({'code': 1, 'message': '包格式错误：缺 manifest.json'}), 400
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    except Exception as e:
        return jsonify({'code': 1, 'message': f'包解析失败: {e}'}), 400

    package_id = manifest.get('package_id', str(uuid.uuid4()))
    target_role = manifest.get('target_role', '')

    # 保存（确保目录存在）
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOAD_DIR / f'{package_id}.rbag'
    save_path.write_bytes(package_bytes)

    # 更新索引
    idx = load_index()
    idx[package_id] = {
        'package_id': package_id,
        'package_type': manifest.get('package_type', ''),
        'target_role': target_role,
        'creator': manifest.get('creator_account', ''),
        'created_at': manifest.get('created_at', ''),
        'received_at': datetime.now().isoformat(),
        'size': len(package_bytes),
        'file': str(save_path.relative_to(BASE_DIR)),
        'downloaded_by': [],
    }
    save_index(idx)

    return jsonify({
        'code': 0,
        'data': {
            'package_id': package_id,
            'size': len(package_bytes),
            'saved_path': str(save_path),
        }
    })


@app.route('/api/center/packages/<package_id>')
def get_package(package_id):
    """下载 .rbag"""
    idx = load_index()
    if package_id not in idx:
        return jsonify({'code': 1, 'message': '包不存在'}), 404

    meta = idx[package_id]
    file_path = BASE_DIR / meta['file']
    if not file_path.exists():
        return jsonify({'code': 1, 'message': '包文件已丢失'}), 404

    # 记录下载
    downloader = request.headers.get('X-Client-Account', 'unknown')
    meta['downloaded_by'].append({
        'account': downloader,
        'at': datetime.now().isoformat(),
    })
    save_index(idx)

    return send_file(str(file_path), mimetype='application/octet-stream',
                     as_attachment=True, download_name=f'{package_id}.rbag')


@app.route('/api/center/packages/list')
def list_packages():
    """列出所有包"""
    target_role = request.args.get('target_role', '')
    idx = load_index()

    items = []
    for pid, meta in idx.items():
        if target_role and meta.get('target_role') != target_role:
            continue
        items.append(meta)
    items.sort(key=lambda x: x.get('received_at', ''), reverse=True)

    return jsonify({'code': 0, 'data': {'items': items, 'total': len(items)}})


@app.route('/api/center/stats')
def stats():
    """中心节点统计"""
    idx = load_index()
    total_size = sum(m.get('size', 0) for m in idx.values())
    return jsonify({
        'code': 0,
        'data': {
            'package_count': len(idx),
            'total_size': total_size,
            'server_time': datetime.now().isoformat(),
        }
    })


@app.route('/')
def index():
    return jsonify({
        'service': '报销稽核系统 - 中心节点',
        'version': '1.0.0',
        'endpoints': [
            '/api/center/ping',
            '/api/center/packages/upload',
            '/api/center/packages/list',
            '/api/center/packages/<package_id>',
            '/api/center/stats',
        ]
    })


def main():
    init_dirs()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5443

    # 0. 自动迁移（如配置了 DB）
    try:
        from migrations.runner import MigrationManager
        mgr = MigrationManager()
        current = mgr.get_applied_versions()
        current_ver = current[-1] if current else 'none'
        pending = mgr._topological_sort()
        if pending:
            print(f'[迁移] v{current_ver} → v{pending[-1]}（共 {len(pending)} 个版本）')
            mgr.upgrade()
        else:
            print(f'[迁移] 已是最新（v{current_ver}）')
    except Exception as e:
        print(f'[迁移] 跳过: {e}')

    # TLS
    ssl_cert = BASE_DIR / 'ssl' / 'cert.pem'
    ssl_key = BASE_DIR / 'ssl' / 'key.pem'
    ssl_context = None
    if ssl_cert.exists() and ssl_key.exists():
        ssl_context = (str(ssl_cert), str(ssl_key))
        print(f'[TLS 启用] {ssl_cert}')
    else:
        print('[警告] SSL 证书不存在，使用 HTTP 启动（仅供测试）')
        print('       生产环境请先运行: python generate_ssl.py')

    print(f'\n{"=" * 50}')
    print(f'报销稽核系统 - 中心节点')
    print(f'监听: {"https" if ssl_context else "http"}://0.0.0.0:{port}')
    print(f'{"=" * 50}\n')

    app.run(host='0.0.0.0', port=port, ssl_context=ssl_context, debug=False)


if __name__ == '__main__':
    main()
