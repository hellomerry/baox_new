"""
启动期 stdout/stderr 兜底
- 解决 Windows 控制台 GBK 编码崩溃
- 解决 PyInstaller --windowed 下 sys.stdout = None 导致 print 崩
- 三个 launcher 启动时调用一次即可
"""
import sys
import io
import os


def setup_safe_stdout():
    """重新配置 stdout/stderr 为 UTF-8，并兜底 None（PyInstaller --windowed）"""
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            # PyInstaller --windowed 模式：stdout/stderr 是 None
            # 替换为 devnull，否则 print() 会崩
            setattr(sys, stream_name, open(os.devnull, 'w', encoding='utf-8'))
        else:
            try:
                # 重新配置为 UTF-8
                stream.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, io.UnsupportedOperation):
                # 老 Python / 包装过的流
                pass


if __name__ == '__main__':
    setup_safe_stdout()
    print('stdout OK ✓ 包含中文 ❌ 警告 ⚠️ 都能打')
