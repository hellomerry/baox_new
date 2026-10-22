"""
同步服务（M3 + N5 决策）
- 离线模式：本地优先，不连中心
- 联网模式：与中心节点定期同步
- 心跳检测
- 上传 / 下载 .rbag
"""
import json
import socket
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional

from config import OFFLINE_MODE, CENTER_NODE_HOST, CENTER_NODE_PORT


def is_online() -> bool:
    """是否处于联网模式（环境变量控制）"""
    return not OFFLINE_MODE


def ping_center(timeout: float = 2.0) -> tuple:
    """
    心跳检测中心节点

    :return: (ok: bool, message: str)
    """
    if OFFLINE_MODE:
        return False, '当前为离线模式（OFFLINE_MODE=true）'

    try:
        url = f'https://{CENTER_NODE_HOST}:{CENTER_NODE_PORT}/api/center/ping'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f'中心节点在线（{r.status}）'
    except urllib.error.URLError as e:
        return False, f'中心节点不可达：{e.reason}'
    except Exception as e:
        return False, f'心跳失败：{e}'


def upload_to_center(package_path: str) -> tuple:
    """
    上传 .rbag 到中心节点

    :param package_path: 本地 .rbag 文件路径
    :return: (ok, message)
    """
    if OFFLINE_MODE:
        return False, '当前为离线模式，无法上传'

    if not is_online():
        return False, '当前为离线模式'

    try:
        url = f'https://{CENTER_NODE_HOST}:{CENTER_NODE_PORT}/api/center/packages/upload'
        with open(package_path, 'rb') as f:
            data = f.read()
        req = urllib.request.Request(
            url,
            data=data,
            method='POST',
            headers={'Content-Type': 'application/octet-stream'},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode('utf-8'))
            if result.get('code') == 0:
                return True, f'上传成功：{result.get("data", {}).get("package_id", "")}'
            return False, f'中心返回错误：{result.get("message", "未知")}'
    except Exception as e:
        return False, f'上传失败：{e}'


def download_from_center(package_id: str) -> tuple:
    """
    从中心节点下载 .rbag

    :param package_id: 包 ID
    :return: (ok, message, bytes)
    """
    if OFFLINE_MODE:
        return False, '当前为离线模式', None

    try:
        url = f'https://{CENTER_NODE_HOST}:{CENTER_NODE_PORT}/api/center/packages/{package_id}'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, '下载成功', r.read()
    except Exception as e:
        return False, f'下载失败：{e}', None


def get_sync_status() -> dict:
    """当前同步状态"""
    return {
        'offline_mode': OFFLINE_MODE,
        'center_node': f'{CENTER_NODE_HOST}:{CENTER_NODE_PORT}',
        'online': is_online(),
    }
