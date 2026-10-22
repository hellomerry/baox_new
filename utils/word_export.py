"""
Word 制式单据导出工具
- 报销单 Word（.docx）输出：A4 纵向、制式表格（实线网格）
- 中文字体：黑体标题 / 宋体正文（eastAsia 字形，Word/WPS 均可正常显示）
- 大写金额（缺失时回退 amount_to_capital）/ 审批意见 / 费用明细 / 签字栏
"""
from datetime import datetime
from decimal import Decimal

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

from utils.bill_number import amount_to_capital

# 制式字体
FONT_TITLE = '黑体'
FONT_BODY = '宋体'

# 内容区总宽（A4 21cm - 左右边距 2cm × 2）
CONTENT_WIDTH_CM = 17.0

STATUS_TEXT = {
    'draft': '草稿',
    'submitted_auditor': '待初审',
    'rejected_auditor': '稽核驳回',
    'auditor_ok': '已初审',
    'submitted_finance': '待终审',
    'pending_dual_sign': '待双签',
    'rejected_finance': '财务驳回',
    'approved': '已批准',
    'archived': '已归档',
    'final_approved': '已批准',
    'submitted': '待初审',
}


def _fmt_money(v) -> str:
    """金额两位小数字符串"""
    return f'{Decimal(str(v or 0)):.2f}'


def _set_run_font(run, name=FONT_BODY, size=10.5, bold=False, color=None):
    """同时设置西文与中文字体（python-docx 需手动写 eastAsia）"""
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


_ALIGN = {
    'left': WD_ALIGN_PARAGRAPH.LEFT,
    'center': WD_ALIGN_PARAGRAPH.CENTER,
    'right': WD_ALIGN_PARAGRAPH.RIGHT,
}


def _cell_text(cell, text, *, font=FONT_BODY, size=10.5, bold=False,
               align='center', color=None):
    """向单元格写文本（覆盖默认空段落，水平+垂直居中）"""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    # 制式表格：去掉默认段后距/1.08 行距，行高才由 _set_row_height 控制
    _no_spacing(p)
    p.paragraph_format.line_spacing = 1.0
    p.alignment = _ALIGN[align]
    run = p.add_run('' if text is None else str(text))
    _set_run_font(run, font, size, bold, color)
    return p


def _set_table_borders(table, sz=6, color='000000'):
    """制式表格：四边 + 内部全部实线"""
    xml = (
        f'<w:tblBorders {nsdecls("w")}>'
        + ''.join(
            f'<w:{side} w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')
        )
        + '</w:tblBorders>'
    )
    table._tbl.tblPr.append(parse_xml(xml))


def _set_col_widths(table, widths_cm):
    """固定列宽（autofit 关闭 + 逐 cell 设宽，Word 才认）"""
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row in table.rows:
        for cell, w in zip(row.cells, widths_cm):
            cell.width = Cm(w)


def _set_row_height(row, cm):
    row.height = Cm(cm)
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _row_cant_split(row):
    """行内不跨页拆分"""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:cantSplit')) is None:
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))


def _repeat_header(row):
    """跨页时重复表头行"""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:tblHeader')) is None:
        trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))


def _row_keep_next(row):
    """表头行与下一行同页（单元格内所有段落设 keepNext + 段中不分页）"""
    for cell in row.cells:
        for p in cell.paragraphs:
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.keep_together = True


def _no_spacing(p):
    """去掉段前段后间距，制式表格更紧凑"""
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    return p


def _title(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _no_spacing(p)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    _set_run_font(run, FONT_TITLE, 18, bold=True)
    return p


def _section_heading(doc, text):
    """表格之间的小节标题（黑体左对齐，与后续表格同页）"""
    p = doc.add_paragraph()
    _no_spacing(p)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.keep_together = True
    run = p.add_run(text)
    _set_run_font(run, FONT_TITLE, 12, bold=True)
    return p


def _spacer(doc, pt=4):
    p = doc.add_paragraph()
    _no_spacing(p)
    p.paragraph_format.space_after = Pt(pt)
    return p


def _fmt_dt(dt) -> str:
    return dt.strftime('%Y-%m-%d %H:%M') if dt else '-'


def generate_bill_docx(bill, items, project, user, auditor, finance_auditor,
                       output_path: str, dual_signer=None) -> str:
    """
    生成报销单 Word（制式）

    :param bill: ExpenseBill
    :param items: list[ExpenseBillItem]
    :param project: ExpenseProject
    :param user: SysUser (报销人)
    :param auditor: SysUser (稽核员)
    :param finance_auditor: SysUser (财务)
    :param output_path: .docx 保存路径
    :param dual_signer: SysUser (第二签人，可选，D3 双签单据展示)
    :return: 实际保存路径
    """
    doc = Document()

    # ---- 页面：A4 纵向 ----
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    # 默认正文字体（style 级，保证空单元格也不落回 Calibri）
    style = doc.styles['Normal']
    style.font.name = FONT_BODY
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)
    # 默认模板 Normal 带 8pt 段后距 + 1.08 行距，制式表格需取消
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    now = datetime.now()
    days = (bill.travel_end_date - bill.travel_start_date).days + 1 \
        if bill.travel_start_date and bill.travel_end_date else '-'
    capital = bill.capital_amount or amount_to_capital(float(bill.total_amount or 0))

    # ---- 标题 ----
    _title(doc, '差旅费报销单')

    # ---- 编号行（无边框两列表格：左单号 / 右打印日期）----
    t = doc.add_table(rows=1, cols=2)
    _set_col_widths(t, [CONTENT_WIDTH_CM / 2, CONTENT_WIDTH_CM / 2])
    _set_row_height(t.rows[0], 0.5)
    _row_cant_split(t.rows[0])
    _cell_text(t.rows[0].cells[0], f'单据编号：{bill.bill_no}', align='left')
    _cell_text(t.rows[0].cells[1], f'单据状态：{STATUS_TEXT.get(bill.status, bill.status)}',
               align='right')

    _spacer(doc, 1)

    # ---- 主表：基本信息（6 列）----
    w6 = [2.6, 3.4, 2.6, 3.4, 2.6, 2.4]
    t = doc.add_table(rows=4, cols=6)
    _set_table_borders(t)
    _set_col_widths(t, w6)

    r = t.rows[0]
    _set_row_height(r, 0.75)
    _row_cant_split(r)
    _cell_text(r.cells[0], '报销人', bold=True)
    _cell_text(r.cells[1], user.real_name if user else '—（项目总账）')
    _cell_text(r.cells[2], '部门', bold=True)
    _cell_text(r.cells[3], (user.department or '—') if user else '—')
    _cell_text(r.cells[4], '人员类型', bold=True)
    _cell_text(r.cells[5], (user.staff_type or '—') if user else '—')

    label_value_rows = [
        ('所属项目', f'{project.project_code}　{project.project_name}' if project else '—'),
        ('出差目的地', bill.destination or '—'),
        ('出差日期', f'{bill.travel_start_date} 至 {bill.travel_end_date}（共 {days} 天）'
         if bill.travel_start_date and bill.travel_end_date else '—'),
    ]
    for i, (label, value) in enumerate(label_value_rows, start=1):
        r = t.rows[i]
        _set_row_height(r, 0.75)
        _row_cant_split(r)
        _cell_text(r.cells[0], label, bold=True)
        merged = r.cells[1].merge(r.cells[5])
        _cell_text(merged, value, align='left')

    # 代填标注（G2：稽核员代填时在主表下注明）
    if bill.is_agent_filled:
        _spacer(doc, 1)
        p = doc.add_paragraph()
        _no_spacing(p)
        run = p.add_run('※ 本单据为稽核员代填报销')
        _set_run_font(run, size=9, color='888888')

    # ---- 费用汇总表（6 列）----
    _section_heading(doc, '费用汇总')
    fee_w = [2.6, 2.88, 2.88, 2.88, 2.88, 2.88]
    t = doc.add_table(rows=2, cols=6)
    _set_table_borders(t)
    _set_col_widths(t, fee_w)

    header = t.rows[0]
    _set_row_height(header, 0.75)
    _row_cant_split(header)
    _row_keep_next(header)
    for cell, text in zip(header.cells,
                          ['费用项目', '交通费', '住宿费', '伙食补助费', '其他', '合计']):
        _cell_text(cell, text, bold=True)

    amount_row = t.rows[1]
    _set_row_height(amount_row, 0.75)
    _row_cant_split(amount_row)
    amounts = [
        '金额（元）',
        _fmt_money(bill.transport_fee),
        _fmt_money(bill.accommodation_fee),
        _fmt_money(bill.subsidy_fee),
        _fmt_money(bill.other_fee),
        _fmt_money(bill.total_amount),
    ]
    for i, (cell, text) in enumerate(zip(amount_row.cells, amounts)):
        _cell_text(cell, text, bold=(i in (0, 5)))

    # 大写金额行（独立 1×2 表格，靠下划线风格不必，制式用实线框）
    _spacer(doc, 1)
    t = doc.add_table(rows=1, cols=2)
    _set_table_borders(t)
    _set_col_widths(t, [10.0, 7.0])
    r = t.rows[0]
    _set_row_height(r, 0.75)
    _row_cant_split(r)
    _cell_text(r.cells[0], f'合计金额（大写）：{capital}', align='left', bold=True)
    _cell_text(r.cells[1], f'（小写）￥{_fmt_money(bill.total_amount)}', align='right')

    # ---- 费用明细（5 列，如有 items）----
    if items:
        _section_heading(doc, '费用明细')
        item_w = [1.4, 3.4, 3.0, 3.0, 6.2]
        t = doc.add_table(rows=1 + len(items), cols=5)
        _set_table_borders(t)
        _set_col_widths(t, item_w)

        head = t.rows[0]
        _set_row_height(head, 0.6)
        _row_cant_split(head)
        _repeat_header(head)
        _row_keep_next(head)
        for cell, text in zip(head.cells,
                              ['序号', '费用日期', '费用类型', '金额（元）', '说明']):
            _cell_text(cell, text, bold=True)

        for i, it in enumerate(items, start=1):
            r = t.rows[i]
            _set_row_height(r, 0.6)
            _row_cant_split(r)
            _cell_text(r.cells[0], i)
            _cell_text(r.cells[1], str(it.expense_date) if it.expense_date else '—')
            _cell_text(r.cells[2], it.item_type or '—')
            _cell_text(r.cells[3], _fmt_money(it.amount))
            _cell_text(r.cells[4], it.description or '—', align='left')

    # ---- 审批意见（4 列）----
    _section_heading(doc, '审批意见')
    flow_w = [2.6, 8.4, 3.0, 3.0]
    t = doc.add_table(rows=4, cols=4)
    _set_table_borders(t)
    _set_col_widths(t, flow_w)

    head = t.rows[0]
    _set_row_height(head, 0.6)
    _row_cant_split(head)
    _row_keep_next(head)
    for cell, text in zip(head.cells, ['审核环节', '审核意见', '签字人', '日期']):
        _cell_text(cell, text, bold=True)

    approvals = [
        ('稽核员初审', bill.auditor_comment, auditor.real_name if auditor else '',
         _fmt_dt(bill.auditor_audit_at)),
        ('财务终审', bill.finance_comment,
         finance_auditor.real_name if finance_auditor else '',
         _fmt_dt(bill.finance_audit_at)),
    ]
    if bill.finance_dual_signer_id:
        approvals.append(('第二签（双签）', bill.finance_dual_comment,
                          dual_signer.real_name if dual_signer else '',
                          _fmt_dt(bill.finance_dual_sign_at)))

    for i, (stage, comment, signer, at) in enumerate(approvals, start=1):
        r = t.rows[i]
        _set_row_height(r, 0.85)
        _row_cant_split(r)
        _cell_text(r.cells[0], stage, bold=True)
        _cell_text(r.cells[1], comment or '', align='left')
        _cell_text(r.cells[2], signer)
        _cell_text(r.cells[3], at)

    # ---- 签字栏（空白供手签）----
    _section_heading(doc, '签字栏')
    t = doc.add_table(rows=2, cols=4)
    _set_table_borders(t)
    _set_col_widths(t, [4.25, 4.25, 4.25, 4.25])

    head = t.rows[0]
    _set_row_height(head, 0.6)
    _row_cant_split(head)
    _row_keep_next(head)
    for cell, text in zip(head.cells, ['报销人签字', '稽核员签字', '财务负责人签字', '领款人签字']):
        _cell_text(cell, text, bold=True)

    blank = t.rows[1]
    _set_row_height(blank, 1.2)
    _row_cant_split(blank)
    for cell in blank.cells:
        _cell_text(cell, '')

    # ---- 页脚 ----
    _spacer(doc, 4)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _no_spacing(p)
    run = p.add_run(
        f'报销稽核系统 · 制式单据生成时间：{now.strftime("%Y-%m-%d %H:%M:%S")} · '
        f'单据编号：{bill.bill_no}'
    )
    _set_run_font(run, size=8, color='999999')

    # 文档属性
    doc.core_properties.title = f'差旅费报销单_{bill.bill_no}'
    doc.core_properties.author = '报销稽核系统'

    doc.save(output_path)
    return output_path
