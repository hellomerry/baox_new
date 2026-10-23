"""
Word 报表导出工具
- 与 services/report_service 的 Excel 导出一一对应：
  项目汇总 / 报销人汇总 / 月度汇总 / 单据明细 / 综合报表
- 横版 A4（与 PDF 报表风格一致），复用 utils/word_export 的制式表格助手
- 返回 .docx bytes（内存生成，走 BytesIO）
"""
import io
from datetime import datetime

from services.report_service import ReportService, STATUS_NAMES
from utils.word_export import (
    _body_para, _cell_text, _new_doc, _repeat_header, _row_cant_split,
    _row_keep_next, _section_heading, _set_cell_bg, _set_col_widths,
    _set_row_height, _set_table_borders, _spacer, _title,
)

# 表头底色（与 Excel 报表 #34495e 一致）
HEADER_BG = '34495E'
TOTAL_BG = 'E8EDF2'
ZEBRA_BG = 'F5F7FA'

# 横版内容区宽度（A4 29.7cm - 左右边距 2cm × 2）
LANDSCAPE_WIDTH_CM = 25.7


def _money(v) -> str:
    """金额千分位两位小数"""
    return f'{float(v or 0):,.2f}'


def _meta(doc, start_date, end_date, extra=None):
    """报表元信息行：统计周期 + 生成时间"""
    period = f'{start_date or "全部"} 至 {end_date or "全部"}'
    _body_para(doc, f'统计周期：{period}', indent=False)
    _body_para(doc, f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
               indent=False)
    if extra:
        _body_para(doc, extra, indent=False)
    _spacer(doc, 2)


def _render_table(doc, headers, rows, widths, *, size=9, right_cols=(), bold_last=True):
    """通用制式数据表：深色表头 + 斑马纹 + 合计行强调 + 跨页表头重复"""
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    _set_table_borders(t)
    _set_col_widths(t, widths)

    head = t.rows[0]
    _set_row_height(head, 0.65)
    _row_cant_split(head)
    _repeat_header(head)
    _row_keep_next(head)
    for cell, text in zip(head.cells, headers):
        _cell_text(cell, text, bold=True, size=size, color='FFFFFF')
        _set_cell_bg(cell, HEADER_BG)

    n_data = len(rows)
    for i, row in enumerate(rows):
        r = t.rows[i + 1]
        _set_row_height(r, 0.6)
        _row_cant_split(r)
        is_total = bold_last and i == n_data - 1
        for j, (cell, val) in enumerate(zip(r.cells, row)):
            align = 'right' if j in right_cols else 'center'
            if isinstance(val, str) and len(val) > 12:
                align = 'left'
            _cell_text(cell, val, size=size, bold=is_total, align=align)
            if is_total:
                _set_cell_bg(cell, TOTAL_BG)
            elif i % 2 == 1:
                _set_cell_bg(cell, ZEBRA_BG)
    return t


def _save_bytes(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ============= 单表导出 =============

def export_project_summary_docx(start_date=None, end_date=None) -> bytes:
    """项目汇总 Word（对应 export_project_summary_xlsx）"""
    doc = _new_doc(landscape=True)
    _title(doc, '报销汇总报表 — 项目维度')
    _meta(doc, start_date, end_date)

    data = ReportService.project_summary(start_date, end_date)
    if not data:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')
        return _save_bytes(doc)

    rows = [[r['project_code'], r['project_name'], r['bill_count'],
             _money(r['total_amount'])] for r in data]
    rows.append(['合计', '', sum(r['bill_count'] for r in data),
                 _money(sum(r['total_amount'] for r in data))])
    _render_table(doc, ['项目编号', '项目名称', '单据数', '合计金额（元）'],
                  rows, [4.0, 11.7, 4.0, 6.0], right_cols=(2, 3))
    return _save_bytes(doc)


def export_user_summary_docx(start_date=None, end_date=None) -> bytes:
    """报销人汇总 Word（对应 export_user_summary_xlsx）"""
    doc = _new_doc(landscape=True)
    _title(doc, '报销汇总报表 — 报销人维度')
    _meta(doc, start_date, end_date)

    data = ReportService.user_summary(start_date, end_date)
    if not data:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')
        return _save_bytes(doc)

    rows = [[r['real_name'], r['department'], r['bill_count'],
             _money(r['total_amount'])] for r in data]
    rows.append(['合计', '', sum(r['bill_count'] for r in data),
                 _money(sum(r['total_amount'] for r in data))])
    _render_table(doc, ['报销人', '部门', '单据数', '合计金额（元）'],
                  rows, [4.0, 8.7, 4.0, 9.0], right_cols=(2, 3))
    return _save_bytes(doc)


def export_monthly_summary_docx(year: int) -> bytes:
    """月度汇总 Word（对应 export_monthly_summary_xlsx，补全 12 个月）"""
    doc = _new_doc(landscape=True)
    _title(doc, f'{year} 年月度汇总报表')
    _meta(doc, None, None, extra=f'统计年度：{year} 年')

    data = ReportService.monthly_summary(year)
    month_map = {r['month']: r for r in data}
    rows = []
    total_count = 0
    total_amount = 0.0
    for m in range(1, 13):
        key = f'{year}-{m:02d}'
        r = month_map.get(key, {'bill_count': 0, 'total_amount': 0.0})
        total_count += r['bill_count']
        total_amount += float(r['total_amount'] or 0)
        rows.append([key, r['bill_count'], _money(r['total_amount'])])
    rows.append(['合计', total_count, _money(total_amount)])
    _render_table(doc, ['月份', '单据数', '合计金额（元）'],
                  rows, [8.0, 7.0, 10.7], right_cols=(1, 2))
    return _save_bytes(doc)


def export_bill_detail_docx(
    start_date=None, end_date=None, status=None,
    project_id=None, user_id=None,
) -> bytes:
    """单据明细 Word（对应 export_bill_detail_xlsx，含过滤参数）

    列取 Excel 版子集（去掉大写金额/创建时间），保证横版可读。
    """
    from models import db
    from models.models import ExpenseBill, SysUser, ExpenseProject

    doc = _new_doc(landscape=True)
    _title(doc, '报销单明细报表')
    _meta(doc, start_date, end_date)
    if status:
        _body_para(doc, f'状态筛选：{STATUS_NAMES.get(status, status)}', indent=False)

    q = db.session.query(ExpenseBill).join(SysUser, SysUser.id == ExpenseBill.user_id, isouter=True)
    if start_date:
        q = q.filter(ExpenseBill.travel_start_date >= start_date)
    if end_date:
        q = q.filter(ExpenseBill.travel_end_date <= end_date)
    if status:
        q = q.filter(ExpenseBill.status == status)
    if project_id:
        q = q.filter(ExpenseBill.project_id == project_id)
    if user_id:
        q = q.filter(ExpenseBill.user_id == user_id)

    bills = q.order_by(ExpenseBill.id.desc()).all()
    projects = {p.id: p for p in ExpenseProject.query.all()}

    if not bills:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')
        return _save_bytes(doc)

    rows = []
    total = 0.0
    for b in bills:
        user = db.session.get(SysUser, b.user_id) if b.user_id else None
        project = projects.get(b.project_id)
        amount = float(b.total_amount or 0)
        total += amount
        rows.append([
            b.bill_no or '-',
            user.real_name if user else '-',
            (user.department or '-') if user else '-',
            f'{project.project_code} {project.project_name}' if project else '-',
            b.travel_start_date.isoformat() if b.travel_start_date else '-',
            b.travel_end_date.isoformat() if b.travel_end_date else '-',
            b.destination or '-',
            _money(amount),
            STATUS_NAMES.get(b.status, b.status or '-'),
        ])
    rows.append(['合计', '', '', '', '', '', f'共 {len(bills)} 单',
                 _money(total), ''])

    _render_table(
        doc,
        ['单据编号', '报销人', '部门', '项目', '出差起', '出差止',
         '目的地', '金额（元）', '状态'],
        rows,
        [3.9, 2.5, 3.0, 4.0, 2.6, 2.6, 2.5, 2.3, 2.3],
        right_cols=(7,), size=8.5,
    )
    return _save_bytes(doc)


# ============= 综合报表 =============

def export_comprehensive_docx(year=None, start_date=None, end_date=None) -> bytes:
    """综合报表 Word（对应 export_comprehensive_report 多 sheet xlsx）

    Word 无多 sheet，用分节 + 分页组织：封面元信息 / 项目汇总 / 报销人汇总 /
    月度汇总 / 状态分布 / 单据明细
    """
    from models import db
    from models.models import ExpenseBill, SysUser, ExpenseProject

    doc = _new_doc(landscape=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    period = (f'{start_date or "*"} 至 {end_date or "*"}'
              if (start_date or end_date) else f'{year or "全部"} 年度')

    # ---- 封面 ----
    _title(doc, '报销稽核系统 — 综合报表')
    t = doc.add_table(rows=3, cols=2)
    _set_table_borders(t)
    _set_col_widths(t, [6.0, 19.7])
    for i, (label, value) in enumerate([('报表周期', period),
                                        ('生成时间', now),
                                        ('生成方式', '系统自动')]):
        r = t.rows[i]
        _set_row_height(r, 0.8)
        _row_cant_split(r)
        _cell_text(r.cells[0], label, bold=True)
        _cell_text(r.cells[1], value, align='left')

    # ---- 一、项目汇总 ----
    doc.add_page_break()
    _section_heading(doc, '一、项目汇总')
    data = ReportService.project_summary(start_date, end_date)
    if data:
        rows = [[r['project_code'], r['project_name'], r['bill_count'],
                 _money(r['total_amount'])] for r in data]
        rows.append(['合计', '', sum(r['bill_count'] for r in data),
                     _money(sum(r['total_amount'] for r in data))])
        _render_table(doc, ['项目编号', '项目名称', '单据数', '合计金额（元）'],
                      rows, [4.0, 11.7, 4.0, 6.0], right_cols=(2, 3))
    else:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')

    # ---- 二、报销人汇总 ----
    doc.add_page_break()
    _section_heading(doc, '二、报销人汇总')
    data = ReportService.user_summary(start_date, end_date)
    if data:
        rows = [[r['real_name'], r['department'], r['bill_count'],
                 _money(r['total_amount'])] for r in data]
        rows.append(['合计', '', sum(r['bill_count'] for r in data),
                     _money(sum(r['total_amount'] for r in data))])
        _render_table(doc, ['报销人', '部门', '单据数', '合计金额（元）'],
                      rows, [4.0, 8.7, 4.0, 9.0], right_cols=(2, 3))
    else:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')

    # ---- 三、月度汇总 ----
    doc.add_page_break()
    _section_heading(doc, '三、月度汇总')
    if year:
        data = ReportService.monthly_summary(year)
        month_map = {r['month']: r for r in data}
        rows = []
        total_count = 0
        total_amount = 0.0
        for m in range(1, 13):
            key = f'{year}-{m:02d}'
            r = month_map.get(key, {'bill_count': 0, 'total_amount': 0.0})
            total_count += r['bill_count']
            total_amount += float(r['total_amount'] or 0)
            rows.append([key, r['bill_count'], _money(r['total_amount'])])
        rows.append(['合计', total_count, _money(total_amount)])
        _render_table(doc, ['月份', '单据数', '合计金额（元）'],
                      rows, [8.0, 7.0, 10.7], right_cols=(1, 2))
    else:
        _body_para(doc, '未指定统计年度，跳过月度汇总', indent=False,
                   italic=True, color='888888')

    # ---- 四、状态分布 ----
    doc.add_page_break()
    _section_heading(doc, '四、状态分布')
    status_data = ReportService.status_summary()
    if status_data:
        rows = [[STATUS_NAMES.get(k, k), v['count'], _money(v['total_amount'])]
                for k, v in status_data.items()]
        rows.append(['合计', sum(r[1] for r in rows),
                     _money(sum(v['total_amount'] for v in status_data.values()))])
        _render_table(doc, ['状态', '单据数', '合计金额（元）'],
                      rows, [10.0, 6.0, 9.7], right_cols=(1, 2))
    else:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')

    # ---- 五、单据明细 ----
    doc.add_page_break()
    _section_heading(doc, '五、单据明细')
    q = db.session.query(ExpenseBill)
    if start_date:
        q = q.filter(ExpenseBill.travel_start_date >= start_date)
    if end_date:
        q = q.filter(ExpenseBill.travel_end_date <= end_date)
    bills = q.order_by(ExpenseBill.id.desc()).all()
    projects = {p.id: p for p in ExpenseProject.query.all()}

    if bills:
        rows = []
        total = 0.0
        for b in bills:
            user = db.session.get(SysUser, b.user_id) if b.user_id else None
            project = projects.get(b.project_id)
            amount = float(b.total_amount or 0)
            total += amount
            rows.append([
                b.bill_no or '-',
                user.real_name if user else '-',
                (user.department or '-') if user else '-',
                f'{project.project_code} {project.project_name}' if project else '-',
                b.travel_start_date.isoformat() if b.travel_start_date else '-',
                b.travel_end_date.isoformat() if b.travel_end_date else '-',
                b.destination or '-',
                _money(amount),
                STATUS_NAMES.get(b.status, b.status or '-'),
            ])
        rows.append(['合计', '', '', '', '', '', f'共 {len(bills)} 单',
                     _money(total), ''])
        _render_table(
            doc,
            ['单据编号', '报销人', '部门', '项目', '出差起', '出差止',
             '目的地', '金额（元）', '状态'],
            rows,
            [3.9, 2.5, 3.0, 4.0, 2.6, 2.6, 2.5, 2.3, 2.3],
            right_cols=(7,), size=8.5,
        )
    else:
        _body_para(doc, '无数据', indent=False, italic=True, color='888888')

    doc.core_properties.title = '综合报表'
    doc.core_properties.author = '报销稽核系统'
    return _save_bytes(doc)
