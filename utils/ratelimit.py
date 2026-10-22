"""
轻量限速（O2 决策）
- 全局默认：60 次/分钟/IP
- 登录端点：10 次/分钟/IP
- 内存存储（开发期）
- 跨重启不持久（生产应换 Redis）
"""
import time
from collections import defaultdict
from threading import Lock
from functools import wraps
from flask import request, jsonify


class RateLimiter:
    """基于内存的滑动窗口限速器"""

    def __init__(self):
        self._store = defaultdict(list)
        self._lock = Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple:
        """
        记录一次命中

        :return: (allowed: bool, remaining: int, retry_after: int)
        """
        now = time.time()
        with self._lock:
            history = [t for t in self._store[key] if t > now - window_seconds]
            if len(history) >= limit:
                retry_after = int(history[0] + window_seconds - now) + 1
                self._store[key] = history
                return False, 0, retry_after
            history.append(now)
            self._store[key] = history
            return True, limit - len(history), 0

    def clear(self, key: str = None):
        with self._lock:
            if key:
                self._store.pop(key, None)
            else:
                self._store.clear()


_limiter = RateLimiter()


def get_client_ip() -> str:
    """取客户端 IP（O12：支持 X-Forwarded-For）"""
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def rate_limit(limit: int = 60, window_seconds: int = 60, key_prefix: str = 'global'):
    """
    限速装饰器

    :param limit: 窗口内最大次数
    :param window_seconds: 窗口大小（秒）
    :param key_prefix: 计数 key 前缀
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = get_client_ip()
            key = f'{key_prefix}:{ip}'
            allowed, remaining, retry_after = _limiter.hit(key, limit, window_seconds)
            if not allowed:
                resp = jsonify({
                    'code': 429,
                    'message': f'请求过于频繁，请在 {retry_after} 秒后重试',
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_after)
                resp.headers['X-RateLimit-Limit'] = str(limit)
                resp.headers['X-RateLimit-Remaining'] = '0'
                return resp
            resp = f(*args, **kwargs)
            # 给响应加上限速头
            try:
                if hasattr(resp, 'headers'):
                    resp.headers['X-RateLimit-Limit'] = str(limit)
                    resp.headers['X-RateLimit-Remaining'] = str(remaining)
            except Exception:
                pass
            return resp
        return wrapper
    return decorator


# O2 决策预定义限速
limit_global = rate_limit(limit=60, window_seconds=60, key_prefix='global')      # 60/分钟
limit_login = rate_limit(limit=10, window_seconds=60, key_prefix='login')        # 10/分钟
