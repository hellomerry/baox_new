"""
报表服务（T4 + T5 补完）
- 项目汇总
- 报销人汇总
- 部门汇总
- Excel 导出（xlsxwriter）
"""
import io
import json
from datetime import datetime, date
from sqlalchemy import func

from models import db
from models.models import ExpenseBill, ExpenseBillItem, SysUser, ExpenseProject


class ReportService:

    @staticmethod
    def project_summary(start_date: date = None, end_date: date = None) -> list:
        """项目汇总：按项目分组，统计单据数、合计金额"""
        q = db.session.query(
            ExpenseProject.id,
            ExpenseProject.project_code,
            ExpenseProject.project_name,
            func.count(ExpenseBill.id).label('bill_count'),
            func.sum(ExpenseBill.total_amount).label('total_amount'),
        ).join(ExpenseBill, ExpenseBill.project_id == ExpenseProject.id)

        if start_date:
            q = q.filter(ExpenseBill.travel_start_date >= start_date)
        if end_date:
            q = q.filter(ExpenseBill.travel_end_date <= end_date)

        q = q.group_by(ExpenseProject.id, ExpenseProject.project_code, ExpenseProject.project_name)
        q = q.order_by(func.sum(ExpenseBill.total_amount).desc())

        rows = q.all()
        return [{
            'project_id': r[0],
            'project_code': r[1],
            'project_name': r[2],
            'bill_count': r[3],
            'total_amount': float(r[4] or 0),
        } for r in rows]

    @staticmethod
    def user_summary(start_date: date = None, end_date: date = None) -> list:
        """报销人汇总"""
        q = db.session.query(
            SysUser.id,
            SysUser.real_name,
            SysUser.department,
            func.count(ExpenseBill.id).label('bill_count'),
            func.sum(ExpenseBill.total_amount).label('total_amount'),
        ).join(ExpenseBill, ExpenseBill.user_id == SysUser.id)

        if start_date:
            q = q.filter(ExpenseBill.travel_start_date >= start_date)
        if end_date:
            q = q.filter(ExpenseBill.travel_end_date <= end_date)

        q = q.group_by(SysUser.id, SysUser.real_name, SysUser.department)
        q = q.order_by(func.sum(ExpenseBill.total_amount).desc())

        return [{
            'user_id': r[0],
            'real_name': r[1],
            'department': r[2] or '-',
            'bill_count': r[3],
            'total_amount': float(r[4] or 0),
        } for r in q.all()]

    @staticmethod
    def status_summary() -> dict:
        """状态分布"""
        q = db.session.query(
            ExpenseBill.status,
            func.count(ExpenseBill.id).label('count'),
            func.sum(ExpenseBill.total_amount).label('total'),
        ).group_by(ExpenseBill.status)

        result = {}
        for r in q.all():
            result[r[0]] = {
                'count': r[1],
                'total_amount': float(r[2] or 0),
            }
        return result

    @staticmethod
    def monthly_summary(year: int) -> list:
        """按月汇总"""
        q = db.session.query(
            func.strftime('%Y-%m', ExpenseBill.travel_start_date).label('month'),
            func.count(ExpenseBill.id),
            func.sum(ExpenseBill.total_amount),
        ).filter(
            func.strftime('%Y', ExpenseBill.travel_start_date) == str(year)
        ).group_by('month').order_by('month')

        return [{
            'month': r[0],
            'bill_count': r[1],
            'total_amount': float(r[2] or 0),
        } for r in q.all()]


# ============= Excel 导出 =============

# Excel 列头中文映射
HEADERS = {
    'project_summary': ['项目编号', '项目名称', '单据数', '合计金额（元）'],
    'user_summary': ['报销人', '部门', '单据数', '合计金额（元）'],
    'monthly_summary': ['月份', '单据数', '合计金额（元）'],
    'status_summary': ['状态', '单据数', '合计金额（元）'],
    'bill_detail': [
        '单据编号', '报销人', '部门', '项目', '出差起', '出差止',
        '目的地', '总金额', '大写金额', '状态', '创建时间'
    ],
}

STATUS_NAMES = {
    'draft': '草稿',
    'submitted': '已提交',
    'submitted_finance': '已提交财务',
    'auditor_approved': '稽核通过',
    'auditor_rejected': '稽核驳回',
    'final_approved': '终审通过',
    'final_rejected': '终审驳回',
    'archived': '已归档',
    'rejected': '已驳回',
    'red_rush': '已冲红',
}


def _apply_common_format(worksheet, workbook, headers, data_rows):
    """通用 Excel 格式：表头加粗 + 冻结 + 自动列宽"""
    wb = workbook
    # 表头加粗 + 底色
    header_fmt = wb.add_format({
        'bold': True,
        'bg_color': '#34495e',
        'font_color': '#ffffff',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
    })
    # 数据格式
    money_fmt = wb.add_format({
        'num_format': '#,##0.00',
        'align': 'right',
    })
    text_fmt = wb.add_format({
        'align': 'left',
        'valign': 'vcenter',
    })
    center_fmt = wb.add_format({
        'align': 'center',
        'valign': 'vcenter',
    })

    # 写表头
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_fmt)

    # 写数据
    for row_idx, row in enumerate(data_rows, 1):
        for col_idx, val in enumerate(row):
            if col_idx == 0 or (isinstance(val, str) and len(val) < 12):
                worksheet.write(row_idx, col_idx, val, center_fmt)
            elif isinstance(val, (int, float)):
                worksheet.write(row_idx, col_idx, val, money_fmt)
            else:
                worksheet.write(row_idx, col_idx, val, text_fmt)

    # 冻结首行
    worksheet.freeze_panes(1, 0)

    # 自动列宽
    for col, h in enumerate(headers):
        max_len = len(h)
        for row in data_rows:
            if col < len(row):
                v = str(row[col])
                # 中文字符按 2 算宽度
                w = sum(2 if ord(c) > 127 else 1 for c in v)
                max_len = max(max_len, w)
        worksheet.set_column(col, col, min(max_len + 2, 40))


def export_project_summary_xlsx(
    start_date: date = None,
    end_date: date = None,
    output: io.BytesIO = None,
) -> bytes:
    """导出项目汇总 Excel

    Args:
        start_date / end_date: 过滤范围
        output: 可选 BytesIO（默认新建）

    Returns:
        Excel bytes
    """
    import xlsxwriter
    if output is None:
        output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('项目汇总')

    data = ReportService.project_summary(start_date, end_date)
    rows = [
        [r['project_code'], r['project_name'], r['bill_count'], r['total_amount']]
        for r in data
    ]
    # 合计行
    total_amount = sum(r['total_amount'] for r in data)
    total_count = sum(r['bill_count'] for r in data)
    rows.append(['', '合计', total_count, total_amount])

    _apply_common_format(worksheet, workbook, HEADERS['project_summary'], rows)

    # 标题元数据
    title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
    period = f'{start_date or "*"} 至 {end_date or "*"}'
    worksheet.write(0, 0, f'报销稽核系统 - 项目汇总报表', title_fmt)
    # 重新写表头
    for col, h in enumerate(HEADERS['project_summary']):
        worksheet.write(1, col, h)

    # 重新写数据
    for row_idx, row in enumerate(rows, 2):
        for col_idx, val in enumerate(row):
            if col_idx == 3 and isinstance(val, (int, float)):
                worksheet.write(row_idx, col_idx, val, workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'bg_color': '#ecf0f1'}))
            elif col_idx == 1 and val == '合计':
                worksheet.write(row_idx, col_idx, val, workbook.add_format({'bold': True, 'bg_color': '#ecf0f1'}))
            else:
                worksheet.write(row_idx, col_idx, val)

    worksheet.freeze_panes(2, 0)
    worksheet.set_column(0, 0, 18)
    worksheet.set_column(1, 1, 30)
    worksheet.set_column(2, 2, 12)
    worksheet.set_column(3, 3, 18)

    workbook.close()
    return output.getvalue()


def export_user_summary_xlsx(
    start_date: date = None,
    end_date: date = None,
    output: io.BytesIO = None,
) -> bytes:
    """导出报销人汇总 Excel"""
    import xlsxwriter
    if output is None:
        output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('报销人汇总')

    data = ReportService.user_summary(start_date, end_date)
    rows = [
        [r['real_name'], r['department'], r['bill_count'], r['total_amount']]
        for r in data
    ]
    total_amount = sum(r['total_amount'] for r in data)
    total_count = sum(r['bill_count'] for r in data)
    rows.append(['', '合计', total_count, total_amount])

    _apply_common_format(worksheet, workbook, HEADERS['user_summary'], rows)
    workbook.close()
    return output.getvalue()


def export_monthly_summary_xlsx(year: int, output: io.BytesIO = None) -> bytes:
    """导出月度汇总 Excel"""
    import xlsxwriter
    if output is None:
        output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet(f'{year}年汇总')

    data = ReportService.monthly_summary(year)
    # 补全 12 个月（缺的填 0）
    month_map = {r['month']: r for r in data}
    rows = []
    for m in range(1, 13):
        key = f'{year}-{m:02d}'
        r = month_map.get(key, {'month': key, 'bill_count': 0, 'total_amount': 0.0})
        rows.append([r['month'], r['bill_count'], r['total_amount']])

    total_amount = sum(r[2] for r in rows)
    total_count = sum(r[1] for r in rows)
    rows.append(['合计', total_count, total_amount])

    _apply_common_format(worksheet, workbook, HEADERS['monthly_summary'], rows)
    workbook.close()
    return output.getvalue()


def export_bill_detail_xlsx(
    start_date: date = None,
    end_date: date = None,
    status: str = None,
    project_id: int = None,
    user_id: int = None,
    output: io.BytesIO = None,
) -> bytes:
    """导出单据明细 Excel（满足审计/合规的"原始单据清单"需求）"""
    import xlsxwriter
    if output is None:
        output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('单据明细')

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

    rows = []
    for b in bills:
        user = db.session.get(SysUser, b.user_id) if b.user_id else None
        project = projects.get(b.project_id)
        rows.append([
            b.bill_no or '-',
            user.real_name if user else '-',
            user.department if user else '-',
            f'{project.project_code} {project.project_name}' if project else '-',
            b.travel_start_date.isoformat() if b.travel_start_date else '-',
            b.travel_end_date.isoformat() if b.travel_end_date else '-',
            b.destination or '-',
            float(b.total_amount or 0),
            b.capital_amount or '-',
            STATUS_NAMES.get(b.status, b.status or '-'),
            b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '-',
        ])

    total_amount = sum(r[7] for r in rows)
    rows.append(['', '', '', '', '', '', '合计', total_amount, '', '', ''])

    _apply_common_format(worksheet, workbook, HEADERS['bill_detail'], rows)
    workbook.close()
    return output.getvalue()


def export_comprehensive_report(
    year: int = None,
    start_date: date = None,
    end_date: date = None,
    output: io.BytesIO = None,
) -> bytes:
    """综合报表（多 sheet）

    Sheets:
        1. 封面（元数据）
        2. 项目汇总
        3. 报销人汇总
        4. 月度汇总
        5. 状态分布
        6. 单据明细
    """
    import xlsxwriter
    if output is None:
        output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    # 封面
    cover = workbook.add_worksheet('封面')
    cover.set_column(0, 0, 20)
    cover.set_column(1, 1, 40)

    title_fmt = workbook.add_format({'bold': True, 'font_size': 18, 'align': 'center'})
    label_fmt = workbook.add_format({'bold': True, 'bg_color': '#ecf0f1'})
    value_fmt = workbook.add_format({'align': 'left'})

    cover.merge_range('A1:B1', '报销稽核系统 - 综合报表', title_fmt)
    cover.set_row(0, 30)

    period = f'{start_date or "*"} 至 {end_date or "*"}' if (start_date or end_date) else f'{year or "全部"} 年度'
    metadata = [
        ('报表周期', period),
        ('生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('生成人', '系统自动'),
        ('版本', 'v1.0'),
    ]
    for i, (label, value) in enumerate(metadata, 2):
        cover.write(i, 0, label, label_fmt)
        cover.write(i, 1, value, value_fmt)

    # 项目汇总
    ws_proj = workbook.add_worksheet('项目汇总')
    proj_data = ReportService.project_summary(start_date, end_date)
    proj_rows = [[r['project_code'], r['project_name'], r['bill_count'], r['total_amount']]
                 for r in proj_data]
    proj_rows.append(['', '合计', sum(r['bill_count'] for r in proj_data), sum(r['total_amount'] for r in proj_data)])
    _apply_common_format(ws_proj, workbook, HEADERS['project_summary'], proj_rows)

    # 报销人汇总
    ws_user = workbook.add_worksheet('报销人汇总')
    user_data = ReportService.user_summary(start_date, end_date)
    user_rows = [[r['real_name'], r['department'], r['bill_count'], r['total_amount']]
                 for r in user_data]
    user_rows.append(['', '合计', sum(r['bill_count'] for r in user_data), sum(r['total_amount'] for r in user_data)])
    _apply_common_format(ws_user, workbook, HEADERS['user_summary'], user_rows)

    # 月度汇总
    if year:
        ws_month = workbook.add_worksheet(f'{year}年月度')
        month_data = ReportService.monthly_summary(year)
        month_map = {r['month']: r for r in month_data}
        month_rows = []
        for m in range(1, 13):
            key = f'{year}-{m:02d}'
            r = month_map.get(key, {'month': key, 'bill_count': 0, 'total_amount': 0.0})
            month_rows.append([r['month'], r['bill_count'], r['total_amount']])
        month_rows.append(['合计', sum(r[1] for r in month_rows), sum(r[2] for r in month_rows)])
        _apply_common_format(ws_month, workbook, HEADERS['monthly_summary'], month_rows)

    # 状态分布
    ws_status = workbook.add_worksheet('状态分布')
    status_data = ReportService.status_summary()
    status_rows = [[STATUS_NAMES.get(k, k), v['count'], v['total_amount']]
                   for k, v in status_data.items()]
    if status_rows:
        status_rows.append(['合计', sum(r[1] for r in status_rows), sum(r[2] for r in status_rows)])
    _apply_common_format(ws_status, workbook, HEADERS['status_summary'], status_rows)

    # 单据明细
    ws_detail = workbook.add_worksheet('单据明细')
    q = db.session.query(ExpenseBill)
    if start_date:
        q = q.filter(ExpenseBill.travel_start_date >= start_date)
    if end_date:
        q = q.filter(ExpenseBill.travel_end_date <= end_date)
    bills = q.order_by(ExpenseBill.id.desc()).all()
    projects = {p.id: p for p in ExpenseProject.query.all()}
    detail_rows = []
    for b in bills:
        user = db.session.get(SysUser, b.user_id) if b.user_id else None
        project = projects.get(b.project_id)
        detail_rows.append([
            b.bill_no or '-',
            user.real_name if user else '-',
            user.department if user else '-',
            f'{project.project_code} {project.project_name}' if project else '-',
            b.travel_start_date.isoformat() if b.travel_start_date else '-',
            b.travel_end_date.isoformat() if b.travel_end_date else '-',
            b.destination or '-',
            float(b.total_amount or 0),
            b.capital_amount or '-',
            STATUS_NAMES.get(b.status, b.status or '-'),
            b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '-',
        ])
    if detail_rows:
        detail_rows.append(['', '', '', '', '', '', '合计', sum(r[7] for r in detail_rows), '', '', ''])
    _apply_common_format(ws_detail, workbook, HEADERS['bill_detail'], detail_rows)

    workbook.close()
    return output.getvalue()


# ============= PDF 报表导出（v2.5.0）=============

class PDFReportService:
    """PDF 报表生成

    使用 reportlab + 中文字体
    """
    @staticmethod
    def _setup_chinese_font():
        """注册中文字体（fallback）"""
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        # 尝试常见中文字体
        font_paths = [
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont('CJK', fp))
                    return 'CJK'
                except Exception:
                    pass
        return 'Helvetica'

    @staticmethod
    def export_project_summary_pdf(start_date=None, end_date=None) -> bytes:
        """项目汇总 PDF"""
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from io import BytesIO

        font = PDFReportService._setup_chinese_font()
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontName=font, fontSize=18)
        h_style = ParagraphStyle('H', parent=styles['Heading2'], fontName=font, fontSize=12)
        body_style = ParagraphStyle('Body', parent=styles['BodyText'], fontName=font, fontSize=10)

        elements = []
        elements.append(Paragraph('报销汇总报表 - 项目维度', title_style))
        elements.append(Spacer(1, 0.5 * cm))
        period = f'{start_date or "全部"} 至 {end_date or "全部"}'
        elements.append(Paragraph(f'统计周期：{period}', body_style))
        elements.append(Paragraph(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', body_style))
        elements.append(Spacer(1, 0.5 * cm))

        # 数据
        data = ReportService.project_summary(start_date, end_date)
        if not data:
            elements.append(Paragraph('无数据', body_style))
        else:
            # 表头
            table_data = [['项目编码', '项目名称', '单据数', '总金额（元）']]
            total_amount = 0
            total_count = 0
            for row in data:
                table_data.append([
                    str(row.get('project_code', '')),
                    str(row.get('project_name', '')),
                    str(row.get('bill_count', 0)),
                    f"{float(row.get('total_amount', 0) or 0):.2f}",
                ])
                total_amount += float(row.get('total_amount', 0) or 0)
                total_count += int(row.get('bill_count', 0) or 0)
            table_data.append(['合计', '', str(total_count), f'{total_amount:.2f}'])
            table = Table(table_data, colWidths=[4 * cm, 8 * cm, 3 * cm, 4 * cm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)

        doc.build(elements)
        return buf.getvalue()

    @staticmethod
    def export_user_summary_pdf(start_date=None, end_date=None) -> bytes:
        """报销人汇总 PDF"""
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from io import BytesIO

        font = PDFReportService._setup_chinese_font()
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontName=font, fontSize=18)
        body_style = ParagraphStyle('Body', parent=styles['BodyText'], fontName=font, fontSize=10)

        elements = []
        elements.append(Paragraph('报销汇总报表 - 报销人维度', title_style))
        elements.append(Spacer(1, 0.5 * cm))
        period = f'{start_date or "全部"} 至 {end_date or "全部"}'
        elements.append(Paragraph(f'统计周期：{period}', body_style))
        elements.append(Paragraph(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', body_style))
        elements.append(Spacer(1, 0.5 * cm))

        data = ReportService.user_summary(start_date, end_date)
        if not data:
            elements.append(Paragraph('无数据', body_style))
        else:
            table_data = [['姓名', '账号', '部门', '单据数', '总金额（元）']]
            total_amount = 0
            total_count = 0
            for row in data:
                table_data.append([
                    str(row.get('real_name', '')),
                    str(row.get('username', '')),
                    str(row.get('department', '')),
                    str(row.get('bill_count', 0)),
                    f"{float(row.get('total_amount', 0) or 0):.2f}",
                ])
                total_amount += float(row.get('total_amount', 0) or 0)
                total_count += int(row.get('bill_count', 0) or 0)
            table_data.append(['合计', '', '', str(total_count), f'{total_amount:.2f}'])
            table = Table(table_data, colWidths=[4 * cm, 4 * cm, 6 * cm, 3 * cm, 4 * cm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
            ]))
            elements.append(table)

        doc.build(elements)
        return buf.getvalue()

    @staticmethod
    def export_bill_detail_pdf(start_date=None, end_date=None) -> bytes:
        """单据明细 PDF"""
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from io import BytesIO

        font = PDFReportService._setup_chinese_font()
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontName=font, fontSize=18)
        body_style = ParagraphStyle('Body', parent=styles['BodyText'], fontName=font, fontSize=10)

        elements = []
        elements.append(Paragraph('报销单明细报表', title_style))
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph(f'统计周期：{start_date or "全部"} 至 {end_date or "全部"}', body_style))
        elements.append(Paragraph(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', body_style))
        elements.append(Spacer(1, 0.5 * cm))

        # 单据明细（限制 200 条）
        q = db.session.query(ExpenseBill).filter(ExpenseBill.status.in_(['approved', 'archived']))
        if start_date:
            q = q.filter(ExpenseBill.created_at >= start_date)
        if end_date:
            q = q.filter(ExpenseBill.created_at <= end_date)
        bills = q.order_by(ExpenseBill.created_at.desc()).limit(200).all()
        if not bills:
            elements.append(Paragraph('无数据', body_style))
        else:
            table_data = [['单号', '报销人', '项目', '日期', '金额', '状态']]
            total = 0
            for b in bills:
                user = SysUser.query.get(b.user_id) if b.user_id else None
                proj = ExpenseProject.query.get(b.project_id) if b.project_id else None
                table_data.append([
                    str(b.bill_no or ''),
                    user.real_name if user else '-',
                    proj.project_name if proj else '-',
                    b.travel_start_date or '-',
                    f"{float(b.total_amount or 0):.2f}",
                    b.status,
                ])
                total += float(b.total_amount or 0)
            table_data.append(['合计', '', '', '', f'{total:.2f}', f'{len(bills)} 单'])
            table = Table(table_data, colWidths=[4 * cm, 3 * cm, 6 * cm, 3 * cm, 4 * cm, 3 * cm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
            ]))
            elements.append(table)

        doc.build(elements)
        return buf.getvalue()
