"""
============================================================
模块：services/intel_monitor.py —— Intel 频道监控服务
------------------------------------------------------------
功能说明：
    监视 EVE 客户端的 Intel（情报）频道日志。
    已接入真实日志解析：
    - 通过配置指定要监控的频道名（如 southeast.imperium）
    - 只处理指定频道的消息，其他频道一律忽略
    - 消息内容命中危险关键字时发射 sig_alert 预警信号：
      UI 弹出悬浮预警窗，音频管理器进行语音播报

    频道识别原理：
      EVE 日志文件名 = 频道名_日期_时间_监听者.txt，
      从文件名即可判断消息所属频道。

    🔒 线程安全说明：
      与 LocalMonitor 相同——回调在 watchdog 线程，
      只通过 Qt 信号向外传递数据，不直接操作 UI。
============================================================
"""
from pathlib import Path
from typing import List

from PyQt5.QtCore import pyqtSignal

from core.audio_manager import AudioManager
from core.chatlog_parser import channel_name_from_file, parse_line
from core.log_watcher import LogWatcher
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("intel_monitor")


class IntelMonitorService(BaseService):
    """
    Intel 频道监控服务。

    新增信号：
        sig_alert(str): 预警信号，参数为触发预警的完整描述。
                        UI 收到后弹出置顶半透明悬浮预警窗。
        sig_intel_message(str, str, str): 情报消息信号，
                        参数为 (频道名, 发言人, 内容)，供 UI 展示。
    """

    sig_alert = pyqtSignal(str)                       # (预警描述)
    sig_intel_message = pyqtSignal(str, str, str)     # (频道, 发言人, 内容)

    def __init__(
        self,
        log_watcher: LogWatcher,
        audio_manager: AudioManager,
        danger_keywords: List[str],
        intel_channels: List[str],
        parent=None,
    ):
        """
        参数：
            log_watcher: core 层日志监视器实例
            audio_manager: core 层音频管理器（用于语音播报）
            danger_keywords: 危险关键字列表（来自配置，禁止写死在代码里）
            intel_channels: 要监控的 Intel 频道名列表（来自配置），
                            例如 ["southeast.imperium"]；
                            空列表表示监控"除本地外所有频道"
            parent: Qt 父对象
        """
        super().__init__(service_name="IntelMonitor", parent=parent)
        self._log_watcher = log_watcher
        self._audio_manager = audio_manager
        # 关键字统一小写存储，匹配时也转小写，实现"忽略大小写"匹配
        self._danger_keywords = [kw.lower() for kw in danger_keywords]
        # 频道名统一小写存储（频道名不区分大小写更稳妥）
        self._intel_channels = {ch.lower() for ch in intel_channels}

    def run(self) -> None:
        """线程主体：订阅日志并等待停止指令（事件驱动型服务）。"""
        try:
            self._log_watcher.subscribe(self._on_log_line)
            if self._intel_channels:
                channels_desc = "、".join(sorted(self._intel_channels))
            else:
                channels_desc = "全部频道"
            self.emit_log(
                "INFO",
                f"Intel 频道监控已就绪，监控频道：{channels_desc}，"
                f"危险关键字 {len(self._danger_keywords)} 个",
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

    def _on_log_line(self, file_path: Path, line: str) -> None:
        """
        LogWatcher 回调：检查日志行是否来自 Intel 频道、是否命中关键字。

        ⚠️ 注意：运行在 watchdog 线程，禁止抛异常、禁止操作 UI。

        参数：
            file_path: 日志文件路径（文件名含频道名）
            line: 新增的日志行文本
        """
        try:
            # ---- 第一步：按文件名识别频道并过滤 ----
            channel = channel_name_from_file(file_path)
            if self._intel_channels and channel.lower() not in self._intel_channels:
                return  # 不在监控名单内，忽略

            # ---- 第二步：解析消息行 ----
            message = parse_line(line, channel=channel)
            if message is None or message.is_system:
                return  # 非消息行或系统消息（如置顶信息）不参与关键字预警

            # 发射情报消息信号（UI 可用于展示最近情报）
            self.sig_intel_message.emit(channel, message.sender, message.content)

            # ---- 第三步：关键字匹配（忽略大小写） ----
            content_lower = message.content.lower()
            for keyword in self._danger_keywords:
                if keyword in content_lower:
                    # 命中关键字：组装预警描述，发射信号 + 语音播报
                    alert_text = f"[{channel}] {message.sender}: {message.content}"
                    self.emit_log("WARNING", f"[Intel 预警] 命中关键字「{keyword}」：{alert_text}")
                    self.sig_alert.emit(alert_text)
                    self._audio_manager.speak("注意，情报频道发现危险信息")
                    break  # 一条消息只预警一次，避免重复播报

        except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
            logger.error(f"Intel 日志行处理异常（已拦截）：{e}")
