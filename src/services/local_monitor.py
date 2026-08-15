"""
============================================================
模块：services/local_monitor.py —— Local 频道监控服务
------------------------------------------------------------
功能说明：
    监视 EVE 客户端的 Local（本地）频道日志文件。
    当本地频道人员列表发生变化（有人进入/离开星系）时，
    把变化内容通过信号发送给 UI，必要时触发预警。

    工作流程：
      LogWatcher（core 层）监听到日志新行
        -> 回调 _on_log_line 在本服务中处理
        -> 通过 sig_local_changed 信号通知 UI

    🔒 线程安全说明：
      LogWatcher 的回调运行在 watchdog 线程，
      本服务只把数据转成 Qt 信号发射出去，
      Qt 信号跨线程投递是安全的（自动排队到接收方线程）。
============================================================
"""
from typing import Set

from PyQt5.QtCore import pyqtSignal

from core.log_watcher import LogWatcher
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("local_monitor")


class LocalMonitorService(BaseService):
    """
    Local 频道监控服务。

    新增信号：
        sig_local_changed(int): 本地频道人数变化信号，参数为当前人数。
                               UI 收到后刷新人数显示。
    """

    # 本地频道人数变化信号（携带当前人数）
    sig_local_changed = pyqtSignal(int)

    def __init__(self, log_watcher: LogWatcher, parent=None):
        """
        参数：
            log_watcher: core 层的日志监视器实例（由外部注入，便于复用）
            parent: Qt 父对象
        """
        super().__init__(service_name="LocalMonitor", parent=parent)
        self._log_watcher = log_watcher
        # 记录已知的本地频道成员名单，用于对比人员变化
        self._known_members: Set[str] = set()

    def run(self) -> None:
        """
        线程主体：订阅日志监视器并等待停止指令。

        说明：
          本服务是"事件驱动"型——真正的工作由 LogWatcher 回调触发，
          run() 只需要保持线程存活并响应 stop() 即可。
        """
        try:
            # 订阅日志行（LogWatcher 有新内容时会调用 _on_log_line）
            self._log_watcher.subscribe(self._on_log_line)
            self.emit_log("INFO", "Local 频道监控已就绪，等待日志更新")

            # 事件驱动型服务：循环等待，直到收到 stop() 指令
            # 🔒 线程安全说明：_running 由 stop() 置 False，本循环检测退出
            while self._running:
                self.msleep(200)  # Qt 线程的毫秒级休眠，避免空转占 CPU

        except Exception as e:  # noqa: BLE001 —— 兜底：异常通过信号发给 UI
            self.emit_error(f"Local 监控运行异常：{e}")
        finally:
            # 无论正常退出还是异常，都要取消订阅，防止内存泄漏
            self._log_watcher.unsubscribe(self._on_log_line)
            self.emit_log("INFO", "Local 频道监控已退出")
            self.sig_finished.emit(self.service_name)

    def _on_log_line(self, line: str) -> None:
        """
        LogWatcher 回调：收到一行新日志。

        ⚠️ 注意：此方法运行在 watchdog 线程，
        内部禁止抛异常，禁止直接操作 UI。

        参数：
            line: 新增的日志行文本。
        """
        try:
            # 骨架阶段：只过滤出 Local 频道相关的行（含 "Local" 关键字）
            # TODO: 接入真实日志后，按 EVE 日志格式解析进出人员
            if "Local" in line:
                self.emit_log("INFO", f"[Local] {line}")
                # 人数变化时发射信号（骨架阶段暂以名单数量模拟）
                self.sig_local_changed.emit(len(self._known_members))
        except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
            logger.error(f"Local 日志行处理异常（已拦截）：{e}")
