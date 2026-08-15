"""
============================================================
模块：data/sde_loader.py —— SDE 星图数据加载器
------------------------------------------------------------
功能说明：
    SDE（Static Data Export）是 CCP 官方导出的 EVE 静态数据。
    本模块负责把星图数据（星系、星门连接关系）加载到内存，
    供 core/jump_calculator.py 构建 networkx 图使用。

    数据格式策略：
    - 首次从 YAML 源数据解析（速度慢）
    - 解析结果缓存为 Pickle 文件（下次秒开）
    小白理解：第一次把"大字典书"翻译成 Python 能直接读的形式，
              之后直接读翻译好的版本，省时间。
============================================================
"""
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

from utils.constants import SDE_DIR
from utils.logger import get_logger

logger = get_logger("sde_loader")


class SdeLoader:
    """
    SDE 数据加载器。

    对外提供两个核心数据：
    - solar_systems: 星系字典 {星系ID: 星系名称}
    - stargate_links: 星门连接列表 [(星系ID_A, 星系ID_B), ...]
    """

    def __init__(self, sde_dir: Path = SDE_DIR):
        """
        初始化加载器。

        参数：
            sde_dir: SDE 数据文件所在目录。
        """
        self._sde_dir = sde_dir
        # 内存缓存：加载过一次就不用再读磁盘
        self._solar_systems: Dict[int, str] = {}
        self._stargate_links: List[Tuple[int, int]] = []
        self._loaded = False  # 标记是否已加载

    def load(self) -> bool:
        """
        加载星图数据（优先读 Pickle 缓存，没有则解析 YAML）。

        返回：
            bool: 加载成功返回 True，失败返回 False。
        """
        # 已经加载过就直接返回，避免重复 IO
        if self._loaded:
            return True

        cache_file = self._sde_dir / "stargraph.pickle"

        # ---- 第一步：尝试读 Pickle 缓存（快） ----
        try:
            if cache_file.exists():
                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                self._solar_systems = cached["solar_systems"]
                self._stargate_links = cached["stargate_links"]
                self._loaded = True
                logger.info(
                    f"SDE 缓存加载成功：{len(self._solar_systems)} 个星系，"
                    f"{len(self._stargate_links)} 条星门连接"
                )
                return True
        except (pickle.PickleError, OSError, KeyError) as e:
            # 缓存文件损坏时删除重建，不影响主流程
            logger.warning(f"SDE 缓存读取失败，将重新解析源数据：{e}")

        # ---- 第二步：解析 YAML 源数据（慢，首次运行才走这里） ----
        try:
            self._parse_yaml_source()
            self._save_cache(cache_file)
            self._loaded = True
            return True
        except FileNotFoundError:
            logger.error(
                f"未找到 SDE 数据文件，请把星图数据放到 {self._sde_dir} 目录"
            )
            return False
        except OSError as e:
            logger.error(f"SDE 数据读取失败：{e}")
            return False

    def _parse_yaml_source(self) -> None:
        """
        解析 YAML 格式的 SDE 源数据。

        说明：
            骨架阶段仅搭好流程框架，实际字段映射
            待拿到真实 SDE 文件后按结构补全。
        """
        # TODO: 拿到真实 SDE 文件后，用 yaml.safe_load 解析
        #       solar_systems 与 stargate_links 字段
        logger.info("SDE YAML 解析为占位实现，等待接入真实数据文件")
        self._solar_systems = {}
        self._stargate_links = []

    def _save_cache(self, cache_file: Path) -> None:
        """把解析结果写入 Pickle 缓存文件。"""
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "wb") as f:
                pickle.dump(
                    {
                        "solar_systems": self._solar_systems,
                        "stargate_links": self._stargate_links,
                    },
                    f,
                )
            logger.info(f"SDE 缓存已生成：{cache_file}")
        except OSError as e:
            # 缓存写失败不影响本次使用，只记录日志
            logger.warning(f"SDE 缓存写入失败（不影响本次运行）：{e}")

    @property
    def solar_systems(self) -> Dict[int, str]:
        """只读属性：星系字典 {星系ID: 星系名称}。"""
        return self._solar_systems

    @property
    def stargate_links(self) -> List[Tuple[int, int]]:
        """只读属性：星门连接列表。"""
        return self._stargate_links
