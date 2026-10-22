"""客户端打包 service（v2.10.0）

把裁剪后的 db + 模板 → 绿色 zip 包
"""
import logging
import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict

from config import Config
from services.client_distribution_service import (
    export_auditor_db, export_reimburser_db, export_finance_db,
)

log = logging.getLogger(__name__)


def build_auditor_client_package(
    operator_id: int,
    auditor_id: int,
    finance_id: int = None,
) -> Dict:
    """生成稽核员绿色客户端包

    流程：
    1. 在 dist_clients/auditor_<id>_<ts>/ 准备目录
    2. 复制模板（python/ + workspace/ + 启动.bat）
    3. 裁剪数据生成 target db
    4. 替换 workspace/reimbursement-app/reimbursement.db
    5. 打成 zip
    6. 返回 zip 路径 + 文件大小
    """
    return _build_package(
        operator_id=operator_id,
        target_user_id=auditor_id,
        target_role='auditor',
        include_finance_id=finance_id,
    )


def build_reimburser_client_package(
    operator_id: int,
    reimburser_id: int,
    auditor_id: int = None,
) -> Dict:
    """生成报销员绿色客户端包"""
    return _build_package(
        operator_id=operator_id,
        target_user_id=reimburser_id,
        target_role='reimburser',
        include_auditor_id=auditor_id,
    )


def build_finance_client_package(operator_id: int, finance_id: int) -> Dict:
    """生成财务绿色客户端包（含全部数据）"""
    return _build_package(
        operator_id=operator_id,
        target_user_id=finance_id,
        target_role='finance',
    )


def _build_package(
    operator_id: int,
    target_user_id: int,
    target_role: str,
    include_finance_id: int = None,
    include_auditor_id: int = None,
) -> Dict:
    template_dir = Path(Config.CLIENT_TEMPLATE_DIR)
    if not template_dir.exists():
        return {'success': False, 'message': f'模板不存在: {template_dir}（请确认 templates/green_client_template/ 已部署）'}

    required = ['python/python.exe', 'python/python311._pth', 'workspace/reimbursement-app']
    for p in required:
        if not (template_dir / p).exists():
            return {'success': False, 'message': f'模板不完整，缺少: {p}'}

    # 1. 准备输出目录
    dist_root = Path(Config.CLIENT_DIST_DIR)
    dist_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    target_dir = dist_root / f'{target_role}_{target_user_id}_{ts}'
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    # 2. 复制模板（python 目录是大文件，做硬链接或直接复制）
    log.info(f'复制模板: {template_dir} → {target_dir}')
    shutil.copytree(template_dir / 'python', target_dir / 'python', symlinks=False, dirs_exist_ok=True)
    shutil.copytree(template_dir / 'workspace', target_dir / 'workspace', symlinks=False, dirs_exist_ok=True)

    # 3. 复制启动脚本
    for bat in ['启动财务版.bat', '启动稽核员版.bat', '启动报销人版.bat', '使用说明.txt']:
        src = template_dir / bat
        if src.exists():
            shutil.copy2(src, target_dir / bat)

    # 4. 裁剪数据生成目标 db
    target_db = target_dir / 'workspace' / 'reimbursement-app' / 'reimbursement.db'
    if target_role == 'auditor':
        result = export_auditor_db(target_user_id, str(target_db), include_finance_id=include_finance_id)
    elif target_role == 'reimburser':
        result = export_reimburser_db(target_user_id, str(target_db), include_auditor_id=include_auditor_id)
    elif target_role == 'finance':
        result = export_finance_db(target_user_id, str(target_db))
    else:
        return {'success': False, 'message': f'不支持的角色: {target_role}'}

    if not result.get('success'):
        shutil.rmtree(target_dir, ignore_errors=True)
        return result

    # 5. 打成 zip
    role_name_zh = {'finance': '财务版', 'auditor': '稽核员版', 'reimburser': '报销人版'}[target_role]
    zip_name = f'报销稽核系统_{role_name_zh}_用户{target_user_id}_{ts}.zip'
    zip_path = dist_root / zip_name
    log.info(f'打包: {target_dir} → {zip_path}')

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                fp = Path(root) / f
                arc = fp.relative_to(target_dir.parent)
                zf.write(fp, arc)

    # 6. 清理临时目录
    shutil.rmtree(target_dir, ignore_errors=True)

    zip_size = os.path.getsize(zip_path)
    return {
        'success': True,
        'zip_path': str(zip_path),
        'zip_name': zip_name,
        'zip_size': zip_size,
        'data_scope': result,
    }
