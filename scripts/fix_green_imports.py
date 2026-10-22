"""
绿色版 sys.path 修复脚本
用于 launcher_*.py 和 app.py，让嵌入 Python 能找到同目录模块

背景：python311._pth 的 "." 指的是 python/ 目录，不是当前工作目录
所以从 bat 调 python 时 cwd 不会被自动加进 sys.path

执行：在打包脚本里调用此脚本，给 launcher*.py 和 app.py 加 sys.path 修复
"""
import re
import sys
from pathlib import Path


def fix_launcher(path: Path):
    """给 launcher_*.py 加 sys.path 修复"""
    content = path.read_text(encoding='utf-8')
    # 如果已经修复过则跳过
    if '绿色版修复' in content:
        return False
    # 在 import webview 之前插入 sys.path 修复
    fix_block = (
        'import sys\nimport os\nfrom pathlib import Path\n'
        '# 绿色版修复：把脚本所在目录加进 sys.path\n'
        'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
        'sys.path.insert(0, os.getcwd())\n'
    )
    # 找所有 import 行
    lines = content.split('\n')
    out = []
    inserted = False
    for line in lines:
        if not inserted and line.startswith('import ') and 'webview' in line:
            out.append(fix_block)
            inserted = True
        out.append(line)
    if not inserted:
        # 兼容其他格式
        old = 'import sys\nimport time\nimport os\nfrom pathlib import Path'
        new = fix_block + 'import time'
        if old in content:
            content = content.replace(old, new)
            path.write_text(content, encoding='utf-8')
            return True
        return False
    content = '\n'.join(out)
    path.write_text(content, encoding='utf-8')
    return True


def fix_app(path: Path):
    """给 app.py 加 sys.path 修复"""
    content = path.read_text(encoding='utf-8')
    if '绿色版修复' in content:
        return False
    old = '"""\n通用 Flask 应用工厂（T1）\nT2-T5 的蓝图在这里注册\n"""\nimport os'
    new = (
        '"""\n通用 Flask 应用工厂（T1）\nT2-T5 的蓝图在这里注册\n"""\nimport os\nimport sys\n'
        '# 绿色版修复：把脚本所在目录加进 sys.path\n'
        '_app_dir = os.path.dirname(os.path.abspath(__file__))\n'
        'if _app_dir not in sys.path:\n'
        '    sys.path.insert(0, _app_dir)\n'
        'if os.getcwd() not in sys.path:\n'
        '    sys.path.insert(0, os.getcwd())'
    )
    if old in content:
        content = content.replace(old, new)
        path.write_text(content, encoding='utf-8')
        return True
    return False


if __name__ == '__main__':
    base = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    fixed = 0
    for launcher in ['launcher_finance.py', 'launcher_auditor.py', 'launcher_reimburser.py']:
        p = base / launcher
        if p.exists() and fix_launcher(p):
            print(f'[OK] {launcher}')
            fixed += 1
        elif p.exists():
            print(f'[skip] {launcher} (already fixed)')
    if fix_app(base / 'app.py'):
        print('[OK] app.py')
        fixed += 1
    else:
        print('[skip] app.py (already fixed)')
    print(f'Fixed {fixed} file(s)')
