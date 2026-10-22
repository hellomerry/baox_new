"""数据导入路由（v2.3.0）

- 模板下载
- 上传 + 预览（不写入）
- 确认导入
- 历史查询
"""
import json
import logging
from flask import Blueprint, request, jsonify, send_file, g
from io import BytesIO
from werkzeug.utils import secure_filename

from services.data_import_service import do_import
from utils.excel_import import read_excel, generate_template, file_hash, TEMPLATES
from models.models import db, DataImportLog
from utils.decorators import get_current_user, role_required

data_import_bp = Blueprint('data_import', __name__, url_prefix='/api/data-import')
log = logging.getLogger(__name__)


# ============= 模板下载 =============

@data_import_bp.route('/template/<import_type>', methods=['GET'])
@role_required('admin', 'finance')
def download_template(import_type):
    """下载 Excel 模板"""
    if import_type not in TEMPLATES:
        return jsonify({'code': 1, 'message': f'未知类型: {import_type}'}), 400
    tpl = TEMPLATES[import_type]
    xlsx_bytes = generate_template(import_type)
    fname = f'{tpl["name"]}_模板.xlsx'
    return send_file(
        BytesIO(xlsx_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=fname,
    )


@data_import_bp.route('/templates', methods=['GET'])
@role_required('admin', 'finance')
def list_templates():
    """列出所有可用模板（用于前端下拉）"""
    return jsonify({
        'code': 0,
        'data': [
            {
                'type': k,
                'name': v['name'],
                'columns': [
                    {
                        'key': c['key'],
                        'label': c['label'],
                        'required': c.get('required', False),
                        'type': c.get('type', 'str'),
                        'choices': c.get('choices', []),
                        'note': c.get('note', ''),
                    }
                    for c in v['columns']
                ],
            }
            for k, v in TEMPLATES.items()
        ],
    })


# ============= 上传 + 预览 =============

@data_import_bp.route('/preview', methods=['POST'])
@role_required('admin', 'finance')
def preview():
    """上传 Excel 解析预览（不写入 DB）

    form-data:
        file: .xlsx
        import_type: user / project / standard
    """
    import_type = request.form.get('import_type') or (request.json or {}).get('import_type')
    if import_type not in TEMPLATES:
        return jsonify({'code': 1, 'message': f'未知类型: {import_type}'}), 400

    if 'file' not in request.files:
        return jsonify({'code': 1, 'message': '请上传文件'}), 400

    f = request.files['file']
    if not f.filename or not f.filename.endswith('.xlsx'):
        return jsonify({'code': 1, 'message': '只支持 .xlsx 文件'}), 400

    file_bytes = f.read()
    if len(file_bytes) > 20 * 1024 * 1024:  # 20MB
        return jsonify({'code': 1, 'message': '文件超过 20MB'}), 400

    try:
        result = read_excel(import_type, file_bytes)
    except Exception as e:
        log.exception('read_excel failed')
        return jsonify({'code': 1, 'message': f'解析失败: {e}'}), 400

    valid_count = sum(1 for r in result['rows'] if r['_valid'])
    invalid_count = sum(1 for r in result['rows'] if not r['_valid'])

    return jsonify({
        'code': 0,
        'data': {
            'total_rows': result['total_rows'],
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'file_hash': file_hash(file_bytes),
            'file_size': len(file_bytes),
            'rows': [
                # 简化返回：只返必要字段
                {k: v for k, v in r.items() if not k.startswith('_')} | {
                    '_row': r['_row'],
                    '_valid': r['_valid'],
                    '_errors': r['_errors'],
                }
                for r in result['rows']
            ],
        },
    })


# ============= 确认导入 =============

@data_import_bp.route('/commit', methods=['POST'])
@role_required('admin', 'finance')
def commit_import():
    """确认导入（写入 DB）

    body: {
        import_type, rows, file_hash, file_size, file_name
    }
    """
    user = get_current_user()
    data = request.get_json() or {}

    import_type = data.get('import_type')
    rows = data.get('rows', [])
    f_hash = data.get('file_hash')
    f_size = data.get('file_size', 0)
    f_name = data.get('file_name', 'unknown.xlsx')

    if import_type not in TEMPLATES:
        return jsonify({'code': 1, 'message': f'未知类型: {import_type}'}), 400

    if not rows:
        return jsonify({'code': 1, 'message': '没有数据行'}), 400

    try:
        log_entry = do_import(
            import_type=import_type,
            rows=rows,
            operator_id=user.id,
            file_name=f_name,
            file_hash=f_hash or '',
            file_size=f_size,
        )
    except Exception as e:
        log.exception('do_import failed')
        return jsonify({'code': 1, 'message': f'导入失败: {e}'}), 500

    return jsonify({
        'code': 0,
        'message': f'导入完成：成功 {log_entry.success_count}，失败 {log_entry.failed_count}',
        'data': log_entry.to_dict(),
    })


# ============= 历史查询 =============

@data_import_bp.route('/history', methods=['GET'])
@role_required('admin', 'finance')
def history():
    """导入历史"""
    import_type = request.args.get('import_type')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    q = DataImportLog.query
    if import_type:
        q = q.filter_by(import_type=import_type)
    items = q.order_by(DataImportLog.imported_at.desc()).offset(offset).limit(limit).all()
    total = q.count()

    return jsonify({
        'code': 0,
        'data': [i.to_dict() for i in items],
        'total': total,
    })


@data_import_bp.route('/history/<int:log_id>', methods=['GET'])
@role_required('admin', 'finance')
def history_detail(log_id):
    """单次导入详情"""
    item = DataImportLog.query.get(log_id)
    if not item:
        return jsonify({'code': 1, 'message': '记录不存在'}), 404
    return jsonify({'code': 0, 'data': item.to_dict()})
