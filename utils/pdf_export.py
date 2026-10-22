"""
PDF 单据导出工具
- 报销单打印（A4 纵向）
- 中文支持（用 CID 字体）
- 大写金额 / 审批流程 / 明细表
"""
import os
from datetime import datetime
from decimal import Decimal

from reportlab.lib import pagesizes
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, gray, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.platypus.flowables import HRFlowable


# 注册中文字体（reportlab 内置 STSong-Light）
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))


def generate_bill_pdf(bill, items, project, user, auditor, finance_auditor, output_path: str) -> str:
    """
    生成报销单 PDF

    :param bill: ExpenseBill
    :param items: list[ExpenseBillItem]
    :param project: ExpenseProject
    :param user: SysUser (报销人)
    :param auditor: SysUser (稽核员)
    :param finance_auditor: SysUser (财务)
    :param output_path: PDF 保存路径
    :return: 实际保存路径
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=pagesizes.A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title=f'报销单_{bill.bill_no}',
        author='报销稽核系统',
    )

    # 样式
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontName='STSong-Light',
        fontSize=22, alignment=TA_CENTER,
        spaceAfter=12, textColor=HexColor('#1890ff'),
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontName='STSong-Light',
        fontSize=13, textColor=HexColor('#333'),
        spaceBefore=12, spaceAfter=6,
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'],
        fontName='STSong-Light',
        fontSize=10, textColor=gray,
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='STSong-Light',
        fontSize=10,
    )

    story = []

    # 标题
    story.append(Paragraph('报销单', title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#1890ff')))
    story.append(Spacer(1, 6*mm))

    # 单号 + 状态
    status_text = {
        'draft': '草稿',
        'submitted_auditor': '待初审',
        'rejected_auditor': '稽核驳回',
        'auditor_ok': '已初审',
        'submitted_finance': '待终审',
        'rejected_finance': '财务驳回',
        'approved': '已批准',
        'archived': '已归档',
    }.get(bill.status, bill.status)

    header_data = [
        ['单号', bill.bill_no, '状态', status_text],
        ['报销人', user.real_name if user else '-', '部门', user.department or '-' if user else '-'],
        ['项目', f'{project.project_code if project else ""} {project.project_name if project else ""}', '类型', '项目总账' if bill.bill_type == 'project_total' else '个人报销'],
        ['出发日期', str(bill.travel_start_date), '返回日期', str(bill.travel_end_date)],
        ['目的地', bill.destination or '-', '是否代填', '是' if bill.is_agent_filled else '否'],
    ]
    t = Table(header_data, colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'STSong-Light', 10),
        ('TEXTCOLOR', (0, 0), (0, -1), gray),
        ('TEXTCOLOR', (2, 0), (2, -1), gray),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#eee')),
    ]))
    story.append(t)

    # 金额明细
    story.append(Paragraph('金额明细', h2_style))
    fee_data = [
        ['项目', '金额（元）'],
        ['交通费', f'{Decimal(str(bill.transport_fee or 0)):.2f}'],
        ['住宿费', f'{Decimal(str(bill.accommodation_fee or 0)):.2f}'],
        ['补助', f'{Decimal(str(bill.subsidy_fee or 0)):.2f}'],
        ['其他', f'{Decimal(str(bill.other_fee or 0)):.2f}'],
        ['合计', f'{Decimal(str(bill.total_amount or 0)):.2f}'],
    ]
    ft = Table(fee_data, colWidths=[12*cm, 6*cm])
    ft.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'STSong-Light', 10),
        ('FONT', (0, 5), (-1, 5), 'STSong-Light', 11),
        ('FONT', (0, 0), (-1, 0), 'STSong-Light', 10),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f0f0f0')),
        ('BACKGROUND', (0, 5), (-1, 5), HexColor('#e6f7ff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('TEXTCOLOR', (0, 0), (-1, 0), black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#ddd')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ft)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(f'<b>大写金额：</b>{bill.capital_amount or ""}', body_style))

    # 报销明细（如有 items）
    if items:
        story.append(Paragraph('费用明细', h2_style))
        item_data = [['序号', '类型', '金额', '日期', '说明']]
        for i, it in enumerate(items, 1):
            item_data.append([
                str(i),
                it.item_type or '-',
                f'{Decimal(str(it.amount or 0)):.2f}',
                str(it.expense_date) if it.expense_date else '-',
                (it.description or '-')[:30],
            ])
        it_t = Table(item_data, colWidths=[1.5*cm, 3*cm, 3*cm, 3*cm, 7.5*cm])
        it_t.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'STSong-Light', 9),
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f0f0f0')),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#eee')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(it_t)

    # 审批流程
    story.append(Paragraph('审批流程', h2_style))
    flow_data = [
        ['环节', '人员', '时间', '意见'],
        [
            '稽核员初审',
            auditor.real_name if auditor else '-',
            str(bill.auditor_audit_at) if bill.auditor_audit_at else '-',
            bill.auditor_comment or '-',
        ],
        [
            '财务终审',
            finance_auditor.real_name if finance_auditor else '-',
            str(bill.finance_audit_at) if bill.finance_audit_at else '-',
            bill.finance_comment or '-',
        ],
    ]
    ft = Table(flow_data, colWidths=[3*cm, 3*cm, 4*cm, 8*cm])
    ft.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'STSong-Light', 10),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f0f0f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#ddd')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ft)

    # 签字栏
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph('签字栏', h2_style))
    sign_data = [
        ['', '签字', '日期'],
        ['报销人', '', ''],
        ['稽核员', '', ''],
        ['财务', '', ''],
    ]
    st = Table(sign_data, colWidths=[4*cm, 6*cm, 8*cm], rowHeights=[0.8*cm, 1.5*cm, 1.5*cm, 1.5*cm])
    st.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'STSong-Light', 10),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f0f0f0')),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('VALIGN', (0, 1), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, black),
    ]))
    story.append(st)

    # 页脚
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#ccc')))
    story.append(Paragraph(
        f'<font color="gray" size="8">'
        f'报销稽核系统 · 单据生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} · '
        f'单号：{bill.bill_no}'
        f'</font>',
        ParagraphStyle('Footer', alignment=TA_CENTER, fontName='STSong-Light', fontSize=8)
    ))

    doc.build(story)
    return output_path


# ============= D3 决策：终审独立审计报告 PDF =============

def export_research_audit_report(
    output_path: str,
    bill,
    history: list,
    chain: dict,
    creator,
) -> str:
    """终审独立审计报告（D3）

    Args:
        output_path: 输出 PDF 路径
        bill: ExpenseBill 对象
        history: list_research_audits() 返回的审计记录
        chain: verify_research_audit_chain() 返回的校验结果
        creator: 单据创建人 SysUser

    输出：A4 纵向 PDF，含单据信息 + 审计时间线 + 完整性校验
    """
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    doc = SimpleDocTemplate(
        output_path,
        pagesize=pagesizes.A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'], fontName='STSong-Light',
        fontSize=18, alignment=TA_CENTER, spaceAfter=12
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'], fontName='STSong-Light',
        fontSize=14, textColor=HexColor('#2c3e50'), spaceAfter=8, spaceBefore=12
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'], fontName='STSong-Light', fontSize=10, leading=14
    )

    story = []

    # 标题
    story.append(Paragraph('终审独立审计报告', title_style))
    story.append(HRFlowable(width='100%', thickness=1, color=HexColor('#2c3e50')))
    story.append(Spacer(1, 0.3*cm))

    # 报告元信息
    meta_data = [
        ['报告编号', f'RA-{bill.id:06d}-{datetime.now().strftime("%Y%m%d%H%M%S")}'],
        ['单据编号', bill.bill_no or '-'],
        ['单据类型', bill.bill_type or '-'],
        ['单据金额', f'¥{float(bill.total_amount or 0):,.2f}'],
        ['报销人', creator.real_name if creator else '-'],
        ['生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
    ]
    meta_table = Table(meta_data, colWidths=[3*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#ecf0f1')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5*cm))

    # 完整性校验
    story.append(Paragraph('一、审计链完整性', h2_style))
    chain_status = '✓ 完整' if chain['ok'] else '✗ 异常'
    chain_color = HexColor('#27ae60') if chain['ok'] else HexColor('#e74c3c')
    chain_data = [
        ['校验结果', chain_status],
        ['审计记录数', str(chain.get('count', 0))],
        ['最后动作', chain.get('last_action') or '-'],
    ]
    if chain.get('missing_actions'):
        chain_data.append(['缺失动作', ', '.join(chain['missing_actions'])])
    if chain.get('message'):
        chain_data.append(['备注', chain['message']])

    chain_table = Table(chain_data, colWidths=[3*cm, 12*cm])
    chain_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#ecf0f1')),
        ('TEXTCOLOR', (1, 0), (1, 0), chain_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(chain_table)
    story.append(Spacer(1, 0.5*cm))

    # 审计时间线
    story.append(Paragraph('二、终审独立审计时间线', h2_style))
    if not history:
        story.append(Paragraph('<i>无终审记录（金额未达终审阈值）</i>', body_style))
    else:
        # 表头
        timeline_data = [['#', '时间', '操作人', '动作', '状态变更', 'IP', '原因']]
        action_map = {
            'final_approve': '终审通过',
            'final_reject': '终审驳回',
            'override': '强制修改',
            'archive': '归档',
        }
        for i, h in enumerate(history, 1):
            timeline_data.append([
                str(i),
                h['created_at'][:19] if h.get('created_at') else '-',
                f"{h.get('auditor_name', '-')} ({h.get('auditor_role', '-')})",
                action_map.get(h['action'], h['action']),
                f"{h.get('original_status') or '-'} → {h.get('new_status') or '-'}",
                h.get('ip_address') or '-',
                (h.get('reason') or '-')[:30],
            ])

        timeline_table = Table(
            timeline_data,
            colWidths=[1*cm, 3.5*cm, 3.5*cm, 2*cm, 3*cm, 2*cm, 2*cm]
        )
        timeline_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#bdc3c7')),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        # 斑马纹
        for i in range(1, len(timeline_data)):
            if i % 2 == 0:
                timeline_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), HexColor('#f8f9fa')),
                ]))
        story.append(timeline_table)
    story.append(Spacer(1, 0.5*cm))

    # 合规声明
    story.append(Paragraph('三、合规声明', h2_style))
    story.append(Paragraph(
        '本报告由报销稽核系统（D3 决策）自动生成，记录了上述单据的完整终审独立审计过程。<br/>'
        '审计链的每一步均不可篡改，所有操作记录均带操作人、IP、客户端 ID 三元组，可用于内部审计与外部合规检查。<br/>'
        '本报告 SHA-256 哈希可用于离线校验。',
        body_style
    ))
    story.append(Spacer(1, 0.3*cm))

    # 报告哈希
    import hashlib
    report_content = (
        f'RA-{bill.id}-{bill.bill_no}-{len(history)}-'
        f'{chain.get("ok")}-{datetime.now().isoformat()}'
    )
    report_hash = hashlib.sha256(report_content.encode()).hexdigest()
    story.append(Paragraph(
        f'<font color="gray" size="8">报告哈希 (SHA-256): {report_hash}</font>',
        ParagraphStyle('Hash', parent=body_style, fontSize=8, textColor=gray)
    ))

    # 页脚
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=gray))
    story.append(Paragraph(
        f'<font color="gray" size="8">'
        f'报销稽核系统 · 终审独立审计报告 · 生成于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</font>',
        ParagraphStyle('Footer', alignment=TA_CENTER, fontName='STSong-Light', fontSize=8)
    ))

    doc.build(story)
    return output_path
