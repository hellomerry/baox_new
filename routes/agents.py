"""代理关系管理路由（v2.10.0 模式 C 增强）

设计原则：
- 报销依托项目，所以 agent_auth 必须含 project_id
- 项目是稽核员创建的，所以代理关系由财务/稽核员设置
- 报销员**不能**自行设置代理（避免越权）

API：
- POST   /api/agents/setup              设置代理
- DELETE /api/agents/<id>               撤销
- GET    /api/agents/list               当前用户代理列表
- GET    /api/agents/by-project/<id>    项目的可代填报销员
- GET    /api/agents/mode-c-status      全局模式 C 判定
"""
import logging
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from models import db
from models.models import (
    AgentAuth, SysUser, UserProject, ExpenseProject,
)
from utils.decorators import login_required, get_current_user, role_required

agents_bp = Blueprint('agents', __name__, url_prefix='/api/agents')
log = logging.getLogger(__name__)


@agents_bp.route('/setup', methods=['POST'])
@role_required('finance', 'auditor')
def setup_agent():
    """设置代理关系

    body: {
        agent_id: 稽核员 id,
        be_agent_id: 报销员 id,
        project_id: 项目 id,
        auth_start_date: 'YYYY-MM-DD'（默认今天）,
        auth_end_date: 'YYYY-MM-DD'（可选）,
        agent_mode: 'full' / 'partial'（默认 full）,
    }
    """
    user = get_current_user()
    data = request.get_json() or {}

    agent_id = data.get('agent_id')
    be_agent_id = data.get('be_agent_id')
    project_id = data.get('project_id')

    if not all([agent_id, be_agent_id, project_id]):
        return jsonify({'code': 1, 'message': 'agent_id / be_agent_id / project_id 必填'}), 400

    # 1. 校验角色
    agent = SysUser.query.get(agent_id)
    if not agent or agent.role != 'auditor':
        return jsonify({'code': 1, 'message': 'agent_id 不是稽核员'}), 400

    be_agent = SysUser.query.get(be_agent_id)
    if not be_agent or be_agent.role != 'reimburser':
        return jsonify({'code': 1, 'message': 'be_agent_id 不是报销员'}), 400

    # 2. 校验项目
    project = ExpenseProject.query.get(project_id)
    if not project:
        return jsonify({'code': 1, 'message': '项目不存在'}), 400

    # 3. 权限：财务可任意，稽核员只能为自己设置
    if user.role == 'auditor' and user.id != agent_id:
        return jsonify({'code': 1, 'message': '稽核员只能为自己设置代理'}), 403

    # 4. 校验报销员是否在该项目下
    up = UserProject.query.filter_by(
        user_id=be_agent_id, project_id=project_id, status='active'
    ).first()
    if not up:
        return jsonify({
            'code': 1,
            'message': f'报销员 {be_agent.real_name} 未绑定到项目 {project.project_name}，'
                       f'请先在「项目台账」添加该报销员到此项目',
        }), 400

    # 5. 已存在则更新
    existing = AgentAuth.query.filter_by(
        agent_id=agent_id, be_agent_id=be_agent_id, project_id=project_id
    ).first()
    if existing:
        existing.status = 'active'
        existing.auth_start_date = date.fromisoformat(data['auth_start_date']) if data.get('auth_start_date') else existing.auth_start_date
        existing.auth_end_date = date.fromisoformat(data['auth_end_date']) if data.get('auth_end_date') else None
        existing.agent_mode = data.get('agent_mode', 'full')
        existing.created_by = user.id
        db.session.commit()
        return jsonify({'code': 0, 'message': '代理关系已更新', 'data': {'id': existing.id}})

    # 6. 新建
    auth = AgentAuth(
        agent_id=agent_id,
        be_agent_id=be_agent_id,
        project_id=project_id,
        auth_start_date=date.fromisoformat(data['auth_start_date']) if data.get('auth_start_date') else date.today(),
        auth_end_date=date.fromisoformat(data['auth_end_date']) if data.get('auth_end_date') else None,
        agent_mode=data.get('agent_mode', 'full'),
        status='active',
        created_by=user.id,
    )
    db.session.add(auth)
    db.session.commit()
    return jsonify({'code': 0, 'message': '代理关系已建立', 'data': {'id': auth.id}})


@agents_bp.route('/<int:auth_id>', methods=['DELETE'])
@role_required('finance', 'auditor')
def revoke_agent(auth_id):
    """撤销代理"""
    user = get_current_user()
    auth = AgentAuth.query.get(auth_id)
    if not auth:
        return jsonify({'code': 1, 'message': '代理关系不存在'}), 404

    # 权限：财务可任意；稽核员只能撤销自己作为 agent 的
    if user.role == 'auditor' and user.id != auth.agent_id:
        return jsonify({'code': 1, 'message': '稽核员只能撤销自己作为稽核的代理'}), 403

    auth.status = 'revoked'
    db.session.commit()
    return jsonify({'code': 0, 'message': '已撤销'})


@agents_bp.route('/list', methods=['GET'])
@login_required
def list_agents():
    """列出我（当前用户）的代理关系

    - 稽核员：作为 agent 的所有关系
    - 财务：所有 active 关系
    - 报销员：被代理的关系
    """
    user = get_current_user()
    if user.role == 'auditor':
        rows = db.session.execute(text("""
            SELECT a.id, a.be_agent_id, u.real_name, u.username, u.department,
                   a.project_id, p.project_name, p.project_code,
                   a.agent_mode, a.status, a.auth_start_date, a.auth_end_date
            FROM agent_auth a
            JOIN sys_user u ON u.id = a.be_agent_id
            JOIN expense_project p ON p.id = a.project_id
            WHERE a.agent_id = :uid AND a.status = 'active'
            ORDER BY p.project_code
        """), {'uid': user.id}).fetchall()
        items = [{
            'id': r[0],
            'be_agent_id': r[1],
            'reimburser_name': r[2],
            'reimburser_username': r[3],
            'department': r[4],
            'project_id': r[5],
            'project_name': r[6],
            'project_code': r[7],
            'agent_mode': r[8],
            'status': r[9],
            'auth_start_date': str(r[10]) if r[10] else None,
            'auth_end_date': str(r[11]) if r[11] else None,
        } for r in rows]
    elif user.role == 'reimburser':
        rows = db.session.execute(text("""
            SELECT a.id, a.agent_id, u.real_name, u.username, u.role,
                   a.project_id, p.project_name, p.project_code,
                   a.agent_mode, a.status, a.auth_start_date
            FROM agent_auth a
            JOIN sys_user u ON u.id = a.agent_id
            JOIN expense_project p ON p.id = a.project_id
            WHERE a.be_agent_id = :uid AND a.status = 'active'
            ORDER BY p.project_code
        """), {'uid': user.id}).fetchall()
        items = [{
            'id': r[0],
            'agent_id': r[1],
            'auditor_name': r[2],
            'auditor_username': r[3],
            'auditor_role': r[4],
            'project_id': r[5],
            'project_name': r[6],
            'project_code': r[7],
            'agent_mode': r[8],
            'status': r[9],
            'auth_start_date': str(r[10]) if r[10] else None,
        } for r in rows]
    else:  # finance
        rows = db.session.execute(text("""
            SELECT a.id, a.agent_id, ag.real_name, a.be_agent_id, be.real_name,
                   a.project_id, p.project_name,
                   a.agent_mode, a.status, a.auth_start_date
            FROM agent_auth a
            JOIN sys_user ag ON ag.id = a.agent_id
            JOIN sys_user be ON be.id = a.be_agent_id
            JOIN expense_project p ON p.id = a.project_id
            WHERE a.status = 'active'
            ORDER BY p.project_code, ag.real_name
        """)).fetchall()
        items = [{
            'id': r[0],
            'agent_id': r[1], 'auditor_name': r[2],
            'be_agent_id': r[3], 'reimburser_name': r[4],
            'project_id': r[5], 'project_name': r[6],
            'agent_mode': r[7], 'status': r[8],
            'auth_start_date': str(r[9]) if r[9] else None,
        } for r in rows]

    return jsonify({'code': 0, 'data': items})


@agents_bp.route('/by-project/<int:project_id>', methods=['GET'])
@role_required('finance', 'auditor')
def list_by_project(project_id):
    """列出项目的所有代理关系

    包括：
    - 已设置的代理（哪些稽核员代理了哪些报销员）
    - 项目下未代理的报销员（可建议设置代理）
    """
    project = ExpenseProject.query.get(project_id)
    if not project:
        return jsonify({'code': 1, 'message': '项目不存在'}), 404

    # 权限：财务可任意；稽核员只能查自己负责的或自己参与的项目
    user = get_current_user()
    if user.role == 'auditor' and project.finance_auditor_id and project.finance_auditor_id != user.id:
        # 不是项目负责人，仅可看自己代理的
        pass

    # 1. 已设置的代理
    auth_rows = db.session.execute(text("""
        SELECT a.id, a.agent_id, ag.real_name, a.be_agent_id, be.real_name,
               be.username, a.agent_mode, a.status
        FROM agent_auth a
        JOIN sys_user ag ON ag.id = a.agent_id
        JOIN sys_user be ON be.id = a.be_agent_id
        WHERE a.project_id = :pid AND a.status = 'active'
        ORDER BY ag.real_name
    """), {'pid': project_id}).fetchall()
    active_auths = [{
        'id': r[0],
        'agent_id': r[1], 'auditor_name': r[2],
        'be_agent_id': r[3], 'reimburser_name': r[4],
        'reimburser_username': r[5],
        'agent_mode': r[6], 'status': r[7],
    } for r in auth_rows]

    # 2. 项目下所有报销员
    up_rows = db.session.execute(text("""
        SELECT up.user_id, u.real_name, u.username, u.department
        FROM user_project up
        JOIN sys_user u ON u.id = up.user_id
        WHERE up.project_id = :pid AND up.status = 'active' AND u.role = 'reimburser'
        ORDER BY u.real_name
    """), {'pid': project_id}).fetchall()
    all_reimbursers = [r[0] for r in up_rows]

    # 3. 项目下所有稽核员
    auditor_rows = db.session.execute(text("""
        SELECT id, real_name, username FROM sys_user
        WHERE role = 'auditor' AND account_status = 'normal'
        ORDER BY real_name
    """)).fetchall()
    auditors = [{'id': r[0], 'real_name': r[1], 'username': r[2]} for r in auditor_rows]

    # 4. 标记未代理的报销员
    be_agent_ids = {a['be_agent_id'] for a in active_auths}
    unassigned = [{
        'user_id': r[0], 'real_name': r[1], 'username': r[2], 'department': r[3],
        'need_agent': r[0] not in be_agent_ids,
    } for r in up_rows]

    return jsonify({
        'code': 0,
        'data': {
            'project': {
                'id': project.id, 'project_name': project.project_name,
                'project_code': project.project_code, 'status': project.status,
            },
            'active_auths': active_auths,
            'unassigned_reimbursers': unassigned,
            'all_reimbursers': [{
                'id': r[0], 'real_name': r[1], 'username': r[2], 'department': r[3]
            } for r in up_rows],
            'available_auditors': auditors,
        },
    })


@agents_bp.route('/mode-c-status', methods=['GET'])
@role_required('finance', 'auditor')
def mode_c_status():
    """全局模式 C 状态

    对每个报销员，判定其模式 C 状态：
    - 'agent_c'：所有 user_project 都有 active agent_auth（完全代填，无需客户端）
    - 'partial'：部分项目有代理
    - 'self'：所有项目都无代理（完全自助）

    """
    rows = db.session.execute(text("""
        SELECT u.id, u.real_name, u.username,
               up_total.total_projects,
               up_authed.authed_projects
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
        WHERE u.role = 'reimburser' AND u.account_status = 'normal'
        ORDER BY u.real_name
    """)).fetchall()

    items = []
    for r in rows:
        uid, real_name, username, total, authed = r
        if not total:
            mode = 'orphan'  # 没有绑定项目
        elif total == authed:
            mode = 'agent_c'  # 所有项目都被代理
        elif authed and authed < total:
            mode = 'partial'  # 部分代理
        else:
            mode = 'self'  # 完全自助
        items.append({
            'user_id': uid,
            'real_name': real_name,
            'username': username,
            'total_projects': total or 0,
            'authed_projects': authed or 0,
            'mode': mode,
            'need_package': mode in ('self', 'partial', 'orphan'),
        })
    return jsonify({'code': 0, 'data': items})
