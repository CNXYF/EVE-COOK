"""
============================================================
模块：data/models/app_config.py —— 应用配置数据模型
------------------------------------------------------------
功能说明：
    用 dataclass 定义"应用配置"的结构。
    强制约束：配置必须用 dataclass 定义结构，禁止魔法字符串。
    小白理解：dataclass 就像一张"表格模板"，
              提前规定好每一列叫什么、是什么类型，
              填数据时不容易出错。
============================================================
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class AlertConfig:
    """
    预警相关的配置项。

    字段说明：
        home_system: 当前星系名，用于判断跳数
        jump_range: 跳数预警范围，敌对出现在多少跳以内时触发预警
        alert_window_minutes: 预警时间窗口（分钟），超过该时间的旧报告不再预警
        show_overlay: 是否显示悬浮预警窗口
        voice_system_warning: 是否播放星系预警语音（敌对进入预警范围）
        voice_local_warning: 是否播放本地预警语音（本地频道出现敌对）
        voice_drone_warning: 是否播放无人机预警语音（被无人机锁定）
    """
    home_system: str = ""                          # 当前星系
    jump_range: int = 6                            # 跳数预警范围
    alert_window_minutes: int = 20                 # 预警时间窗口（分钟）
    show_overlay: bool = True                      # 显示悬浮预警
    voice_system_warning: bool = True              # 星系预警语音
    voice_local_warning: bool = True               # 本地预警语音
    voice_drone_warning: bool = True               # 无人机预警语音


@dataclass
class DroneConfig:
    """
    无人机监控专用配置（与 UI 预览区双向同步 + 持久化）。

    字段说明：
        target_hwnd: 最近一次选中的目标窗口句柄；0 表示未选中。
                    ⚠️ 下次启动时窗口句柄通常会变化，所以读取配置后
                    仅用于"尝试还原"，还原失败时 UI 会自动切回未选中。
        roi_rect: 最近一次框选的无人机面板矩形，
                  格式 (L, T, R, B)，像素相对窗口客户区左上角。
                  若窗口分辨率不变，框选结果跨会话仍然有效；
                  若用户切换了客户端分辨率，请重新框选。
        interval_ms: 检查间隔（毫秒），默认 2 秒一次
    """
    target_hwnd: int = 0
    roi_rect: Optional[Tuple[int, int, int, int]] = None
    interval_ms: int = 2000


@dataclass
class MonitorConfig:
    """
    监控相关的配置项。

    字段说明：
        eve_log_dir: EVE 客户端 Chatlogs 日志目录
                     （默认自动定位：文档\\EVE\\logs\\Chatlogs）
        intel_channels: 要监控的 Intel 频道名列表，
                        例如 ["southeast.imperium"]；
                        空列表表示监控除本地外的所有频道
        danger_keywords: Intel 频道需要预警的危险关键字列表
        enable_voice: 是否开启语音播报
        hostile_list: 敌对角色名列表，用于精确匹配预警目标
        translation_channels: 需要翻译的频道名列表
        drone: 无人机监控子配置（目标窗口 + ROI + 间隔）
        alert: 预警子配置（跳数范围、时间窗口、语音开关等）
    """
    eve_log_dir: str = ""                                         # EVE 日志目录路径
    intel_channels: List[str] = field(default_factory=list)       # Intel 频道名单
    danger_keywords: List[str] = field(default_factory=list)      # 危险关键字列表
    enable_voice: bool = True                                     # 是否开启语音
    hostile_list: List[str] = field(default_factory=list)         # 敌对角色名列表
    translation_channels: List[str] = field(default_factory=list) # 需要翻译的频道名
    drone: DroneConfig = field(default_factory=DroneConfig)       # 无人机子配置
    alert: AlertConfig = field(default_factory=AlertConfig)       # 预警子配置


@dataclass
class UiConfig:
    """
    界面相关的配置项。

    字段说明：
        always_on_top: 悬浮预警窗是否置顶
        opacity: 悬浮窗不透明度（0.0 全透明 ~ 1.0 不透明）
    """
    always_on_top: bool = True      # 悬浮窗置顶
    opacity: float = 0.85           # 悬浮窗不透明度（半透明）


@dataclass
class AppConfig:
    """
    应用总配置，聚合各子配置。

    这是写入 / 读取 JSON 配置文件的顶层结构。
    """
    monitor: MonitorConfig = field(default_factory=MonitorConfig)  # 监控配置
    ui: UiConfig = field(default_factory=UiConfig)                 # 界面配置

    def to_dict(self) -> dict:
        """把配置对象转成普通字典，方便序列化为 JSON。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """
        从字典还原配置对象。

        采用"宽容解析"：字典里缺某个键时使用默认值，
        避免旧版本配置文件缺少新字段时直接报错。
        """
        monitor_data = data.get("monitor", {}) or {}
        ui_data = data.get("ui", {}) or {}

        alert_data = monitor_data.get("alert", {}) or {}
        monitor_data["alert"] = AlertConfig(**alert_data)

        drone_data = monitor_data.get("drone", {}) or {}
        # roi_rect: 旧配置不存在 / 长度不是 4 / 类型错误时，置 None
        raw_roi = drone_data.get("roi_rect", None)
        if raw_roi is not None:
            if isinstance(raw_roi, (list, tuple)) and len(raw_roi) == 4:
                try:
                    drone_data["roi_rect"] = (
                        int(raw_roi[0]), int(raw_roi[1]),
                        int(raw_roi[2]), int(raw_roi[3]),
                    )
                except (TypeError, ValueError):
                    drone_data["roi_rect"] = None
            else:
                drone_data["roi_rect"] = None
        monitor_data["drone"] = DroneConfig(**drone_data)

        return cls(
            monitor=MonitorConfig(**monitor_data),
            ui=UiConfig(**ui_data),
        )
