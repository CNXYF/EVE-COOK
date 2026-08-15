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
import random
from enum import Enum
from typing import Dict, Optional

from PyQt5.QtCore import pyqtSignal

from core.window_enumerator import WindowEnumerator, WindowInfo
from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("drone_monitor")

# 延迟导入 AudioManager，避免循环依赖或缺少依赖时报错
try:
    from core.audio_manager import AudioManager
except ImportError:
    AudioManager = None  # type: ignore


class DroneStatus(Enum):
    """
    无人机状态枚举。

    状态流转：IDLE → ATTACKING → DAMAGED → RETURNING → IDLE
    """
    IDLE = "空闲"
    ATTACKING = "攻击中"
    RETURNING = "返航"
    DAMAGED = "受损"


class DroneMonitorService(BaseService):
    """
    无人机状态监控服务。

    新增信号：
        sig_status_changed(int, str, str): 无人机状态变更信号
            参数：(窗口句柄 hwnd, 角色名, 状态值字符串)
        sig_drone_alert(str): 无人机异常预警信号，参数为异常描述。
                              UI 收到后弹出预警提示。
    """

    sig_status_changed = pyqtSignal(int, str, str)  # (hwnd, 角色名, 状态值字符串)
    sig_drone_alert = pyqtSignal(str)               # (异常描述文本)

    def __init__(
        self,
        interval_ms: int = 2000,
        audio_manager: Optional["AudioManager"] = None,
        voice_enabled: bool = True,
        target_hwnd: int = 0,
        parent=None,
    ):
        """
        参数：
            interval_ms: 截图检查间隔（毫秒），默认 2 秒一次
            audio_manager: 音频管理器实例，用于 TTS 语音播报（可选）
            voice_enabled: 是否启用语音播报（默认 True）
            target_hwnd: 指定监控的窗口句柄，0 = 监控所有 EVE 窗口（默认 0）
            parent: Qt 父对象
        """
        super().__init__(service_name="DroneMonitor", parent=parent)
        self._interval_ms = interval_ms
        self._window_enumerator = WindowEnumerator()  # 复用 core 层窗口枚举器

        # 音频相关
        self._audio_manager = audio_manager
        self._voice_enabled = voice_enabled

        # 目标窗口句柄（0 = 所有窗口）
        self._target_hwnd = target_hwnd

        # 每个窗口独立记录上一次状态：hwnd -> DroneStatus
        self._last_statuses: Dict[int, DroneStatus] = {}

        # 每个窗口独立的检查计数器，用于仿真状态机推进：hwnd -> 计数
        self._check_counts: Dict[int, int] = {}

        # 每个窗口独立的"下一次推进阈值"，随机 5~10 次检查后推进状态
        self._advance_thresholds: Dict[int, int] = {}

    def set_target_window(self, hwnd: int) -> None:
        """
        运行时切换目标监控窗口。

        参数：
            hwnd: 新的目标窗口句柄，0 = 监控所有 EVE 窗口
        """
        old_target = self._target_hwnd
        self._target_hwnd = hwnd
        self.emit_log(
            "INFO",
            f"监控目标窗口已切换：{old_target or '全部窗口'} → {hwnd or '全部窗口'}"
        )

    def run(self) -> None:
        """
        线程主体：定时截图检查无人机状态。

        与 Local/Intel 监控不同，本服务是"轮询型"——
        需要主动定时截图（图像状态没有日志文件可监听）。
        """
        try:
            self.emit_log("INFO", f"无人机监控已启动，检查间隔 {self._interval_ms}ms")
            if self._target_hwnd != 0:
                self.emit_log("INFO", f"当前仅监控窗口句柄：{self._target_hwnd}")
            else:
                self.emit_log("INFO", "当前监控所有 EVE 窗口")

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

        流程：
        1. enumerate_eve_windows 获取所有 EVE 窗口
        2. 若 target_hwnd != 0 仅处理匹配句柄的窗口
        3. 每个窗口独立记录上一次 DroneStatus
        4. 图像识别逻辑以 TODO 占位，当前使用"状态仿真切换逻辑"用于 UI 演示：
           - 每隔 5-10 次检查按概率推进状态机：
             IDLE → ATTACKING → DAMAGED → RETURNING → IDLE
        5. 状态变更时发射 sig_status_changed + emit_log INFO
        6. DAMAGED 时发射 sig_drone_alert + 语音播报（若配置）
        """
        try:
            eve_windows = self._window_enumerator.enumerate_eve_windows()

            # 没找到 EVE 窗口：客户端未运行，跳过本次检查
            if not eve_windows:
                return

            # 若指定了目标窗口句柄，仅保留匹配的窗口
            if self._target_hwnd != 0:
                eve_windows = [
                    w for w in eve_windows if w.hwnd == self._target_hwnd
                ]
                if not eve_windows:
                    # 指定的目标窗口不存在，跳过
                    return

            # 逐个窗口处理
            for window in eve_windows:
                self._process_single_window(window)

        except Exception as e:  # noqa: BLE001 —— 单次检查失败不影响循环继续
            logger.error(f"无人机状态检查失败（已拦截）：{e}")

    def _process_single_window(self, window: WindowInfo) -> None:
        """
        处理单个 EVE 窗口的无人机状态检查。

        参数：
            window: 窗口信息（含 hwnd、角色名等）
        """
        hwnd = window.hwnd
        character_name = window.character_name or f"窗口{hwnd}"

        # ============================================================
        # TODO: 真实图像识别逻辑（接入时替换仿真逻辑即可）
        # ------------------------------------------------------------
        # 1. 对无人机面板区域截图（pywin32 + Pillow）
        #    - 使用 win32gui.GetWindowRect(hwnd) 获取窗口坐标
        #    - 根据面板在窗口中的相对位置裁剪
        # 2. 图像分析判断状态：
        #    - 颜色阈值：检测受损时的红色闪烁区域
        #    - 模板匹配：对比"空闲/攻击中/返航/受损"的模板截图
        # 3. 根据分析结果设置 current_status
        # ============================================================

        # ------------------------------------------------------------
        # 仿真状态切换逻辑（仅用于 UI 演示，图像识别接入时替换）
        # ------------------------------------------------------------
        # 初始化该窗口的计数器和阈值
        if hwnd not in self._check_counts:
            self._check_counts[hwnd] = 0
        if hwnd not in self._advance_thresholds:
            self._advance_thresholds[hwnd] = random.randint(5, 10)
        if hwnd not in self._last_statuses:
            self._last_statuses[hwnd] = DroneStatus.IDLE

        # 计数 +1
        self._check_counts[hwnd] += 1

        # 判断是否到达推进阈值
        current_status = self._last_statuses[hwnd]
        if self._check_counts[hwnd] >= self._advance_thresholds[hwnd]:
            # 重置计数，生成新的随机阈值
            self._check_counts[hwnd] = 0
            self._advance_thresholds[hwnd] = random.randint(5, 10)

            # 按状态机流转推进
            status_flow = [
                DroneStatus.IDLE,
                DroneStatus.ATTACKING,
                DroneStatus.DAMAGED,
                DroneStatus.RETURNING,
            ]
            try:
                idx = status_flow.index(current_status)
                current_status = status_flow[(idx + 1) % len(status_flow)]
            except ValueError:
                current_status = DroneStatus.IDLE
        # ------------------------------------------------------------
        # 仿真逻辑结束
        # ------------------------------------------------------------

        # 若状态发生变更，则发射信号并记录日志
        last_status = self._last_statuses.get(hwnd)
        if last_status != current_status:
            self._last_statuses[hwnd] = current_status

            # 发射状态变更信号
            self.sig_status_changed.emit(hwnd, character_name, current_status.value)

            # 记录 INFO 日志
            self.emit_log(
                "INFO",
                f"[{character_name}] 无人机状态变更："
                f"{last_status.value if last_status else '未知'} → {current_status.value}"
            )

            # DAMAGED 状态：发射预警信号 + 语音播报
            if current_status == DroneStatus.DAMAGED:
                alert_msg = "无人机受损，请回收"
                self.sig_drone_alert.emit(alert_msg)

                # 若配置了音频管理器且语音已启用，则播报
                if self._audio_manager is not None and self._voice_enabled:
                    try:
                        self._audio_manager.speak(f"{character_name}：{alert_msg}")
                    except Exception as speak_err:  # noqa: BLE001
                        logger.warning(f"语音播报失败：{speak_err}")
