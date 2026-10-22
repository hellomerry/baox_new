"""可视化大屏 service（v2.6.0）

服务端生成 SVG 图表（无外部依赖）
"""
import io
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict

from models import db
from models.models import (
    ExpenseBill, ExpenseProject, SysUser, AuditLog,
    ResearchAuditLog, Notification, DataImportLog, AppVersion,
)
from sqlalchemy import func

log = logging.getLogger(__name__)


# ============= 公共统计 =============

def dashboard_overview(year: int = None) -> Dict:
    """总览数据"""
    y = year or datetime.now().year
    # 单据总数
    bill_count = ExpenseBill.query.count()
    archived = ExpenseBill.query.filter_by(status='archived').count()
    pending = ExpenseBill.query.filter(
        ExpenseBill.status.in_(['submitted_auditor', 'submitted_finance', 'pending_dual_sign'])
    ).count()

    # 金额统计
    total_amount = db.session.query(func.sum(ExpenseBill.total_amount)).filter(
        ExpenseBill.status.in_(['approved', 'archived'])
    ).scalar() or 0
    year_amount = db.session.query(func.sum(ExpenseBill.total_amount)).filter(
        ExpenseBill.status.in_(['approved', 'archived']),
        func.extract('year', ExpenseBill.created_at) == y,
    ).scalar() or 0

    # 用户
    user_count = SysUser.query.filter_by(account_status='normal').count()
    finance_count = SysUser.query.filter_by(role='finance', account_status='normal').count()
    auditor_count = SysUser.query.filter_by(role='auditor', account_status='normal').count()
    reimb_count = SysUser.query.filter_by(role='reimburser', account_status='normal').count()

    # 项目
    project_count = ExpenseProject.query.filter_by(status='active').count()

    # 通知
    notif_count = Notification.query.count()
    unread_count = Notification.query.filter_by(is_read=False).count()

    # 审计
    audit_count = ResearchAuditLog.query.count()

    # 数据库版本
    latest = AppVersion.query.order_by(AppVersion.release_date.desc()).first()
    db_version = latest.version if latest else '?'

    return {
        'year': y,
        'bill_count': bill_count,
        'archived': archived,
        'pending': pending,
        'total_amount': float(total_amount),
        'year_amount': float(year_amount),
        'user_count': user_count,
        'finance_count': finance_count,
        'auditor_count': auditor_count,
        'reimb_count': reimb_count,
        'project_count': project_count,
        'notif_count': notif_count,
        'unread_count': unread_count,
        'audit_count': audit_count,
        'db_version': db_version,
    }


def bill_status_distribution() -> Dict:
    """单据状态分布（饼图数据）"""
    rows = db.session.query(
        ExpenseBill.status, func.count(ExpenseBill.id)
    ).group_by(ExpenseBill.status).all()
    return {r[0]: r[1] for r in rows if r[0]}


def monthly_trend(year: int = None) -> List[Dict]:
    """月度趋势（折线图）"""
    y = year or datetime.now().year
    rows = db.session.query(
        func.extract('month', ExpenseBill.created_at).label('month'),
        func.count(ExpenseBill.id).label('count'),
        func.sum(ExpenseBill.total_amount).label('amount'),
    ).filter(
        ExpenseBill.status.in_(['approved', 'archived']),
        func.extract('year', ExpenseBill.created_at) == y,
    ).group_by('month').all()

    result = []
    month_map = {int(r[0]): {'count': r[1], 'amount': float(r[2] or 0)} for r in rows}
    for m in range(1, 13):
        info = month_map.get(m, {'count': 0, 'amount': 0})
        result.append({
            'month': m,
            'month_name': f'{m}月',
            'count': info['count'],
            'amount': info['amount'],
        })
    return result


def project_amount_top(limit: int = 10) -> List[Dict]:
    """项目金额 TOP N（条形图）"""
    rows = db.session.query(
        ExpenseProject.id,
        ExpenseProject.project_code,
        ExpenseProject.project_name,
        func.count(ExpenseBill.id).label('bill_count'),
        func.sum(ExpenseBill.total_amount).label('amount'),
    ).join(ExpenseBill, ExpenseBill.project_id == ExpenseProject.id).filter(
        ExpenseBill.status.in_(['approved', 'archived'])
    ).group_by(
        ExpenseProject.id
    ).order_by(
        func.sum(ExpenseBill.total_amount).desc()
    ).limit(limit).all()

    return [
        {
            'project_id': r[0],
            'project_code': r[1],
            'project_name': r[2],
            'bill_count': r[3],
            'amount': float(r[4] or 0),
        }
        for r in rows
    ]


def user_amount_top(limit: int = 10) -> List[Dict]:
    """报销人金额 TOP N"""
    rows = db.session.query(
        SysUser.id,
        SysUser.real_name,
        SysUser.department,
        func.count(ExpenseBill.id).label('bill_count'),
        func.sum(ExpenseBill.total_amount).label('amount'),
    ).join(ExpenseBill, ExpenseBill.user_id == SysUser.id).filter(
        ExpenseBill.status.in_(['approved', 'archived'])
    ).group_by(
        SysUser.id
    ).order_by(
        func.sum(ExpenseBill.total_amount).desc()
    ).limit(limit).all()

    return [
        {
            'user_id': r[0],
            'real_name': r[1],
            'department': r[2] or '',
            'bill_count': r[3],
            'amount': float(r[4] or 0),
        }
        for r in rows
    ]


# ============= SVG 图表生成器 =============

def _svg_bar(data: List[Dict], value_key: str, label_key: str, width: int = 600, height: int = 300,
             color: str = '#4472C4', title: str = '') -> str:
    """水平条形图 SVG"""
    if not data:
        return f'<svg width="{width}" height="100"><text x="20" y="30" fill="#999">无数据</text></svg>'

    max_val = max(d[value_key] for d in data) or 1
    bar_h = (height - 40) // len(data)
    label_w = 100
    bar_area_w = width - label_w - 60

    parts = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:white;border-radius:6px;">']
    if title:
        parts.append(f'<text x="{width//2}" y="20" text-anchor="middle" font-size="14" font-weight="bold" fill="#2c3e50">{title}</text>')
    for i, d in enumerate(data):
        y = 30 + i * bar_h
        bw = int(bar_area_w * d[value_key] / max_val)
        parts.append(f'<text x="{label_w - 5}" y="{y + bar_h//2 + 4}" text-anchor="end" font-size="11" fill="#555">{d[label_key][:12]}</text>')
        parts.append(f'<rect x="{label_w}" y="{y + 4}" width="{bw}" height="{bar_h - 8}" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{label_w + bw + 5}" y="{y + bar_h//2 + 4}" font-size="11" fill="#333">{d[value_key]:,.0f}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def _svg_pie(data: Dict[str, int], width: int = 400, height: int = 300, title: str = '') -> str:
    """饼图 SVG"""
    if not data:
        return f'<svg width="{width}" height="100"><text x="20" y="30" fill="#999">无数据</text></svg>'

    total = sum(data.values()) or 1
    colors = ['#4472C4', '#27ae60', '#e67e22', '#e74c3c', '#9b59b6', '#16a085', '#34495e', '#f39c12']
    cx, cy, r = width // 2, (height + 30) // 2, min(width, height) // 3

    parts = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:white;border-radius:6px;">']
    if title:
        parts.append(f'<text x="{width//2}" y="20" text-anchor="middle" font-size="14" font-weight="bold" fill="#2c3e50">{title}</text>')

    start = 0
    import math
    for i, (k, v) in enumerate(data.items()):
        end = start + (v / total) * 2 * math.pi
        x1 = cx + r * math.cos(start - math.pi/2)
        y1 = cy + r * math.sin(start - math.pi/2)
        x2 = cx + r * math.cos(end - math.pi/2)
        y2 = cy + r * math.sin(end - math.pi/2)
        large = 1 if (end - start) > math.pi else 0
        d = f'M {cx} {cy} L {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f} Z'
        parts.append(f'<path d="{d}" fill="{colors[i % len(colors)]}" stroke="white" stroke-width="1"/>')
        # 图例
        lx = 10
        ly = 30 + i * 18
        parts.append(f'<rect x="{lx}" y="{ly}" width="10" height="10" fill="{colors[i % len(colors)]}"/>')
        parts.append(f'<text x="{lx + 14}" y="{ly + 9}" font-size="11" fill="#333">{k} ({v})</text>')
        start = end
    parts.append('</svg>')
    return ''.join(parts)


def _svg_line(data: List[Dict], value_key: str, label_key: str, width: int = 700, height: int = 300,
              color: str = '#4472C4', title: str = '') -> str:
    """折线图 SVG"""
    if not data:
        return f'<svg width="{width}" height="100"><text x="20" y="30" fill="#999">无数据</text></svg>'

    max_val = max(d[value_key] for d in data) or 1
    margin = 40
    plot_w = width - margin * 2
    plot_h = height - margin * 2

    parts = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:white;border-radius:6px;">']
    if title:
        parts.append(f'<text x="{width//2}" y="20" text-anchor="middle" font-size="14" font-weight="bold" fill="#2c3e50">{title}</text>')

    # 坐标轴
    parts.append(f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#ddd"/>')
    parts.append(f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#ddd"/>')

    # 数据点
    n = len(data)
    if n < 2:
        parts.append('</svg>')
        return ''.join(parts)

    points = []
    for i, d in enumerate(data):
        x = margin + (plot_w * i / (n - 1))
        y = height - margin - (plot_h * d[value_key] / max_val)
        points.append((x, y))
        # X 标签
        parts.append(f'<text x="{x}" y="{height - margin + 14}" text-anchor="middle" font-size="10" fill="#777">{d[label_key]}</text>')

    # 折线
    line_d = f'M {points[0][0]:.1f} {points[0][1]:.1f} ' + ' '.join(f'L {x:.1f} {y:.1f}' for x, y in points[1:])
    parts.append(f'<path d="{line_d}" stroke="{color}" stroke-width="2" fill="none"/>')
    for x, y in points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    parts.append('</svg>')
    return ''.join(parts)
