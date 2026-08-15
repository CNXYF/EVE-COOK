"""
============================================================
模块：services/drone_monitor.py —— 无人机状态监控服务
------------------------------------------------------------
功能说明：
    定时对 EVE 客户端窗口的"无人机面板"区域截图，
    后续通过图像分析判断无人机状态（受损/被攻击等），
    异常时发射信号通知 UI 预警。

    ⚠️ 注意：仅限 Windows 系统（截图依赖 pywin32）

    🔒 线程安全说明：
      截图循环运行在本服务的 QThread 中，
      循环体检查 _running 标志位以响应 stop()，
      截图结果只通过 Qt 信号发出，不直接操作 UI。
============================================================
"""
from PyQt5.QtCore import pyqtSignal

from core.window_enumerator import WindowEnumerator
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("drone_monitor")


class DroneMonitorService(BaseService):
    """
    无人机状态监控服务。

    新增信号：
        sig_drone_alert(str): 无人机异常预警信号，参数为异常描述。
                              UI 收到后弹出预警提示。
    """

    sig_drone_alert = pyqtSignal(str)  # (异常描述文本)

    def __init__(self, interval_ms: int = 2000, parent=None):
        """
        参数：
            interval_ms: 截图检查间隔（毫秒），默认 2 秒一次
            parent: Qt 父对象
        """
        super().__init__(service_name="DroneMonitor", parent=parent)
        self._interval_ms = interval_ms
        self._window_enumerator = WindowEnumerator()  # 复用 core 层窗口枚举器

    def run(self) -> None:
        """
        线程主体：定时截图检查无人机状态。

        与 Local/Intel 监控不同，本服务是"轮询型"——
        需要主动定时截图（图像状态没有日志文件可监听）。
        """
        try:
            self.emit_log("INFO", f"无人机监控已启动，检查间隔 {self._interval_ms}ms")

            # 🔒 线程安全说明：循环检查 _running，stop() 后自然退出
            while self._running:
                self._check_drone_status()
                # msleep 期间线程休眠，不占 CPU；醒来后再检查标志位
                self.msleep(self._interval_ms)

        except Exception as e:  # noqa: BLE001 —— 异常通过信号发给 UI
            self.emit_error(f"无人机监控运行异常：{e}")
        finally:
            self.emit_log("INFO", "无人机监控已退出")
            self.sig_finished.emit(self.service_name)

    def _check_drone_status(self) -> None:
        """
        执行一次无人机状态检查。

        骨架阶段流程：
        1. 枚举 EVE 窗口（确认客户端在运行）
        2. TODO: 对无人机面板区域截图（pywin32 + Pillow）
        3. TODO: 图像分析判断状态
        4. 异常时发射 sig_drone_alert
        """
        try:
            eve_windows = self._window_enumerator.enumerate_eve_windows()

            # 没找到 EVE 窗口：客户端未运行，跳过本次检查
            if not eve_windows:
                return

            # TODO: 拿到窗口句柄后，用 win32gui/win32ui + PIL 截取面板区域
            # TODO: 对截图做状态分析（颜色阈值 / 模板匹配）
            # 分析发现异常时：self.sig_drone_alert.emit("无人机受损")

        except Exception as e:  # noqa: BLE001 —— 单次检查失败不影响循环继续
            logger.error(f"无人机状态检查失败（已拦截）：{e}")
