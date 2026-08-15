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
from typing import List


@dataclass
class MonitorConfig:
    """
    监控相关的配置项。

    字段说明：
        eve_log_dir: EVE 客户端日志目录（Local/Intel 频道日志所在位置）
        danger_keywords: Intel 频道需要预警的危险关键字列表
        enable_voice: 是否开启语音播报
    """
    eve_log_dir: str = ""                                  # EVE 日志目录路径
    danger_keywords: List[str] = field(default_factory=list)  # 危险关键字列表
    enable_voice: bool = True                              # 是否开启语音


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
        monitor_data = data.get("monitor", {})
        ui_data = data.get("ui", {})
        return cls(
            monitor=MonitorConfig(**monitor_data) if monitor_data else MonitorConfig(),
            ui=UiConfig(**ui_data) if ui_data else UiConfig(),
        )
