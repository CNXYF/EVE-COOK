"""
============================================================
模块：ui/tabs/monitor_tab.py —— 监控选项卡
------------------------------------------------------------
功能说明：
    主窗口的核心页面：
    - 上半部分：Local/Intel 监控状态与启停按钮
    - 下半部分：分级着色的日志显示区（LogViewer）

    UI 层职责约束：
    - 本文件只负责"画界面 + 发信号"
    - 点击按钮 -> 发射信号，由主窗口/服务层处理
    - 日志通过槽函数被动接收，不主动拉取
============================================================
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.log_viewer import LogViewer


class MonitorTab(QWidget):
    """
    监控选项卡页面。

    对外信号：
        sig_start_clicked(): 用户点击"启动监控"按钮
        sig_stop_clicked():  用户点击"停止监控"按钮
    """

    sig_start_clicked = pyqtSignal()
    sig_stop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        """构建监控页界面。"""
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """搭建界面控件与布局（纯界面代码，无业务逻辑）。"""
        # 根布局：垂直方向，从上到下排列
        root_layout = QVBoxLayout(self)

        # ---- 顶部：状态行 + 控制按钮 ----
        control_layout = QHBoxLayout()

        # 状态标签：显示当前监控运行状态
        self._status_label = QLabel("监控状态：未启动")
        self._status_label.setObjectName("statusLabel")
        control_layout.addWidget(self._status_label)

        # 当前星系标签：显示 Local 监控追踪到的当前星系
        self._system_label = QLabel("当前星系：未知")
        self._system_label.setObjectName("systemLabel")
        control_layout.addWidget(self._system_label)

        control_layout.addStretch()  # 弹性空白，把按钮推到右侧

        # 启动按钮：点击后发射 sig_start_clicked 信号
        self._start_button = QPushButton("启动监控")
        self._start_button.clicked.connect(self.sig_start_clicked.emit)
        control_layout.addWidget(self._start_button)

        # 停止按钮：初始禁用（未启动时不能停止）
        self._stop_button = QPushButton("停止监控")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self.sig_stop_clicked.emit)
        control_layout.addWidget(self._stop_button)

        root_layout.addLayout(control_layout)

        # ---- 下部：日志显示区 ----
        self.log_viewer = LogViewer(self)
        root_layout.addWidget(self.log_viewer)

    def set_current_system(self, system_name: str) -> None:
        """
        刷新"当前星系"显示（供主窗口在收到星系变化信号后调用）。

        参数：
            system_name: 新的星系名。
        """
        self._system_label.setText(f"当前星系：{system_name}")

    def set_running_state(self, running: bool) -> None:
        """
        根据监控运行状态刷新界面（供主窗口调用）。

        参数：
            running: True 表示监控运行中。
        """
        if running:
            self._status_label.setText("监控状态：运行中")
            self._start_button.setEnabled(False)  # 运行中不能再启动
            self._stop_button.setEnabled(True)
        else:
            self._status_label.setText("监控状态：未启动")
            self._start_button.setEnabled(True)
            self._stop_button.setEnabled(False)
