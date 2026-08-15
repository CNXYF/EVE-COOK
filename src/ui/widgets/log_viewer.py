"""
============================================================
模块：ui/widgets/log_viewer.py —— 分级着色日志显示控件
------------------------------------------------------------
功能说明：
    用 QPlainTextEdit 显示程序日志，并按级别着色：
    - ERROR   红色
    - WARNING 黄色
    - INFO    青色
    后台服务通过信号把日志发过来，本控件只负责"显示"，
    不做任何业务处理（UI 层职责约束）。

    实现方式：
      用 HTML 富文本插入每一行（QPlainTextEdit 支持 appendHtml），
      不同级别包不同颜色的 <span>。
============================================================
"""
from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import pyqtSlot

from utils.constants import (
    COLOR_ERROR,
    COLOR_WARN,
    COLOR_INFO,
    COLOR_TEXT,
)


class LogViewer(QPlainTextEdit):
    """
    分级着色的日志显示控件。

    特性：
    - 只读（用户不能编辑日志）
    - 限制最大行数，防止长时间运行内存膨胀
    - 提供槽函数 append_log，直接连接服务的 sig_log 信号
    """

    # 日志区最多保留的行数（超过后自动删旧行）
    MAX_LINES = 1000

    # 日志级别 -> HTML 颜色 的映射表（避免写一堆 if/else）
    _LEVEL_COLORS = {
        "ERROR": COLOR_ERROR,
        "WARNING": COLOR_WARN,
        "INFO": COLOR_INFO,
    }

    def __init__(self, parent=None):
        """初始化日志控件的基础属性。"""
        super().__init__(parent)
        self.setReadOnly(True)               # 只读，禁止用户编辑
        self.setMaximumBlockCount(self.MAX_LINES)  # 自动裁剪超出的旧行

    @pyqtSlot(str, str)
    def append_log(self, level: str, message: str) -> None:
        """
        追加一条日志（槽函数，可直接 connect 服务的 sig_log）。

        参数：
            level: 日志级别（"INFO" / "WARNING" / "ERROR"）
            message: 日志内容
        """
        # 未知级别统一用普通文字颜色
        color = self._LEVEL_COLORS.get(level.upper(), COLOR_TEXT)

        # 转义 HTML 特殊字符，防止日志内容里的 < > & 破坏排版
        safe_message = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        # 组装一行带颜色的 HTML 并追加显示
        html = f'<span style="color:{color};">[{level}] {safe_message}</span>'
        self.appendHtml(html)
