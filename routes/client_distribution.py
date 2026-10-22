"""客户端分发路由（v2.10.0）

- 财务触发：生成稽核员/报销员客户端包
- 稽核员触发：生成报销员客户端包
- 任何角色：可生成自己角色的完整包
"""
import logging
import os
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from services.client_packager import (
    build_auditor_client_package,
    build_reimburser_client_package,
    build_finance_client_package,
)
from models.models import SysUser
from utils.decorators import login_required, get_current_user, role_required

dist_bp = Blueprint('distribution', __name__, url_prefix='/api/distribution')
log = logging.getLogger(__name__)


@dist_bp.route('/build/auditor/<int:auditor_id>', methods=['POST'])
@role_required('finance')
def build_for_auditor(auditor_id):
    """财务触发：给指定稽核员生成绿色客户端包"""
    user = get_current_user()

    # 验证稽核员存在
    auditor = SysUser.query.get(auditor_id)
    if not auditor:
        return jsonify({'code': 1, 'message': '稽核员不存在'}), 404
    if auditor.role != 'auditor':
        return jsonify({'code': 1, 'message': '该用户不是稽核员'}), 400

    result = build_auditor_client_package(
        operator_id=user.id,
        auditor_id=auditor_id,
        finance_id=user.id,
    )

    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 500

    return jsonify({
        'code': 0,
        'message': f'已生成稽核员客户端包（{result["zip_name"]}）',
        'data': {
            'zip_name': result['zip_name'],
            'zip_size_mb': round(result['zip_size'] / (1024 * 1024), 1),
            'data_scope': result['data_scope'],
        },
    })


@dist_bp.route('/build/reimburser/<int:reimburser_id>', methods=['POST'])
@role_required('finance', 'auditor')
def build_for_reimburser(reimburser_id):
    """财务/稽核员触发：给指定报销员生成绿色客户端包"""
    user = get_current_user()

    reimburser = SysUser.query.get(reimburser_id)
    if not reimburser:
        return jsonify({'code': 1, 'message': '报销员不存在'}), 404
    if reimburser.role != 'reimburser':
        return jsonify({'code': 1, 'message': '该用户不是报销员'}), 400

    # v2.10.0 模式 C：基于项目覆盖度判定
    #   - agent_c：所有项目都被代理 → 完全模式 C，禁止单独打包
    #   - partial/self/orphan → 允许打包
    from sqlalchemy import text
    from models import db
    coverage = db.session.execute(text("""
        SELECT
            COALESCE(up_total.total_projects, 0),
            COALESCE(up_authed.authed_projects, 0)
        FROM sys_user u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS total_projects
            FROM user_project WHERE status = 'active' GROUP BY user_id
        ) up_total ON up_total.user_id = u.id
        LEFT JOIN (
            SELECT up.user_id, COUNT(DISTINCT up.project_id) AS authed_projects
            FROM user_project up
            JOIN agent_auth a ON a.project_id = up.project_id AND a.be_agent_id = up.user_id
            WHERE up.status = 'active' AND a.status = 'active'
            GROUP BY up.user_id
        ) up_authed ON up_authed.user_id = u.id
        WHERE u.id = :bid
    """), {'bid': reimburser_id}).fetchone()
    if coverage:
        total, authed = coverage
        if total > 0 and total == authed:
            return jsonify({
                'code': 1,
                'message': f'该报销员所有 {total} 个项目都已被代理（完全模式 C），无需单独打包客户端。'
                           f'如确需独立部署，请先解除对应项目的代理关系。',
            }), 400

    # 稽核员只能给自己的报销员生成
    if user.role == 'auditor':
        row = db.session.execute(text(
            "SELECT 1 FROM agent_auth WHERE agent_id = :aid AND be_agent_id = :bid AND status = 'active'"
        ), {'aid': user.id, 'bid': reimburser_id}).fetchone()
        if not row:
            return jsonify({'code': 1, 'message': '权限不足：只能给自己代理的报销员打包'}), 403

    # 找到报销员的稽核员（用于数据回流）
    auditor_id = None
    if user.role == 'auditor':
        auditor_id = user.id
    else:
        row = db.session.execute(text(
            "SELECT agent_id FROM agent_auth WHERE be_agent_id = :bid AND status = 'active' LIMIT 1"
        ), {'bid': reimburser_id}).fetchone()
        if row:
            auditor_id = row[0]

    result = build_reimburser_client_package(
        operator_id=user.id,
        reimburser_id=reimburser_id,
        auditor_id=auditor_id,
    )

    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 500

    return jsonify({
        'code': 0,
        'message': f'已生成报销员客户端包（{result["zip_name"]}）',
        'data': {
            'zip_name': result['zip_name'],
            'zip_size_mb': round(result['zip_size'] / (1024 * 1024), 1),
            'data_scope': result['data_scope'],
        },
    })


@dist_bp.route('/check-reimburser/<int:reimburser_id>', methods=['GET'])
@role_required('finance', 'auditor')
def check_reimburser_status(reimburser_id):
    """检查报销员的部署模式

    v2.10.0 增强：基于项目覆盖度判定
    - agent_c：所有项目都被代理（完全模式 C，无需客户端）
    - partial：部分项目被代理
    - self：所有项目都无代理
    - orphan：没有绑定任何项目
    """
    from sqlalchemy import text
    from models import db
    row = db.session.execute(text("""
        SELECT
            up_total.total_projects,
            up_authed.authed_projects,
            (SELECT id FROM sys_user WHERE id = (
                SELECT agent_id FROM agent_auth
                WHERE be_agent_id = :bid AND status = 'active' LIMIT 1
            )) AS proxy_id,
            (SELECT real_name FROM sys_user WHERE id = (
                SELECT agent_id FROM agent_auth
                WHERE be_agent_id = :bid AND status = 'active' LIMIT 1
            )) AS proxy_name
        FROM sys_user u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS total_projects
            FROM user_project
            WHERE status = 'active'
            GROUP BY user_id
        ) up_total ON up_total.user_id = u.id
        LEFT JOIN (
            SELECT up.user_id, COUNT(DISTINCT up.project_id) AS authed_projects
            FROM user_project up
            JOIN agent_auth a ON a.project_id = up.project_id AND a.be_agent_id = up.user_id
            WHERE up.status = 'active' AND a.status = 'active'
            GROUP BY up.user_id
        ) up_authed ON up_authed.user_id = u.id
        WHERE u.id = :bid
    """), {'bid': reimburser_id}).fetchone()

    if not row:
        return jsonify({'code': 1, 'message': '用户不存在'}), 404

    total, authed, proxy_id, proxy_name = row
    total = total or 0
    authed = authed or 0

    if total == 0:
        mode = 'orphan'
    elif total == authed:
        mode = 'agent_c'
    elif authed and authed < total:
        mode = 'partial'
    else:
        mode = 'self'

    return jsonify({
        'code': 0,
        'data': {
            'mode': mode,
            'need_package': mode in ('self', 'partial', 'orphan'),
            'total_projects': total,
            'authed_projects': authed,
            'proxy_auditor': {'id': proxy_id, 'name': proxy_name} if proxy_id else None,
            'proxy_auditor_name': proxy_name,
            'message': {
                'agent_c': f'该报销员 {authed}/{total} 项目已全部被代理（完全模式 C），无需生成客户端包',
                'partial': f'该报销员 {authed}/{total} 项目被代理（混合模式），仍需生成客户端包',
                'self': '该报销员无代理关系（自助模式），需要生成客户端包',
                'orphan': '该报销员未绑定项目',
            }[mode],
        }
    })


@dist_bp.route('/build/finance', methods=['POST'])
@role_required('finance')
def build_for_finance():
    """财务触发：给自己生成完整客户端包（重新打包）"""
    user = get_current_user()
    result = build_finance_client_package(operator_id=user.id, finance_id=user.id)

    if not result['success']:
        return jsonify({'code': 1, 'message': result['message']}), 500

    return jsonify({
        'code': 0,
        'message': f'已生成财务客户端包（{result["zip_name"]}）',
        'data': {
            'zip_name': result['zip_name'],
            'zip_size_mb': round(result['zip_size'] / (1024 * 1024), 1),
            'data_scope': result['data_scope'],
        },
    })


@dist_bp.route('/download/<zip_name>', methods=['GET'])
@role_required('finance', 'auditor')
def download_zip(zip_name):
    """下载已生成的客户端 zip"""
    from config import Config
    # 防路径穿越
    safe_name = secure_filename(zip_name)
    if safe_name != zip_name:
        return jsonify({'code': 1, 'message': '非法文件名'}), 400

    zip_path = os.path.join(Config.CLIENT_DIST_DIR, safe_name)
    if not os.path.exists(zip_path):
        return jsonify({'code': 1, 'message': '文件不存在'}), 404

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=safe_name,
        mimetype='application/zip',
    )


@dist_bp.route('/list', methods=['GET'])
@role_required('finance', 'auditor')
def list_packages():
    """列出已生成的客户端包"""
    from config import Config
    dist_dir = Config.CLIENT_DIST_DIR
    if not os.path.exists(dist_dir):
        return jsonify({'code': 0, 'data': {'items': []}})

    items = []
    for f in sorted(os.listdir(dist_dir), reverse=True):
        if f.endswith('.zip'):
            full = os.path.join(dist_dir, f)
            items.append({
                'name': f,
                'size_mb': round(os.path.getsize(full) / (1024 * 1024), 1),
                'created_at': os.path.getmtime(full),
            })

    return jsonify({'code': 0, 'data': {'items': items[:50]}})


@dist_bp.route('/delete/<zip_name>', methods=['POST'])
@role_required('finance', 'auditor')
def delete_zip(zip_name):
    """删除已生成的客户端包"""
    from config import Config
    safe_name = secure_filename(zip_name)
    zip_path = os.path.join(Config.CLIENT_DIST_DIR, safe_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)
        return jsonify({'code': 0, 'message': '已删除'})
    return jsonify({'code': 1, 'message': '文件不存在'}), 404
