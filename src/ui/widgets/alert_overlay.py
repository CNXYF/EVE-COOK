"""
============================================================
模块：ui/widgets/alert_overlay.py —— 悬浮预警窗
------------------------------------------------------------
功能说明：
    当 Intel 监控发现危险信息时弹出的悬浮提示窗。
    强制约束：必须"置顶 + 半透明"。

    实现要点：
    - Qt.WindowStaysOnTopHint：窗口永远置顶
    - Qt.FramelessWindowHint：无边框（更像"悬浮提示"）
    - setWindowOpacity：整体半透明
    - Qt.Tool：不在任务栏显示图标
============================================================
"""
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from utils.constants import COLOR_PRIMARY


class AlertOverlay(QWidget):
    """
    置顶半透明悬浮预警窗。

    使用方式：
        overlay = AlertOverlay()
        intel_service.sig_alert.connect(overlay.show_alert)
    """

    # 预警窗自动隐藏的等待时间（毫秒）
    AUTO_HIDE_MS = 8000

    def __init__(self, parent=None):
        """创建无边框、置顶、半透明的预警窗口。"""
        super().__init__(parent)

        # ---- 窗口标志位 ----
        # FramelessWindowHint: 无边框
        # WindowStaysOnTopHint: 置顶（强制约束）
        # Tool: 不在任务栏出现
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        # 半透明（强制约束）：0.85 既能看清内容又不完全遮挡游戏
        self.setWindowOpacity(0.85)
        self.setFixedSize(420, 90)  # 固定尺寸，避免内容撑变形

        # ---- 内部布局：一个标签显示预警文字 ----
        self._label = QLabel("预警信息")
        self._label.setStyleSheet(
            f"color: {COLOR_PRIMARY}; font-size: 15px; font-weight: bold;"
        )
        self._label.setWordWrap(True)  # 文字过长时自动换行

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

        # 深色半透明背景样式
        self.setStyleSheet(
            "background-color: rgba(10, 14, 20, 230);"
            f"border: 2px solid {COLOR_PRIMARY};"
            "border-radius: 8px;"
        )

        # ---- 自动隐藏定时器：预警展示几秒后自动消失 ----
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)  # 单次触发
        self._hide_timer.timeout.connect(self.hide)

    @pyqtSlot(str)
    def show_alert(self, message: str) -> None:
        """
        显示一条预警（槽函数，连接 IntelMonitorService.sig_alert）。

        参数：
            message: 触发预警的原始内容。
        """
        self._label.setText(message)
        self.show()
        self.raise_()  # 把窗口提到最前
        # 重启自动隐藏计时（连续预警时刷新展示时间）
        self._hide_timer.start(self.AUTO_HIDE_MS)
