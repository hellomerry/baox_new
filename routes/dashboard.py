from datetime import datetime
"""可视化大屏路由（v2.6.0）"""
from flask import Blueprint, jsonify, request

from services.dashboard_service import (
    dashboard_overview,
    bill_status_distribution,
    monthly_trend, project_amount_top, user_amount_top,
    _svg_bar, _svg_pie, _svg_line,
)
from utils.decorators import login_required, get_current_user

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


@dashboard_bp.route('/overview', methods=['GET'])
@login_required
def overview():
    """总览数据"""
    user = get_current_user()
    year = request.args.get('year', type=int)
    return jsonify({'code': 0, 'data': dashboard_overview(year)})


@dashboard_bp.route('/charts', methods=['GET'])
@login_required
def charts():
    """所有图表（SVG）"""
    user = get_current_user()
    year = request.args.get('year', type=int) or None

    monthly = monthly_trend(year)
    proj_top = project_amount_top(5)
    user_top = user_amount_top(5)
    status_dist = bill_status_distribution()

    return jsonify({
        'code': 0,
        'data': {
            'year': year or '',
            'monthly_svg': _svg_line(
                monthly, 'amount', 'month_name',
                title=f'{year or datetime.now().year} 年月度报销趋势（元）'
            ),
            'monthly_count_svg': _svg_line(
                monthly, 'count', 'month_name',
                color='#27ae60',
                title='月度单据数（单）'
            ),
            'project_svg': _svg_bar(
                proj_top, 'amount', 'project_name',
                color='#4472C4',
                title='项目金额 TOP 5'
            ),
            'user_svg': _svg_bar(
                user_top, 'amount', 'real_name',
                color='#e67e22',
                title='报销人金额 TOP 5'
            ),
            'status_svg': _svg_pie(
                status_dist,
                title='单据状态分布'
            ),
        },
    })



