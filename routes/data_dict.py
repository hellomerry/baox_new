"""数据字典路由（v2.5.0）"""
from flask import Blueprint, jsonify
from services.data_dict_service import get_all_tables, get_table_detail, get_stats
from utils.decorators import login_required, get_current_user

data_dict_bp = Blueprint('data_dict', __name__, url_prefix='/api/data-dict')


@data_dict_bp.route('/tables', methods=['GET'])
@login_required
def list_tables():
    """列出所有表"""
    user = get_current_user()
    return jsonify({
        'code': 0,
        'data': get_all_tables(),
    })


@data_dict_bp.route('/tables/<name>', methods=['GET'])
@login_required
def table_detail(name):
    """单表详情"""
    detail = get_table_detail(name)
    if not detail:
        return jsonify({'code': 1, 'message': f'表 {name} 不存在'}), 404
    return jsonify({'code': 0, 'data': detail})


@data_dict_bp.route('/stats', methods=['GET'])
@login_required
def stats():
    """数据字典统计"""
    return jsonify({'code': 0, 'data': get_stats()})
