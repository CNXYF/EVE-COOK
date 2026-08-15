"""
============================================================
模块：ui/main_window.py —— 主窗口
------------------------------------------------------------
功能说明：
    程序主窗口，承载：
    - 选项卡容器（监控页 / 跳数计算页）
    - 悬浮预警窗（AlertOverlay）
    - 服务信号的"接线"：把各服务的信号连到对应 UI 槽函数

    UI 层职责约束：
    - 本文件不写业务逻辑，只做"信号接线"和界面更新
    - 所有后台数据都通过信号送达，不主动访问服务内部
============================================================
"""
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QTabWidget

from services.service_manager import ServiceManager
from ui.tabs.jump_tab import JumpTab
from ui.tabs.monitor_tab import MonitorTab
from ui.widgets.alert_overlay import AlertOverlay
from utils.constants import APP_NAME, APP_VERSION
from utils.logger import get_logger

logger = get_logger("main_window")


class MainWindow(QMainWindow):
    """
    主窗口：组装选项卡、接线服务信号。
    """

    def __init__(self, service_manager: ServiceManager):
        """
        参数：
            service_manager: 服务管理器（由 main.py 创建并注入）。
                             主窗口只用它订阅信号，不直接操控服务内部。
        """
        super().__init__()
        self._service_manager = service_manager

        # 窗口基础属性
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(900, 620)  # 初始窗口大小（宽 x 高）

        # ---- 悬浮预警窗（独立窗口，置顶半透明） ----
        self._alert_overlay = AlertOverlay()

        # ---- 选项卡容器 ----
        self._tabs = QTabWidget(self)
        self._monitor_tab = MonitorTab()
        self._jump_tab = JumpTab()
        self._tabs.addTab(self._monitor_tab, "频道监控")
        self._tabs.addTab(self._jump_tab, "跳数计算")
        self.setCentralWidget(self._tabs)  # 选项卡作为窗口中心内容

        # ---- 信号接线 ----
        self._connect_signals()

    def _connect_signals(self) -> None:
        """
        把"服务信号 -> UI 槽"、"UI 信号 -> 控制动作"连接起来。

        这里是整个程序的"接线板"：
        - 服务的日志/预警信号 连到 日志控件/悬浮窗
        - 选项卡按钮信号 连到 服务启停动作
        """
        # ---- 监控页按钮 -> 服务启停 ----
        self._monitor_tab.sig_start_clicked.connect(self._on_start_clicked)
        self._monitor_tab.sig_stop_clicked.connect(self._on_stop_clicked)

        # ---- 遍历所有服务，把日志/错误信号接到日志显示区 ----
        for name in self._service_manager.list_services():
            service = self._service_manager.get(name)
            if service is None:
                continue
            # sig_log(级别, 内容) -> LogViewer.append_log
            service.sig_log.connect(self._monitor_tab.log_viewer.append_log)
            # sig_error(错误) -> 以 ERROR 级别写入日志区
            service.sig_error.connect(
                lambda msg: self._monitor_tab.log_viewer.append_log("ERROR", msg)
            )

        # ---- Intel 预警信号 -> 悬浮预警窗 ----
        intel_service = self._service_manager.get("IntelMonitor")
        if intel_service is not None:
            intel_service.sig_alert.connect(self._alert_overlay.show_alert)

    @pyqtSlot()
    def _on_start_clicked(self) -> None:
        """启动按钮点击：启动所有服务并刷新界面状态。"""
        self._service_manager.start_all()
        self._monitor_tab.set_running_state(True)

    @pyqtSlot()
    def _on_stop_clicked(self) -> None:
        """停止按钮点击：停止所有服务并刷新界面状态。"""
        self._service_manager.stop_all()
        self._monitor_tab.set_running_state(False)

    def closeEvent(self, event) -> None:
        """
        窗口关闭事件：先优雅停止所有服务，再关闭窗口。

        说明：不重写此方法的话，关闭窗口时后台线程可能还在跑，
        导致进程无法退出或资源未释放。
        """
        logger.info("主窗口关闭，正在停止所有服务...")
        self._service_manager.stop_all()
        event.accept()  # 确认关闭窗口
