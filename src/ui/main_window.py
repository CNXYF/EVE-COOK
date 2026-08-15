"""
============================================================
模块：ui/main_window.py —— 主窗口
------------------------------------------------------------
功能说明：
    程序主窗口，承载：
    - 选项卡容器（EVE-COOK 监控页 / 频道翻译页 / 跳数计算页）
    - 悬浮预警窗（AlertOverlay）
    - 服务信号的"接线"：把各服务的信号连到对应 UI 槽函数

    UI 层职责约束：
    - 本文件不写业务逻辑，只做"信号接线"和界面更新
    - 所有后台数据都通过信号送达，不主动访问服务内部
============================================================
"""
from typing import Any, Dict, Optional

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QTabWidget

from core.audio_manager import AudioManager
from core.log_watcher import LogWatcher
from core.window_enumerator import WindowEnumerator
from data.config_manager import ConfigManager
from data.models.app_config import AppConfig
from services.drone_monitor import DroneMonitorService
from services.intel_monitor import IntelMonitorService
from services.local_monitor import LocalMonitorService
from services.service_manager import ServiceManager
from services.translation_service import TranslationService
from ui.tabs.jump_tab import JumpTab
from ui.tabs.monitor_tab import MonitorTab
from ui.tabs.translate_tab import TranslateTab
from ui.widgets.alert_overlay import AlertOverlay
from utils.constants import APP_NAME, APP_VERSION
from utils.logger import get_logger

logger = get_logger("main_window")


class MainWindow(QMainWindow):
    """
    主窗口：组装选项卡、接线服务信号。
    """

    def __init__(
        self,
        service_manager: ServiceManager,
        local_service: Optional[LocalMonitorService] = None,
        intel_service: Optional[IntelMonitorService] = None,
        drone_service: Optional[DroneMonitorService] = None,
        translation_service: Optional[TranslationService] = None,
        config_manager: Optional[ConfigManager] = None,
        config: Optional[AppConfig] = None,
        audio_manager: Optional[AudioManager] = None,
        alert_overlay: Optional[AlertOverlay] = None,
        log_watcher: Optional[LogWatcher] = None,
    ):
        """
        参数：
            service_manager:    服务管理器（由 main.py 创建并注入）。
            local_service:      LocalMonitor 服务实例（用于连接特定信号）。
            intel_service:      IntelMonitor 服务实例。
            drone_service:      DroneMonitor 服务实例。
            translation_service: TranslationService 翻译服务实例。
            config_manager:     配置管理器（用于保存配置变更）。
            config:             应用配置对象（读初始配置 & 运行时更新）。
            audio_manager:      音频管理器（预留）。
            alert_overlay:      外部注入的悬浮预警窗（为 None 则内部创建）。
            log_watcher:        日志监视器（用于把"监控频道白名单"实时同步到过滤层）。
        """
        super().__init__()
        # ---- 服务与依赖引用 ----
        self._service_manager = service_manager
        self._local_service = local_service
        self._intel_service = intel_service
        self._drone_service = drone_service
        self._translation_service = translation_service
        self._config_manager = config_manager
        self._config = config
        self._audio_manager = audio_manager
        self._log_watcher = log_watcher  # 日志监视器：UI 白名单变更时即时下发到过滤层
        self._window_enumerator = WindowEnumerator()  # 用于扫描 EVE 窗口

        # 窗口基础属性
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 720)  # 初始窗口大小（宽 x 高），增加翻译页和窗口列表空间

        # ---- 悬浮预警窗（独立窗口，置顶半透明） ----
        self._alert_overlay = alert_overlay if alert_overlay is not None else AlertOverlay()

        # ---- 选项卡容器 ----
        self._build_ui()

        # ---- 信号接线 ----
        self._connect_signals()

        # ---- 初始化翻译页配置显示 ----
        if self._config is not None:
            self._translate_tab.set_translation_channels(
                self._config.monitor.translation_channels
            )

        # ---- 初始化无人机关键字（从配置恢复 + 同步到服务）----
        # 说明：set_drone_keywords 内部用 blockSignals 保护，不会触发信号，
        #       因此必须手动把关键字下发到 DroneMonitorService。
        if self._config is not None:
            keywords = list(self._config.monitor.drone.drone_keywords)
            self._monitor_tab.set_drone_keywords(keywords)
            if self._drone_service is not None:
                self._drone_service.set_drone_keywords(keywords)

        # ---- 初始化监控频道白名单（从配置恢复 + 同步到 LogWatcher）----
        # 说明：set_monitored_channels 内部用 blockSignals 保护，
        #       不会触发 sig_monitored_channels_changed 信号，
        #       因此必须手动把白名单下发到 LogWatcher 的过滤层。
        if self._config is not None:
            channels = list(self._config.monitor.monitored_channels)
            self._monitor_tab.set_monitored_channels(channels)
            if self._log_watcher is not None:
                self._log_watcher.set_channel_whitelist(set(channels))

    def _build_ui(self) -> None:
        """
        构建选项卡 UI：
            Tab 0 (索引 0): EVE-COOK 监控页（self._monitor_tab）
            Tab 1 (索引 1): 频道翻译页（self._translate_tab）
            Tab 2 (索引 2): 跳数计算页（self._jump_tab）
        """
        self._tabs = QTabWidget(self)

        # Tab 1 索引 0：主监控页，标题 "EVE-COOK"
        self._monitor_tab = MonitorTab()
        self._tabs.addTab(self._monitor_tab, "EVE-COOK")

        # Tab 2 索引 1：翻译页，标题 "频道翻译"
        self._translate_tab = TranslateTab()
        self._tabs.addTab(self._translate_tab, "频道翻译")

        # Tab 3 索引 2：跳数计算页（移到最后），标题 "跳数计算"
        self._jump_tab = JumpTab()
        self._tabs.addTab(self._jump_tab, "跳数计算")

        self.setCentralWidget(self._tabs)  # 选项卡作为窗口中心内容

    def _connect_signals(self) -> None:
        """
        把"服务信号 -> UI 槽"、"UI 信号 -> 控制动作"连接起来。

        这里是整个程序的"接线板"：
        - 服务的日志/预警信号 连到 日志控件/悬浮窗
        - 选项卡按钮信号 连到 服务启停动作
        """
        # ============================================================
        #  第一部分：监控页按钮 -> 服务启停 / 动作
        # ============================================================
        # 旧版兼容信号
        self._monitor_tab.sig_start_clicked.connect(self._on_start_clicked)
        self._monitor_tab.sig_stop_clicked.connect(self._on_stop_clicked)

        # 新版信号：开始/停止所有
        self._monitor_tab.sig_start_all.connect(self._on_start_all)
        self._monitor_tab.sig_stop_all.connect(self._on_stop_all)

        # 新版信号：扫描一次 EVE 窗口
        self._monitor_tab.sig_scan_once.connect(self._on_scan_once)

        # 新版信号：手动触发检查占位（emit_log INFO）
        self._monitor_tab.sig_local_check.connect(
            lambda: self._monitor_tab.append_log("INFO", "手动触发 本地 检查")
        )
        self._monitor_tab.sig_drone_check.connect(
            lambda: self._monitor_tab.append_log("INFO", "手动触发 无人机 检查")
        )

        # 新版信号：监控配置变更
        self._monitor_tab.sig_config_changed.connect(self._on_monitor_config_changed)

        # 新增：监控频道白名单变更 -> 同步 LogWatcher + 持久化配置
        # 🔒 线程安全说明：LogWatcher.set_channel_whitelist 内部已加锁，
        #    可在主线程中安全调用。
        self._monitor_tab.sig_monitored_channels_changed.connect(
            self._on_monitored_channels_changed
        )

        # 新增：频道发现请求 -> 扫描 Chatlogs 目录并回填 UI
        self._monitor_tab.sig_discover_channels.connect(self._on_discover_channels)

        # 新增：无人机关键字变化 -> 持久化配置 + 同步到 DroneMonitorService
        self._monitor_tab.sig_drone_keywords_changed.connect(self._on_drone_keywords_changed)

        # ============================================================
        #  第二部分：翻译页配置变更
        # ============================================================
        self._translate_tab.sig_config_changed.connect(self._on_translate_channels_changed)

        # ============================================================
        #  第三部分：遍历所有服务，把日志/错误信号接到日志显示区
        # ============================================================
        for name in self._service_manager.list_services():
            service = self._service_manager.get(name)
            if service is None:
                continue
            # sig_log(级别, 内容) -> MonitorTab.append_log
            service.sig_log.connect(self._monitor_tab.append_log)
            # sig_error(错误) -> 以 ERROR 级别写入日志区
            service.sig_error.connect(
                lambda msg: self._monitor_tab.append_log("ERROR", msg)
            )

        # ============================================================
        #  第四部分：翻译服务 -> 翻译页结果显示
        # ============================================================
        if self._translation_service is not None:
            self._translation_service.sig_translation_ready.connect(
                self._on_translation_ready
            )

        # ============================================================
        #  第五部分：Intel 预警信号 -> 悬浮预警窗 + 日志
        # ============================================================
        if self._intel_service is not None:
            # 旧版：sig_alert -> 悬浮窗（保留）
            self._intel_service.sig_alert.connect(self._alert_overlay.show_alert)
            # 新版：sig_intel_alert -> WARNING 日志 + 悬浮窗
            self._intel_service.sig_intel_alert.connect(
                lambda channel, jumps, text: self._route_alert_to_ui(text)
            )

        # ============================================================
        #  第六部分：Local 星系变化 & 敌对预警
        # ============================================================
        if self._local_service is not None:
            # 星系变化信号 -> 监控页"当前星系"标签（保留旧连接）
            self._local_service.sig_system_changed.connect(self._monitor_tab.set_current_system)
            # Local 敌对预警 -> WARNING 日志 + 悬浮窗
            self._local_service.sig_alert_triggered.connect(self._route_alert_to_ui)

        # ============================================================
        #  第七部分：DroneMonitor 信号（日志驱动：仅预警信号）
        # ============================================================
        if self._drone_service is not None:
            # 无人机受损预警 -> WARNING 日志 + 悬浮窗
            self._drone_service.sig_drone_alert.connect(self._route_alert_to_ui)

    # ============================================================
    #  内部路由工具：预警文本 -> 日志 + 悬浮窗
    # ============================================================
    def _route_alert_to_ui(self, alert_text: str) -> None:
        """
        统一预警路由：写入 WARNING 日志，并在悬浮窗（若存在）弹出。

        参数：
            alert_text: 预警描述文本。
        """
        self._monitor_tab.append_log("WARNING", alert_text)
        if self._alert_overlay is not None:
            self._alert_overlay.show_alert(alert_text)

    # ============================================================
    #  按钮 / 动作槽函数
    # ============================================================
    @pyqtSlot()
    def _on_start_clicked(self) -> None:
        """启动按钮点击（旧版兼容）：启动所有服务并刷新界面状态。"""
        self._service_manager.start_all()
        self._monitor_tab.set_running_state(True)

    @pyqtSlot()
    def _on_stop_clicked(self) -> None:
        """停止按钮点击（旧版兼容）：停止所有服务并刷新界面状态。"""
        self._service_manager.stop_all()
        self._monitor_tab.set_running_state(False)

    @pyqtSlot()
    def _on_start_all(self) -> None:
        """开始监控：启动所有服务 + 设置监控页运行状态。"""
        self._service_manager.start_all()
        self._monitor_tab.set_running(True)

    @pyqtSlot()
    def _on_stop_all(self) -> None:
        """停止监控：停止所有服务 + 设置监控页非运行状态。"""
        self._service_manager.stop_all()
        self._monitor_tab.set_running(False)

    @pyqtSlot()
    def _on_scan_once(self) -> None:
        """扫描一次 EVE 窗口并填充到监控页窗口列表表格。"""
        try:
            windows = self._window_enumerator.scan_once()
            self._monitor_tab.set_windows(windows)
            self._monitor_tab.append_log(
                "INFO", f"窗口扫描完成，共找到 {len(windows)} 个 EVE 窗口"
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"窗口扫描失败：{e}")
            self._monitor_tab.append_log("ERROR", f"窗口扫描失败：{e}")

    # ============================================================
    #  配置变更槽函数
    # ============================================================
    @pyqtSlot(dict)
    def _on_monitor_config_changed(self, cfg_dict: Dict[str, Any]) -> None:
        """
        监控页配置变更：更新 config 对象、保存配置、同步刷新相关服务。

        处理逻辑：
            1. 若 cfg_dict 含预警参数键 -> 更新 config.monitor.alert 对应字段
            2. 若 cfg_dict 含 hostile_list -> 更新 config.monitor.hostile_list
            3. 保存配置 config_manager.save(config)
            4. 同步刷新各服务运行时配置：
               - LocalMonitor.update_hostile_list
               - IntelMonitor.update_alert_config(home_system, jump_range, voice_enabled)

        参数：
            cfg_dict: 监控页发射的配置字典（来自 MonitorTab.get_monitor_config）
        """
        if self._config is None:
            return

        changed = False

        # ---- 更新 alert 子配置（若字典含对应 key）----
        alert = self._config.monitor.alert
        alert_keys = [
            ("home_system", None),
            ("jump_range", None),
            ("alert_window_minutes", None),
            ("show_overlay", None),
            ("voice_system_warning", None),
            ("voice_local_warning", None),
            ("voice_drone_warning", None),
        ]
        for key, _ in alert_keys:
            if key in cfg_dict and hasattr(alert, key):
                old_val = getattr(alert, key)
                new_val = cfg_dict[key]
                if old_val != new_val:
                    setattr(alert, key, new_val)
                    changed = True

        # ---- 更新 hostile_list（若字典含对应 key）----
        if "hostile_list" in cfg_dict:
            new_list = list(cfg_dict["hostile_list"])
            if self._config.monitor.hostile_list != new_list:
                self._config.monitor.hostile_list = new_list
                changed = True

        # ---- 保存配置（有变更才写盘）----
        if changed and self._config_manager is not None:
            self._config_manager.save(self._config)
            self._monitor_tab.append_log("INFO", "监控配置已更新并保存")

        # ---- 同步刷新各服务运行时配置 ----
        # LocalMonitor: 更新敌对名单
        if self._local_service is not None:
            self._local_service.update_hostile_list(self._config.monitor.hostile_list)

        # IntelMonitor: 更新预警配置（本营星系 / 跳数范围 / 星系语音开关）
        if self._intel_service is not None:
            self._intel_service.update_alert_config(
                home_system=alert.home_system,
                jump_range=alert.jump_range,
                voice_enabled=alert.voice_system_warning,
            )

    @pyqtSlot()
    def _on_discover_channels(self) -> None:
        """
        频道发现：扫描 Chatlogs 目录，把找到的频道列表回填到 UI。

        说明：扫描逻辑在 LogWatcher.discover_channels 中实现（core 层），
              本方法只负责调用 + 把结果传给 MonitorTab 展示。
        """
        if self._log_watcher is None:
            self._monitor_tab.append_log("WARNING", "日志监视器未初始化，无法扫描频道")
            return

        try:
            channels = self._log_watcher.discover_channels()
        except Exception as e:  # noqa: BLE001
            self._monitor_tab.append_log("ERROR", f"扫描频道失败：{e}")
            return

        if not channels:
            self._monitor_tab.append_log(
                "WARNING",
                f"未在 {self._log_watcher.watch_dir} 发现任何频道日志，"
                "请确认已运行 EVE 客户端并产生过聊天记录"
            )
            return

        # 回填到 UI（保留已勾选状态，新增项默认勾选）
        self._monitor_tab.set_discovered_channels(channels)
        self._monitor_tab.append_log(
            "INFO", f"频道扫描完成，共发现 {len(channels)} 个频道"
        )

    @pyqtSlot(list)
    def _on_drone_keywords_changed(self, keywords: list) -> None:
        """
        无人机关键字变更：写入配置 + 即时下发到 DroneMonitorService。

        参数：
            keywords: 新的关键字列表（空列表 = 使用服务层默认关键字）。
        """
        if self._config is None:
            return

        new_keywords = list(keywords) if keywords else []
        # 配置持久化（仅在变化时写盘）
        if self._config.monitor.drone.drone_keywords != new_keywords:
            self._config.monitor.drone.drone_keywords = new_keywords
            if self._config_manager is not None:
                self._config_manager.save(self._config)

        # 即时下发到 DroneMonitorService（启动前后均生效）
        if self._drone_service is not None:
            self._drone_service.set_drone_keywords(new_keywords)

        desc = "、".join(new_keywords) if new_keywords else "默认关键字"
        self._monitor_tab.append_log(
            "INFO", f"无人机关键字已更新：{desc}"
        )

    @pyqtSlot(list)
    def _on_translate_channels_changed(self, channels: list) -> None:
        """
        翻译页频道白名单变更：写入配置并保存。

        参数：
            channels: 新的翻译频道名列表。
        """
        if self._config is None:
            return

        old_channels = self._config.monitor.translation_channels
        new_channels = list(channels) if channels else []
        if old_channels == new_channels:
            return

        self._config.monitor.translation_channels = new_channels
        if self._config_manager is not None:
            self._config_manager.save(self._config)

        desc = "、".join(new_channels) if new_channels else "全部频道"
        self._monitor_tab.append_log(
            "INFO", f"翻译频道白名单已更新：{desc}"
        )

    @pyqtSlot(list)
    def _on_monitored_channels_changed(self, channels: list) -> None:
        """
        监控频道白名单变更：写入配置 + 即时下发到 LogWatcher 过滤层。

        参数：
            channels: 新的白名单频道名列表（空列表 = 监控所有频道）。

        说明：
            - UI 侧的 set_monitored_channels 用 blockSignals 保护，
              恢复配置时不会触发本槽；只有用户主动增删/勾选时才触发。
            - LogWatcher.set_channel_whitelist 内部已加锁，
              即使 LogWatcher 已在 watchdog 后台线程中广播日志，
              也能安全切换白名单，下一行日志即按新规则过滤。
        """
        if self._config is None:
            return

        new_channels = list(channels) if channels else []
        # 配置持久化（仅在变化时写盘，避免无谓 IO）
        if self._config.monitor.monitored_channels != new_channels:
            self._config.monitor.monitored_channels = new_channels
            if self._config_manager is not None:
                self._config_manager.save(self._config)

        # 即时下发到 LogWatcher（启动前后均生效）
        if self._log_watcher is not None:
            self._log_watcher.set_channel_whitelist(set(new_channels))

        desc = "、".join(new_channels) if new_channels else "全部频道"
        self._monitor_tab.append_log(
            "INFO", f"监控频道白名单已更新：{desc}"
        )

    # ============================================================
    #  翻译服务结果槽函数
    # ============================================================
    @pyqtSlot(str, str, str, str)
    def _on_translation_ready(
        self, channel: str, sender: str, original: str, translated: str
    ) -> None:
        """
        翻译完成：把结果追加到翻译页表格。

        参数：
            channel:    频道名
            sender:     发送者
            original:   原文
            translated: 译文
        """
        self._translate_tab.add_translation_result(channel, sender, original, translated)

    # ============================================================
    #  公有方法：获取服务引用集合（供外部访问）
    # ============================================================
    @property
    def service_refs(self) -> Dict[str, Any]:
        """
        只读属性：返回当前主窗口持有的各服务引用字典。

        返回键：
            service_manager, local, intel, drone, translator,
            config_manager, config, audio_manager, alert_overlay
        """
        return {
            "service_manager": self._service_manager,
            "local": self._local_service,
            "intel": self._intel_service,
            "drone": self._drone_service,
            "translator": self._translation_service,
            "config_manager": self._config_manager,
            "config": self._config,
            "audio_manager": self._audio_manager,
            "alert_overlay": self._alert_overlay,
        }

    def closeEvent(self, event) -> None:
        """
        窗口关闭事件：先优雅停止所有服务，再关闭窗口。

        说明：不重写此方法的话，关闭窗口时后台线程可能还在跑，
        导致进程无法退出或资源未释放。
        """
        logger.info("主窗口关闭，正在停止所有服务...")
        self._service_manager.stop_all()
        event.accept()  # 确认关闭窗口
