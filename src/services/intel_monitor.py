"""
============================================================
模块：services/intel_monitor.py —— Intel 频道监控服务
------------------------------------------------------------
功能说明：
    监视 EVE 客户端的 Intel（情报）频道日志。
    当日志中出现配置的危险关键字（如 "gank"、"红加" 等）时，
    发射预警信号：UI 弹出悬浮预警窗，音频服务进行语音播报。

    🔒 线程安全说明：
      与 LocalMonitor 相同——回调在 watchdog 线程，
      只通过 Qt 信号向外传递数据，不直接操作 UI。
============================================================
"""
from typing import List

from PyQt5.QtCore import pyqtSignal

from core.audio_manager import AudioManager
from core.log_watcher import LogWatcher
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("intel_monitor")


class IntelMonitorService(BaseService):
    """
    Intel 频道监控服务。

    新增信号：
        sig_alert(str): 预警信号，参数为触发预警的原始日志行。
                        UI 收到后弹出置顶半透明悬浮预警窗。
    """

    sig_alert = pyqtSignal(str)  # (触发预警的日志内容)

    def __init__(
        self,
        log_watcher: LogWatcher,
        audio_manager: AudioManager,
        danger_keywords: List[str],
        parent=None,
    ):
        """
        参数：
            log_watcher: core 层日志监视器实例
            audio_manager: core 层音频管理器（用于语音播报）
            danger_keywords: 危险关键字列表（来自配置，禁止写死在代码里）
            parent: Qt 父对象
        """
        super().__init__(service_name="IntelMonitor", parent=parent)
        self._log_watcher = log_watcher
        self._audio_manager = audio_manager
        # 关键字统一小写存储，匹配时也转小写，实现"忽略大小写"匹配
        self._danger_keywords = [kw.lower() for kw in danger_keywords]

    def run(self) -> None:
        """线程主体：订阅日志并等待停止指令（事件驱动型服务）。"""
        try:
            self._log_watcher.subscribe(self._on_log_line)
            self.emit_log(
                "INFO",
                f"Intel 频道监控已就绪，监控关键字 {len(self._danger_keywords)} 个",
            )

            # 🔒 线程安全说明：循环检查 _running 标志位，响应 stop()
            while self._running:
                self.msleep(200)

        except Exception as e:  # noqa: BLE001 —— 异常通过信号发给 UI
            self.emit_error(f"Intel 监控运行异常：{e}")
        finally:
            self._log_watcher.unsubscribe(self._on_log_line)
            self.emit_log("INFO", "Intel 频道监控已退出")
            self.sig_finished.emit(self.service_name)

    def _on_log_line(self, line: str) -> None:
        """
        LogWatcher 回调：检查日志行是否命中危险关键字。

        ⚠️ 注意：运行在 watchdog 线程，禁止抛异常、禁止操作 UI。
        """
        try:
            line_lower = line.lower()
            # 逐个比对危险关键字（忽略大小写）
            for keyword in self._danger_keywords:
                if keyword in line_lower:
                    # 命中关键字：发射预警信号（UI 弹窗）+ 语音播报
                    self.emit_log("WARNING", f"[Intel 预警] 命中关键字「{keyword}」")
                    self.sig_alert.emit(line)
                    self._audio_manager.speak("注意，情报频道发现危险信息")
                    break  # 一行只预警一次，避免重复播报
        except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
            logger.error(f"Intel 日志行处理异常（已拦截）：{e}")
