"""
============================================================
模块：core/jump_calculator.py —— 跳数计算器
------------------------------------------------------------
功能说明：
    基于本地 SDE 星图数据，用 networkx 构建"星系无向图"，
    计算任意两个星系之间的最短跳数（最短路经过的星门数）。

    通俗解释：
      把每个星系想象成"地铁站"，星门就是"地铁线路"，
      跳数计算就是查"从 A 站到 B 站最少坐几站"。

    强制约束：本层为纯逻辑，不依赖 PyQt5。
============================================================
"""
from typing import Optional

import networkx as nx

from data.sde_loader import SdeLoader
from utils.logger import get_logger

logger = get_logger("jump_calculator")


class JumpCalculator:
    """
    跳数计算器：构建星图 + 查询最短跳数。
    """

    def __init__(self, sde_loader: SdeLoader):
        """
        参数：
            sde_loader: 已加载好数据的 SDE 加载器实例。
        """
        self._sde_loader = sde_loader
        self._graph: Optional[nx.Graph] = None  # networkx 无向图

    def build_graph(self) -> bool:
        """
        根据 SDE 数据构建星图。

        返回：
            bool: 构建成功返回 True；数据为空返回 False。
        """
        # 确保 SDE 数据已加载
        if not self._sde_loader.load():
            logger.error("SDE 数据加载失败，无法构建星图")
            return False

        graph = nx.Graph()  # 无向图：星门是双向的

        # 添加节点：每个星系一个节点（带名称属性，方便展示）
        for system_id, system_name in self._sde_loader.solar_systems.items():
            graph.add_node(system_id, name=system_name)

        # 添加边：每条星门连接一条边（权重为 1，代表 1 跳）
        for src, dst in self._sde_loader.stargate_links:
            graph.add_edge(src, dst, weight=1)

        self._graph = graph
        logger.info(
            f"星图构建完成：{graph.number_of_nodes()} 个星系，"
            f"{graph.number_of_edges()} 条星门"
        )
        return True

    def calculate_jumps(self, from_id: int, to_id: int) -> int:
        """
        计算两个星系之间的最短跳数。

        参数：
            from_id: 起点星系 ID
            to_id:   终点星系 ID

        返回：
            int: 最短跳数；无法计算时返回 -1。
        """
        # 星图还没构建好
        if self._graph is None:
            logger.error("星图尚未构建，请先调用 build_graph()")
            return -1

        # 起点或终点不在星图中（ID 写错或数据缺失）
        if from_id not in self._graph or to_id not in self._graph:
            logger.warning(f"星系 ID 不存在：{from_id} -> {to_id}")
            return -1

        try:
            # networkx 最短路径长度 = 经过的边数 = 跳数
            return nx.shortest_path_length(self._graph, from_id, to_id)
        except nx.NetworkXNoPath:
            # 理论上 EVE 宇宙是连通的，这里做防御性处理
            logger.warning(f"{from_id} 到 {to_id} 不存在通路")
            return -1
        except (ValueError, nx.NodeNotFound) as e:
            logger.error(f"跳数计算异常：{e}")
            return -1
