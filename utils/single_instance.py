"""
进程级单实例锁（C1 决策）
跨平台支持：Windows (msvcrt) / Linux (fcntl) / macOS (fcntl)
"""
import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import msvcrt
else:
    import fcntl


_global_lock_fd = None


def _lock_file(fd) -> bool:
    """跨平台文件锁"""
    try:
        if IS_WINDOWS:
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, IOError, OSError):
        return False


def acquire_client_lock(client_dir: str) -> bool:
    """
    进程级单实例锁
    
    :param client_dir: 客户端工作目录
    :return: True=成功获取，可启动；False=已有实例在跑
    """
    global _global_lock_fd
    
    lock_path = Path(client_dir) / '.client.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        lock_fd = open(lock_path, 'w')
    except Exception as e:
        print(f'[ERROR] 无法创建锁文件 {lock_path}: {e}')
        return False
    
    if not _lock_file(lock_fd):
        lock_fd.close()
        return False
    
    # 写入 PID（便于排查）
    lock_fd.write(str(os.getpid()))
    lock_fd.flush()
    
    _global_lock_fd = lock_fd
    return True


def release_client_lock():
    """释放锁（进程退出时调用）"""
    global _global_lock_fd
    if _global_lock_fd is not None:
        try:
            _global_lock_fd.close()
        except Exception:
            pass
        _global_lock_fd = None
