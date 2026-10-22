"""
人员服务（T4）
- 报销人 / 稽核员 / 财务账号管理
- 报销人-稽核员-项目绑定（I 决策）
"""
import json
from datetime import datetime, date
from models import db
from models.models import SysUser, AgentAuth, UserProject, UserPosition, PositionLevel, AuditLog
from werkzeug.security import generate_password_hash


class UserService:

    @staticmethod
    def create_user(operator_id: int, user_data: dict) -> tuple:
        """创建人员账号"""
        username = user_data.get('username')
        if not username:
            return False, 'username 必填'

        if SysUser.query.filter_by(username=username).first():
            return False, f'账号 {username} 已存在'

        role = user_data.get('role', 'reimburser')
        if role not in ('reimburser', 'auditor', 'finance'):
            return False, f'role 必须是 reimburser/auditor/finance，当前 {role}'

        # 强制账号类型（N1 字段加密 + C4 自然人 key）
        from utils.crypto import encrypt_field
        from services.natural_person_service import compute_natural_person_key
        id_card_raw = user_data.get('id_card', '')

        user = SysUser(
            username=username,
            real_name=user_data.get('real_name', ''),
            role=role,
            staff_type=user_data.get('staff_type', '在编'),
            department=user_data.get('department'),
            phone=encrypt_field(user_data['phone']) if user_data.get('phone') else None,
            id_card=encrypt_field(id_card_raw) if id_card_raw else None,
            bank_card=encrypt_field(user_data['bank_card']) if user_data.get('bank_card') else None,
            account_status='normal',
            valid_start_date=user_data.get('valid_start_date'),
            valid_end_date=user_data.get('valid_end_date'),
            password_hash='__unset__',  # 必须改密码
            creator_id=operator_id,
            natural_person_key=compute_natural_person_key(id_card_raw) if id_card_raw else None,
        )

        # 初始化密码 = 账号 + '@2026'
        import hashlib
        user.password_hash = hashlib.md5(f'{username}@2026'.encode()).hexdigest()

        db.session.add(user)
        db.session.commit()

        # 操作日志
        operator = SysUser.query.get(operator_id)
        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role if operator else 'unknown',
            action='CREATE_USER',
            target_type='user',
            target_id=str(user.id),
            detail=json.dumps({'username': username, 'role': role}, ensure_ascii=False),
        )
        db.session.add(log)
        db.session.commit()

        return True, f'创建成功，初始密码 {username}@2026', user

    @staticmethod
    def bind_auditor(operator_id: int, reimburser_id: int, auditor_id: int, project_id: int) -> tuple:
        """
        I 决策：报销人 ↔ 稽核员 ↔ 项目 三元绑定
        """
        if reimburser_id == auditor_id:
            return False, '报销人不能与稽核员为同一人'

        user = SysUser.query.get(reimburser_id)
        auditor = SysUser.query.get(auditor_id)
        if not user or not auditor:
            return False, '人员不存在'
        if auditor.role != 'auditor':
            return False, '稽核员角色错误'
        if user.role != 'reimburser':
            return False, '被绑定方必须是报销人'

        # 解除旧绑定
        AgentAuth.query.filter_by(
            be_agent_id=reimburser_id, project_id=project_id
        ).delete()

        # 新绑定
        from datetime import date
        binding = AgentAuth(
            agent_id=auditor_id,
            be_agent_id=reimburser_id,
            project_id=project_id,
            auth_start_date=date.today(),
            agent_mode='full',
            status='active',
            created_by=operator_id,
        )
        db.session.add(binding)

        # 同步项目-人关联
        existing_up = UserProject.query.filter_by(
            user_id=reimburser_id, project_id=project_id, status='active'
        ).first()
        if not existing_up:
            up = UserProject(
                user_id=reimburser_id,
                project_id=project_id,
                status='active',
                created_by=operator_id,
            )
            db.session.add(up)

        operator = SysUser.query.get(operator_id)
        log = AuditLog(
            actor_id=operator_id,
            actor_role=operator.role if operator else 'unknown',
            action='BIND_AUDITOR',
            detail=json.dumps({
                'reimburser_id': reimburser_id,
                'auditor_id': auditor_id,
                'project_id': project_id,
            }, ensure_ascii=False),
        )
        db.session.add(log)
        db.session.commit()

        return True, '绑定成功'

    @staticmethod
    def list_reimbursers(operator_id: int) -> list:
        """列出所有报销人"""
        return SysUser.query.filter_by(role='reimburser', account_status='normal').all()

    @staticmethod
    def list_auditors(operator_id: int) -> list:
        """列出所有稽核员"""
        return SysUser.query.filter_by(role='auditor', account_status='normal').all()

    @staticmethod
    def list_finances(operator_id: int) -> list:
        """列出所有财务"""
        return SysUser.query.filter_by(role='finance', account_status='normal').all()

    @staticmethod
    def assign_position(user_id: int, position_id: int) -> tuple:
        """分配职务级别"""
        user = SysUser.query.get(user_id)
        if not user:
            return False, '人员不存在'
        pos = PositionLevel.query.get(position_id)
        if not pos:
            return False, '职务级别不存在'

        # 解除旧岗位
        UserPosition.query.filter_by(user_id=user_id).delete()

        up = UserPosition(
            user_id=user_id,
            position_id=position_id,
            effective_date=date.today(),
        )
        db.session.add(up)
        db.session.commit()

        return True, '岗位已更新'
