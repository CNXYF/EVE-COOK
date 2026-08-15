"""
============================================================
模块：services/drone_monitor.py —— 无人机状态监控服务（日志驱动）
------------------------------------------------------------
功能说明：
    订阅 LogWatcher 的日志行事件，检测无人机受损关键字。
    日志行命中任一关键字时发射预警信号 + 语音播报。

    变更说明：已从"截图识别"改为"日志关键字检测"，
              不再依赖窗口句柄、ROI 框选和定时截图，
              彻底移除了 pywin32 截图相关逻辑。

    🔒 线程安全说明：
      LogWatcher 的回调运行在 watchdog 线程，
      本服务只把数据转成 Qt 信号发射出去，
      Qt 信号跨线程投递是安全的（自动排队到接收方线程）。
============================================================
"""
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import pyqtSignal

from core.audio_manager import AudioManager
from core.chatlog_parser import channel_name_from_file, parse_line
from core.log_watcher import LogWatcher
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("drone_monitor")


# 默认无人机受损关键字（配置 drone_keywords 为空时使用）
# 匹配规则：日志消息内容命中任一关键字（不区分大小写）即触发预警
# ⚠️ 用户提供真实日志样本后，可在 UI 的"无人机预警关键字"区编辑替换
DEFAULT_DRONE_KEYWORDS: List[str] = [
    "无人机受损",
    "无人机被摧毁",
    "无人机受到攻击",
    "drone destroyed",
    "drone damaged",
    "drone under attack",
]


class DroneMonitorService(BaseService):
    """
    无人机监控服务（日志驱动型）。

    工作原理：
        1. 启动时订阅 LogWatcher 的日志行事件
        2. 每收到一行日志，检查消息内容是否命中关键字
        3. 命中则发射 sig_drone_alert 预警信号 + TTS 语音播报

    信号：
        sig_drone_alert(str): 无人机受损预警，参数为预警描述文本。
                              UI 收到后弹出预警提示 + 写 WARNING 日志。
    """

    # 无人机受损预警信号（携带描述文本）
    sig_drone_alert = pyqtSignal(str)

    def __init__(
        self,
        log_watcher: LogWatcher,
        drone_keywords: Optional[List[str]] = None,
        audio_manager: Optional[AudioManager] = None,
        voice_enabled: bool = True,
        parent=None,
    ):
        """
        参数：
            log_watcher:    core 层日志监视器实例（由外部注入）
            drone_keywords: 无人机受损关键字列表；None 或空列表使用 DEFAULT_DRONE_KEYWORDS
            audio_manager:  音频管理器实例（可选，用于 TTS 语音预警）
            voice_enabled:  是否启用语音播报（仅在 audio_manager 存在时生效）
            parent:         Qt 父对象
        """
        super().__init__(service_name="DroneMonitor", parent=parent)
        self._log_watcher = log_watcher
        self._audio_manager = audio_manager
        self._voice_enabled = voice_enabled
        # 关键字列表：传入为空则用默认关键字
        self._keywords: List[str] = (
            list(drone_keywords) if drone_keywords else list(DEFAULT_DRONE_KEYWORDS)
        )

    def run(self) -> None:
        """
        线程主体：订阅日志监视器并等待停止指令。

        说明：本服务是"事件驱动"型——真正的工作由 LogWatcher 回调触发，
              run() 只需保持线程存活并响应 stop()。
        """
        try:
            # 订阅日志行（LogWatcher 有新内容时会调用 _on_log_line）
            self._log_watcher.subscribe(self._on_log_line)
            self.emit_log(
                "INFO",
                f"无人机日志监控已就绪，当前关键字：{self._keywords}"
            )

            # 事件驱动型服务：循环等待，直到收到 stop() 指令
            # 🔒 线程安全说明：_running 由 stop() 置 False，本循环检测退出
            while self._running:
                self.msleep(200)  # 毫秒级休眠，避免空转占 CPU

        except Exception as e:  # noqa: BLE001 —— 兜底：异常通过信号发给 UI
            self.emit_error(f"无人机监控运行异常：{e}")
        finally:
            # 无论正常退出还是异常，都要取消订阅，防止内存泄漏
            self._log_watcher.unsubscribe(self._on_log_line)
            self.emit_log("INFO", "无人机日志监控已退出")
            self.sig_finished.emit(self.service_name)

    def _on_log_line(self, file_path: Path, line: str) -> None:
        """
        LogWatcher 回调：检测日志行是否命中无人机受损关键字。

        ⚠️ 注意：此方法运行在 watchdog 线程，
        内部禁止抛异常，禁止直接操作 UI。

        参数：
            file_path: 日志文件路径（文件名含频道名）
            line: 新增的日志行文本
        """
        try:
            # 关键字为空时不检测（兜底，正常情况 run() 已保证非空）
            if not self._keywords:
                return

            # 解析消息行，提取正文用于关键字匹配
            # 非消息行（文件头、分隔线）parse_line 返回 None，此时用原始行兜底
            message = parse_line(line)
            if message is not None:
                text = message.content
                sender = message.sender
            else:
                text = line
                sender = ""

            # 不区分大小写匹配
            text_lower = text.lower()
            for kw in self._keywords:
                if not kw:
                    continue
                if kw.lower() in text_lower:
                    # 命中关键字，构造预警信息
                    channel = channel_name_from_file(file_path)
                    # 先拼接发送者片段（避免 f-string 内嵌套引号导致语法错误）
                    sender_part = f"发送者:{sender} " if sender else ""
                    alert_msg = (
                        f"[无人机预警] 频道:{channel} "
                        f"{sender_part}"
                        f'命中关键字"{kw}"'
                    )
                    # 发射预警信号
                    self.sig_drone_alert.emit(alert_msg)
                    # 写 WARNING 日志
                    self.emit_log("WARNING", alert_msg)

                    # TTS 语音播报（仅在配置启用时）
                    if self._audio_manager is not None and self._voice_enabled:
                        try:
                            self._audio_manager.speak("无人机受损，请注意")
                        except Exception as speak_err:  # noqa: BLE001
                            logger.warning(f"无人机语音播报失败：{speak_err}")

                    # 一行日志只报一次（命中第一个关键字即跳出）
                    break

        except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
            logger.error(f"无人机日志检测异常（已拦截）：{e}")

    def set_drone_keywords(self, keywords: List[str]) -> None:
        """
        运行时更新无人机受损关键字列表。

        参数：
            keywords: 新的关键字列表；空列表恢复为默认关键字。
        """
        self._keywords = list(keywords) if keywords else list(DEFAULT_DRONE_KEYWORDS)
        self.emit_log("INFO", f"无人机关键字已更新：{self._keywords}")

    def set_voice_enabled(self, enabled: bool) -> None:
        """运行时切换语音播报开关。"""
        self._voice_enabled = enabled
