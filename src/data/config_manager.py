"""
============================================================
模块：data/config_manager.py —— 配置管理器
------------------------------------------------------------
功能说明：
    负责应用配置（JSON 文件）的读取、保存与默认值管理。
    - 配置文件路径统一用 pathlib.Path（来自 utils.constants）
    - 配置结构用 dataclass 定义（data/models/app_config.py）
    - 异常处理捕获具体异常类型，并通过日志输出
    小白理解：这个类就是"设置的保管员"，
              程序启动时找它要设置，改了设置找它保存。
============================================================
"""
import json
from pathlib import Path

from data.models.app_config import AppConfig
from utils.constants import CONFIG_FILE, CONFIG_DIR
from utils.logger import get_logger

# 获取本模块专用日志器（日志会带上模块名，方便定位）
logger = get_logger("config_manager")


class ConfigManager:
    """
    配置管理器：加载 / 保存 / 提供默认配置。

    使用方式：
        config_manager = ConfigManager()
        config = config_manager.load()      # 读取配置（不存在则用默认值）
        config.monitor.enable_voice = False # 修改配置
        config_manager.save(config)         # 保存到 JSON 文件
    """

    def __init__(self, config_path: Path = CONFIG_FILE):
        """
        初始化配置管理器。

        参数：
            config_path: 配置文件完整路径，默认使用 constants 中定义的路径。
        """
        self._config_path = config_path  # 记录配置文件路径

    def load(self) -> AppConfig:
        """
        从 JSON 文件加载配置。

        返回：
            AppConfig: 配置对象。文件不存在或损坏时返回默认配置。

        异常处理说明：
            - FileNotFoundError: 首次运行没有配置文件，属正常情况，返回默认值
            - json.JSONDecodeError: 文件内容不是合法 JSON（可能被手动改坏）
            - OSError: 磁盘读取失败等系统级错误
        """
        try:
            # 配置文件不存在：首次运行，创建默认配置并保存一份
            if not self._config_path.exists():
                logger.info("配置文件不存在，使用默认配置并创建初始文件")
                default_config = AppConfig()
                self.save(default_config)
                return default_config

            # 读取文件内容并解析为字典
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 字典 -> dataclass 对象
            return AppConfig.from_dict(data)

        except FileNotFoundError:
            # 极端情况：判断存在后文件又被删除，兜底返回默认配置
            logger.warning("配置文件读取时消失，使用默认配置")
            return AppConfig()
        except json.JSONDecodeError as e:
            # 文件内容损坏（比如手动编辑写错了格式）
            logger.error(f"配置文件格式错误，使用默认配置。错误详情：{e}")
            return AppConfig()
        except OSError as e:
            # 磁盘/权限等系统级读取错误
            logger.error(f"配置文件读取失败（系统错误），使用默认配置。错误详情：{e}")
            return AppConfig()

    def save(self, config: AppConfig) -> bool:
        """
        把配置对象保存为 JSON 文件。

        参数：
            config: 要保存的配置对象。

        返回：
            bool: 保存成功返回 True，失败返回 False。
        """
        try:
            # 确保配置目录存在（首次运行时目录可能还没创建）
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            # dataclass -> 字典 -> JSON 字符串，indent=2 让文件可读性更好
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(f"配置已保存到 {self._config_path}")
            return True

        except OSError as e:
            # 磁盘写满、权限不足等情况
            logger.error(f"配置保存失败：{e}")
            return False
        except TypeError as e:
            # 配置对象里混入了无法 JSON 序列化的类型（开发期 bug 防护）
            logger.error(f"配置序列化失败（存在不可序列化的字段）：{e}")
            return False
