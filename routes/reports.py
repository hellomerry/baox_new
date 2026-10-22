"""
报表路由（T5 补完 + Excel 导出）
"""
from datetime import datetime
from io import BytesIO
from flask import Blueprint, request, jsonify, send_file
from utils.decorators import login_required, get_current_user
from services import report_service
from services.report_service import (
    ReportService,
    PDFReportService,
    export_project_summary_xlsx,
    export_user_summary_xlsx,
    export_monthly_summary_xlsx,
    export_bill_detail_xlsx,
    export_comprehensive_report,
)

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/projects')
@login_required
def project_summary():
    """项目汇总"""
    start = request.args.get('start')
    end = request.args.get('end')
    sd = datetime.strptime(start, '%Y-%m-%d').date() if start else None
    ed = datetime.strptime(end, '%Y-%m-%d').date() if end else None

    data = ReportService.project_summary(sd, ed)
    return jsonify({'code': 0, 'data': data})


@reports_bp.route('/users')
@login_required
def user_summary():
    """报销人汇总"""
    start = request.args.get('start')
    end = request.args.get('end')
    sd = datetime.strptime(start, '%Y-%m-%d').date() if start else None
    ed = datetime.strptime(end, '%Y-%m-%d').date() if end else None

    data = ReportService.user_summary(sd, ed)
    return jsonify({'code': 0, 'data': data})


@reports_bp.route('/status')
@login_required
def status_summary():
    """状态分布"""
    return jsonify({'code': 0, 'data': ReportService.status_summary()})


@reports_bp.route('/monthly')
@login_required
def monthly_summary():
    """月度汇总"""
    year = int(request.args.get('year', datetime.now().year))
    return jsonify({'code': 0, 'data': ReportService.monthly_summary(year)})


# ============= Excel 导出路由 =============

def _parse_date_range():
    """解析时间范围参数"""
    start = request.args.get('start')
    end = request.args.get('end')
    sd = datetime.strptime(start, '%Y-%m-%d').date() if start else None
    ed = datetime.strptime(end, '%Y-%m-%d').date() if end else None
    return sd, ed


def _check_finance_only():
    """检查仅财务可导出"""
    user = get_current_user()
    if user.role != 'finance':
        return jsonify({'code': 1, 'message': '仅财务可导出'}), 403
    return None


@reports_bp.route('/export/projects.xlsx')
@login_required
def export_projects_xlsx():
    """导出项目汇总 Excel"""
    err = _check_finance_only()
    if err:
        return err
    sd, ed = _parse_date_range()
    data = export_project_summary_xlsx(sd, ed)
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'项目汇总_{datetime.now().strftime("%Y%m%d")}.xlsx',
    )


@reports_bp.route('/export/users.xlsx')
@login_required
def export_users_xlsx():
    """导出报销人汇总 Excel"""
    err = _check_finance_only()
    if err:
        return err
    sd, ed = _parse_date_range()
    data = export_user_summary_xlsx(sd, ed)
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'报销人汇总_{datetime.now().strftime("%Y%m%d")}.xlsx',
    )


@reports_bp.route('/export/monthly.xlsx')
@login_required
def export_monthly_xlsx():
    """导出月度汇总 Excel"""
    err = _check_finance_only()
    if err:
        return err
    year = int(request.args.get('year', datetime.now().year))
    data = export_monthly_summary_xlsx(year)
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{year}年月度汇总.xlsx',
    )


@reports_bp.route('/export/bills.xlsx')
@login_required
def export_bills_xlsx():
    """导出单据明细 Excel"""
    err = _check_finance_only()
    if err:
        return err
    sd, ed = _parse_date_range()
    status = request.args.get('status')
    project_id = request.args.get('project_id', type=int)
    user_id = request.args.get('user_id', type=int)

    data = export_bill_detail_xlsx(
        start_date=sd, end_date=ed, status=status,
        project_id=project_id, user_id=user_id,
    )
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'单据明细_{datetime.now().strftime("%Y%m%d")}.xlsx',
    )


@reports_bp.route('/export/comprehensive.xlsx')
@login_required
def export_comprehensive_xlsx():
    """导出综合报表 Excel（多 sheet）

    包含：项目汇总 + 报销人汇总 + 月度汇总 + 状态分布 + 单据明细
    """
    err = _check_finance_only()
    if err:
        return err
    sd, ed = _parse_date_range()
    year_param = request.args.get('year', type=int)
    year = year_param or datetime.now().year
    data = export_comprehensive_report(year=year, start_date=sd, end_date=ed)
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'综合报表_{datetime.now().strftime("%Y%m%d")}.xlsx',
    )


@reports_bp.route('/ping')
def ping():
    return jsonify({'msg': 'reports blueprint ready'})


# ============= PDF 导出（v2.5.0）=============

@reports_bp.route('/projects.pdf')
@login_required
def export_projects_pdf():
    """项目汇总 PDF"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not _check_finance_only():
        return jsonify({'code': 1, 'message': '仅财务可导出'}), 403
    pdf_bytes = PDFReportService.export_project_summary_pdf(start_date, end_date)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'项目汇总_{datetime.now().strftime("%Y%m%d")}.pdf',
    )


@reports_bp.route('/users.pdf')
@login_required
def export_users_pdf():
    """报销人汇总 PDF"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not _check_finance_only():
        return jsonify({'code': 1, 'message': '仅财务可导出'}), 403
    pdf_bytes = PDFReportService.export_user_summary_pdf(start_date, end_date)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'报销人汇总_{datetime.now().strftime("%Y%m%d")}.pdf',
    )


@reports_bp.route('/bills.pdf')
@login_required
def export_bills_pdf():
    """单据明细 PDF"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not _check_finance_only():
        return jsonify({'code': 1, 'message': '仅财务可导出'}), 403
    pdf_bytes = PDFReportService.export_bill_detail_pdf(start_date, end_date)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'单据明细_{datetime.now().strftime("%Y%m%d")}.pdf',
    )
