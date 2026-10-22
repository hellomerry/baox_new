"""Excel 导入工具（v2.3.0）

- 读取 .xlsx 文件
- 校验列
- 模板下载
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from io import BytesIO
import hashlib


# ============= 模板定义 =============

# 每种类型的：列名 / 列宽 / 必填 / 类型校验
TEMPLATES = {
    'user': {
        'name': '用户批量导入',
        'sheet_name': '用户',
        'columns': [
            {'key': 'username', 'label': '用户名', 'width': 15, 'required': True, 'type': 'str', 'note': '唯一，登录用'},
            {'key': 'real_name', 'label': '姓名', 'width': 15, 'required': True, 'type': 'str'},
            {'key': 'role', 'label': '角色', 'width': 10, 'required': True, 'type': 'enum',
             'choices': ['finance', 'auditor', 'reimburser']},
            {'key': 'staff_type', 'label': '人员类型', 'width': 10, 'required': True, 'type': 'enum',
             'choices': ['在编', '借调', '跟班', '实战练兵']},
            {'key': 'phone', 'label': '电话', 'width': 15, 'required': False, 'type': 'str'},
            {'key': 'email', 'label': '邮箱', 'width': 25, 'required': False, 'type': 'str'},
            {'key': 'department', 'label': '部门', 'width': 20, 'required': False, 'type': 'str'},
            {'key': 'password', 'label': '初始密码', 'width': 15, 'required': False, 'type': 'str',
             'note': '不填则用默认 NewP@ss123'},
        ],
        'sample': [
            ['zhangsan', '张三', 'reimburser', '在编', '13800138000', 'zs@example.com', '财务部', 'Pass@123'],
            ['lisi', '李四', 'auditor', '在编', '13900139000', 'ls@example.com', '审计部', 'Pass@123'],
        ],
    },
    'project': {
        'name': '项目批量导入',
        'sheet_name': '项目',
        'columns': [
            {'key': 'project_code', 'label': '项目编码', 'width': 15, 'required': True, 'type': 'str', 'note': '唯一'},
            {'key': 'project_name', 'label': '项目名称', 'width': 25, 'required': True, 'type': 'str'},
            {'key': 'project_type', 'label': '项目类型', 'width': 10, 'required': False, 'type': 'str',
             'note': '默认: 普通'},
            {'key': 'start_date', 'label': '开始日期', 'width': 12, 'required': True, 'type': 'date',
             'note': 'YYYY-MM-DD'},
            {'key': 'end_date', 'label': '结束日期', 'width': 12, 'required': True, 'type': 'date',
             'note': 'YYYY-MM-DD'},
            {'key': 'finance_username', 'label': '主审财务', 'width': 15, 'required': False, 'type': 'str',
             'note': '用户账号，财务角色'},
        ],
        'sample': [
            ['PRJ001', '科研项目一', '科研', '2026-01-01', '2026-12-31', 'admin'],
            ['PRJ002', '会议项目二', '会议', '2026-03-01', '2026-06-30', 'admin'],
        ],
    },
    'standard': {
        'name': '报销标准批量导入',
        'sheet_name': '标准',
        'columns': [
            {'key': 'position_code', 'label': '职务等级', 'width': 10, 'required': True, 'type': 'enum',
             'choices': ['PROVINCIAL', 'BUREAU', 'DIVISION', 'OTHER']},
            {'key': 'staff_type', 'label': '人员类型', 'width': 10, 'required': True, 'type': 'enum',
             'choices': ['在编', '借调', '跟班']},
            {'key': 'subsidy_type', 'label': '补助类型', 'width': 10, 'required': True, 'type': 'enum',
             'choices': ['伙食', '住宿', '交通']},
            {'key': 'amount', 'label': '金额（元）', 'width': 12, 'required': True, 'type': 'num'},
            {'key': 'remark', 'label': '备注', 'width': 25, 'required': False, 'type': 'str'},
        ],
        'sample': [
            ['BUREAU', '在编', '伙食', 150, '厅局级 伙食补助'],
            ['BUREAU', '在编', '住宿', 600, '厅局级 住宿标准'],
        ],
    },
}


# ============= 模板下载 =============

def generate_template(import_type: str) -> bytes:
    """生成 Excel 模板 .xlsx bytes"""
    if import_type not in TEMPLATES:
        raise ValueError(f'未知导入类型: {import_type}')

    tpl = TEMPLATES[import_type]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tpl['sheet_name']

    # 标题行
    headers = [col['label'] for col in tpl['columns']]
    ws.append(headers)
    for col_idx, col in enumerate(tpl['columns'], 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='4472C4')
        cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = col['width']

    # 示例数据
    for sample_row in tpl['sample']:
        ws.append(sample_row)

    # 说明 sheet
    note_ws = wb.create_sheet('说明')
    note_ws.append(['字段', '是否必填', '类型', '说明'])
    for col in tpl['columns']:
        note_ws.append([
            col['label'],
            '是' if col.get('required') else '否',
            col.get('type', 'str'),
            col.get('note', ''),
        ])
    for c in ['A1', 'B1', 'C1', 'D1']:
        note_ws[c].font = Font(bold=True)
    for col_idx in range(1, 5):
        note_ws.column_dimensions[get_column_letter(col_idx)].width = 18

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============= 读取 + 校验 =============

def read_excel(import_type: str, file_bytes: bytes) -> dict:
    """读取 + 解析 + 校验

    Returns:
        {
            'total_rows': int,
            'rows': [ {col_key: value, '_row': int, '_errors': [str], '_valid': bool} ],
            'columns': [...],
        }
    """
    if import_type not in TEMPLATES:
        raise ValueError(f'未知导入类型: {import_type}')

    tpl = TEMPLATES[import_type]
    wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    ws = wb[tpl['sheet_name']]

    # 找表头行：支持 key 或 label 匹配
    headers = [c.value for c in ws[1]]
    header_map = {}  # col_key -> col_idx (0-based)
    for col_idx, header in enumerate(headers):
        if header is None:
            continue
        header_str = str(header).strip()
        for col_def in tpl['columns']:
            if col_def['label'] == header_str or col_def['key'] == header_str:
                header_map[col_def['key']] = col_idx
                break

    missing = [c['label'] for c in tpl['columns'] if c['key'] not in header_map]
    if missing:
        # 缺列时给出警告，但不阻断（仅必填列缺失时阻断）
        must_missing = [c['label'] for c in tpl['columns']
                        if c['key'] not in header_map and c.get('required')]
        if must_missing:
            raise ValueError(f'必填列缺失：{", ".join(must_missing)}')

    rows = []
    total = 0
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        # 跳过空行
        if not any(row):
            continue
        total += 1
        record = {'_row': row_idx, '_errors': [], '_valid': True}
        for col_def in tpl['columns']:
            if col_def['key'] not in header_map:
                record[col_def['key']] = None
                continue
            col_idx = header_map[col_def['key']]
            val = row[col_idx] if col_idx < len(row) else None
            record[col_def['key']] = val

        # 校验
        for col_def in tpl['columns']:
            key = col_def['key']
            val = record.get(key)
            # 必填
            if col_def.get('required') and (val is None or val == ''):
                record['_errors'].append(f'{col_def["label"]}：必填')
                record['_valid'] = False
                continue
            # 类型
            if val is not None and val != '':
                t = col_def.get('type', 'str')
                if t == 'enum':
                    if val not in col_def.get('choices', []):
                        record['_errors'].append(
                            f'{col_def["label"]}：必须为 {"/".join(col_def["choices"])}，实际 {val}'
                        )
                        record['_valid'] = False
                elif t == 'num':
                    try:
                        float(val)
                    except (TypeError, ValueError):
                        record['_errors'].append(f'{col_def["label"]}：必须为数字，实际 {val}')
                        record['_valid'] = False
                elif t == 'date':
                    if not isinstance(val, (str, type(__import__('datetime').date))):
                        try:
                            from datetime import datetime, date
                            if isinstance(val, datetime):
                                record[key] = val.date()
                        except Exception:
                            record['_errors'].append(f'{col_def["label"]}：必须为日期')
                            record['_valid'] = False

        rows.append(record)

    return {
        'total_rows': total,
        'rows': rows,
        'columns': tpl['columns'],
    }


def file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()
