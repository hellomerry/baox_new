"""
考勤服务（T4 + v2.10.0）
- 报销员自助录考勤 → pending → 稽核员审批
- 稽核员代填 → 直接 approved
- 稽核员全权可审批/驳回任何代理报销员的考勤
"""
from datetime import date, datetime
from sqlalchemy import text
from models import db
from models.models import AttendanceRecord as Attendance, AgentAuth, SysUser


class AttendanceService:

    @staticmethod
    def record_attendance(user_id: int, project_id: int, attendance_date: date,
                          status: str = '在岗', remark: str = '',
                          created_by: int = None) -> tuple:
        """录入考勤

        v2.10.0：
        - 报销员自己录 → audit_status='pending'（待稽核员审核）
        - 稽核员代填/财务操作 → audit_status='approved'（自批）
        """
        operator_id = created_by or user_id
        operator = SysUser.query.get(operator_id)
        is_reimburser_self = (operator and operator.role == 'reimburser' and operator.id == user_id)
        is_auditor_or_finance = operator and operator.role in ('auditor', 'finance')

        initial_status = 'approved' if is_auditor_or_finance else 'pending'

        existing = Attendance.query.filter_by(
            user_id=user_id, attendance_date=attendance_date
        ).first()
        if existing:
            existing.status = status
            existing.remark = remark
            if is_auditor_or_finance:
                existing.audit_status = 'approved'
                existing.auditor_id = operator_id
                existing.audited_at = datetime.now()
            else:
                existing.audit_status = 'pending'
                existing.auditor_id = None
                existing.audited_at = None
        else:
            att = Attendance(
                user_id=user_id,
                project_id=project_id,
                attendance_date=attendance_date,
                status=status,
                remark=remark,
                audit_status=initial_status,
                created_by=operator_id,
            )
            if is_auditor_or_finance:
                att.auditor_id = operator_id
                att.audited_at = datetime.now()
            db.session.add(att)
        db.session.commit()

        if is_reimburser_self:
            return True, '考勤已提交，等待稽核员审核'
        return True, '考勤已记录（已自动审核）'

    @staticmethod
    def record_for_user(agent_id: int, be_agent_id: int, project_id: int,
                          attendance_date: date, status: str = '在岗',
                          remark: str = '') -> tuple:
        """稽核员代填考勤（v2.10.0 模式 C）

        v2.10.0 代理权限分级：
        - agent_mode='full'：可代填
        - agent_mode='attendance_only' 或 'full'：可代填
        - agent_mode='bill_only'：不可代填
        """
        agent = SysUser.query.get(agent_id)
        if not agent or agent.role != 'auditor':
            return False, '操作人不是稽核员'

        be_agent = SysUser.query.get(be_agent_id)
        if not be_agent or be_agent.role != 'reimburser':
            return False, '代填目标不是报销员'

        auth = AgentAuth.query.filter_by(
            agent_id=agent_id, be_agent_id=be_agent_id, status='active'
        ).first()
        if not auth:
            return False, '您没有该报销员的代填权限（请先建立代理关系）'

        # 权限校验：bill_only 不能代填考勤
        if auth.agent_mode == 'bill_only':
            return False, '该代理关系仅限代填报销，不可代填考勤'

        ok, msg = AttendanceService.record_attendance(
            user_id=be_agent_id,
            project_id=project_id,
            attendance_date=attendance_date,
            status=status,
            remark=remark,
            created_by=agent_id,
        )
        return ok, msg

    @staticmethod
    def audit_attendance(operator_id: int, attendance_id: int,
                          decision: str, comment: str = '') -> tuple:
        """稽核员审核考勤

        校验：
        - decision 必须是 approved/rejected
        - 必须是稽核员
        - 必须是代理的报销员
        """
        if decision not in ('approved', 'rejected'):
            return False, 'decision 必须是 approved/rejected'

        att = Attendance.query.get(attendance_id)
        if not att:
            return False, '考勤记录不存在'
        if att.audit_status == 'approved':
            return False, '已审核通过，不能重复审批'

        # 校验稽核员身份 + 代理关系
        operator = SysUser.query.get(operator_id)
        if not operator or operator.role != 'auditor':
            return False, '仅稽核员可审批'

        auth = AgentAuth.query.filter_by(
            agent_id=operator_id, be_agent_id=att.user_id, status='active'
        ).first()
        if not auth:
            return False, '该报销员不在您代理范围'

        att.audit_status = decision
        att.auditor_id = operator_id
        att.audited_at = datetime.now()
        att.audit_comment = comment
        db.session.commit()
        return True, f'考勤已{"通过" if decision == "approved" else "驳回"}'

    @staticmethod
    def list_pending(agent_id: int = None) -> list:
        """列出待审考勤（稽核员视角）"""
        if agent_id:
            # 只列出代理报销员的待审
            rows = db.session.execute(text("""
                SELECT a.* FROM attendance_record a
                JOIN agent_auth aa ON aa.be_agent_id = a.user_id
                WHERE a.audit_status = 'pending' AND aa.agent_id = :aid AND aa.status = 'active'
                ORDER BY a.attendance_date DESC
            """), {'aid': agent_id}).fetchall()
            ids = [r[0] for r in rows]
            return Attendance.query.filter(Attendance.id.in_(ids)).order_by(Attendance.attendance_date.desc()).all() if ids else []
        return Attendance.query.filter_by(audit_status='pending').order_by(Attendance.attendance_date.desc()).all()

    @staticmethod
    def is_under_agent(user_id: int) -> bool:
        row = db.session.execute(text(
            "SELECT 1 FROM agent_auth WHERE be_agent_id = :uid AND status = 'active' LIMIT 1"
        ), {'uid': user_id}).fetchone()
        return row is not None

    @staticmethod
    def get_agents_for(user_id: int) -> list:
        rows = db.session.execute(text(
            "SELECT agent_id FROM agent_auth WHERE be_agent_id = :uid AND status = 'active'"
        ), {'uid': user_id}).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def list_attendance(user_id: int, start: date, end: date) -> list:
        return Attendance.query.filter(
            Attendance.user_id == user_id,
            Attendance.attendance_date >= start,
            Attendance.attendance_date <= end,
        ).order_by(Attendance.attendance_date.asc()).all()
