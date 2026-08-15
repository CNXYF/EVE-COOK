"""
============================================================
模块：services/local_monitor.py —— Local（本地）频道监控服务
------------------------------------------------------------
功能说明：
    监视 EVE 客户端的"本地"频道日志（国服频道名为"本地"）。
    已接入真实日志解析：
    - 识别"频道更换为本地：星系名"系统消息，追踪当前所在星系
    - 星系变化时发射 sig_system_changed 信号通知 UI
    - 本地频道有人发言时发射 sig_local_message 信号

    频道识别原理：
      EVE 日志文件名 = 频道名_日期_时间_监听者.txt，
      例如 本地_20260323_232140_2117006221.txt，
      因此从文件名就能判断这条消息属于哪个频道。

    🔒 线程安全说明：
      LogWatcher 的回调运行在 watchdog 线程，
      本服务只把数据转成 Qt 信号发射出去，
      Qt 信号跨线程投递是安全的（自动排队到接收方线程）。
============================================================
"""
from pathlib import Path

from PyQt5.QtCore import pyqtSignal

from core.chatlog_parser import (
    channel_name_from_file,
    extract_local_system,
    parse_line,
)
from core.log_watcher import LogWatcher
from services.base_service import BaseService
from utils.constants import LOCAL_CHANNEL_NAMES
from utils.logger import get_logger

logger = get_logger("local_monitor")


class LocalMonitorService(BaseService):
    """
    Local（本地）频道监控服务。

    新增信号：
        sig_system_changed(str): 当前星系变化信号，参数为新星系名。
                                 UI 收到后刷新"当前星系"显示。
        sig_local_message(str, str): 本地频道发言信号，
                                     参数为 (发言人, 内容)。
    """

    # 当前星系变化信号（携带星系名）
    sig_system_changed = pyqtSignal(str)
    # 本地频道发言信号（携带 发言人、内容）
    sig_local_message = pyqtSignal(str, str)

    def __init__(self, log_watcher: LogWatcher, parent=None):
        """
        参数：
            log_watcher: core 层的日志监视器实例（由外部注入，便于复用）
            parent: Qt 父对象
        """
        super().__init__(service_name="LocalMonitor", parent=parent)
        self._log_watcher = log_watcher
        # 当前所在星系名（收到"频道更换为本地"消息时更新）
        self._current_system = ""

    @property
    def current_system(self) -> str:
        """只读属性：当前所在星系名（未知时为空字符串）。"""
        return self._current_system

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

    def _on_log_line(self, file_path: Path, line: str) -> None:
        """
        LogWatcher 回调：收到一行新日志。

        ⚠️ 注意：此方法运行在 watchdog 线程，
        内部禁止抛异常，禁止直接操作 UI。

        参数：
            file_path: 日志文件路径（文件名含频道名）
            line: 新增的日志行文本
        """
        try:
            # ---- 第一步：按文件名过滤，只处理"本地"频道 ----
            channel = channel_name_from_file(file_path)
            if channel not in LOCAL_CHANNEL_NAMES:
                return

            # ---- 第二步：解析消息行 ----
            message = parse_line(line, channel=channel)
            if message is None:
                return  # 文件头、分隔线等非消息行，忽略

            # ---- 第三步：系统消息 -> 检查是否切换了星系 ----
            if message.is_system:
                new_system = extract_local_system(message.content)
                if new_system is not None and new_system != self._current_system:
                    old = self._current_system or "未知"
                    self._current_system = new_system
                    self.emit_log("INFO", f"[Local] 星系变化：{old} -> {new_system}")
                    self.sig_system_changed.emit(new_system)
                return

            # ---- 第四步：玩家发言 -> 发射发言信号 ----
            self.sig_local_message.emit(message.sender, message.content)

        except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
            logger.error(f"Local 日志行处理异常（已拦截）：{e}")
