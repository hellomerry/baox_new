#!/usr/bin/env python3
"""
数据库迁移工具 — 入口
=====================
详见 migrations/runner.py

用法：
    python migrate.py status
    python migrate.py upgrade
    python migrate.py upgrade v1.2.0
    python migrate.py downgrade v1.0.0
    python migrate.py current
    python migrate.py history
"""
import sys
from pathlib import Path

# 把项目根加到 path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from migrations.runner import main

if __name__ == '__main__':
    main()
