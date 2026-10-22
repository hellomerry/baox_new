"""
启动诊断工具
"""
from .desktop_env import (
    preflight_check,
    check_desktop_env,
    show_diagnostic,
    show_error_popup,
)


__all__ = ['preflight_check', 'check_desktop_env', 'show_diagnostic', 'show_error_popup']
