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
from typing import Dict, List, Optional

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
        self._name_to_id: Dict[str, int] = {}  # 反向映射：{星系名: ID}

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
        name_to_id: Dict[str, int] = {}
        name_conflicts: Dict[str, List[int]] = {}

        # 添加节点：每个星系一个节点（带名称属性，方便展示）
        for system_id, system_name in self._sde_loader.solar_systems.items():
            graph.add_node(system_id, name=system_name)

            # 构建名称 -> ID 反向映射，检测同名冲突
            if system_name in name_to_id:
                # 同名冲突：记录下来，保留先遇到的那个 ID
                if system_name not in name_conflicts:
                    name_conflicts[system_name] = [name_to_id[system_name]]
                name_conflicts[system_name].append(system_id)
            else:
                name_to_id[system_name] = system_id

        # 记录同名冲突日志
        if name_conflicts:
            conflict_count = len(name_conflicts)
            total_dup = sum(len(ids) - 1 for ids in name_conflicts.values())
            logger.warning(
                f"检测到 {conflict_count} 个同名星系（共 {total_dup} 个重复项），"
                f"同名时仅保留首个 ID："
                f"{list(name_conflicts.keys())[:5]}{'...' if conflict_count > 5 else ''}"
            )

        # 添加边：每条星门连接一条边（权重为 1，代表 1 跳）
        for src, dst in self._sde_loader.stargate_links:
            graph.add_edge(src, dst, weight=1)

        self._graph = graph
        self._name_to_id = name_to_id
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

    def get_system_id(self, name: str) -> Optional[int]:
        """
        通过星系名查询星系 ID（不区分大小写）。

        参数：
            name: 星系名称

        返回：
            Optional[int]: 星系 ID；未找到返回 None。
        """
        if not self._name_to_id:
            logger.warning("名称映射尚未构建，请先调用 build_graph()")
            return None

        # 先尝试精确匹配
        if name in self._name_to_id:
            return self._name_to_id[name]

        # 再尝试不区分大小写匹配
        name_lower = name.lower()
        for sys_name, sys_id in self._name_to_id.items():
            if sys_name.lower() == name_lower:
                return sys_id
        return None

    def get_system_name(self, system_id: int) -> Optional[str]:
        """
        通过星系 ID 查询星系名称。

        参数：
            system_id: 星系 ID

        返回：
            Optional[str]: 星系名称；未找到返回 None。
        """
        if self._graph is None:
            logger.warning("星图尚未构建，请先调用 build_graph()")
            return None

        if system_id not in self._graph:
            return None

        return self._graph.nodes[system_id].get("name")

    def calculate_jumps_by_name(self, from_name: str, to_name: str) -> int:
        """
        通过星系名称计算最短跳数。

        参数：
            from_name: 起点星系名称
            to_name:   终点星系名称

        返回：
            int: 最短跳数；任一方不存在或计算失败返回 -1。
        """
        from_id = self.get_system_id(from_name)
        if from_id is None:
            logger.warning(f"起点星系不存在：{from_name}")
            return -1

        to_id = self.get_system_id(to_name)
        if to_id is None:
            logger.warning(f"终点星系不存在：{to_name}")
            return -1

        return self.calculate_jumps(from_id, to_id)

    def extract_systems_from_text(self, content: str) -> List[str]:
        """
        从一段文本中扫描所有可能的星系名。

        匹配规则：
            - 基于 _name_to_id 的键做不区分大小写匹配
            - 返回原文中的大小写形式（即匹配到的字典键的大小写）
            - 按在文本中首次出现的顺序返回，不重复

        参数：
            content: 待扫描的文本

        返回：
            List[str]: 匹配到的星系名称列表（原文大小写形式）。
        """
        if not self._name_to_id:
            logger.warning("名称映射尚未构建，请先调用 build_graph()")
            return []

        if not content:
            return []

        # 构建小写名 -> 原文大小写名 的映射
        lower_to_original: Dict[str, str] = {}
        for sys_name in self._name_to_id.keys():
            lower_to_original[sys_name.lower()] = sys_name

        # 按星系名长度从长到短排序，避免短名先匹配（比如 "Jita" 被 "Jita IV" 之类的干扰）
        sorted_names = sorted(
            lower_to_original.keys(),
            key=lambda x: len(x),
            reverse=True,
        )

        content_lower = content.lower()
        result: List[str] = []
        result_set: set = set()
        # 记录已经匹配过的位置区间，避免重复提取
        matched_spans: List[tuple] = []

        # 先找出所有匹配及其位置
        all_matches: List[tuple] = []  # (start, end, original_name)
        for lower_name in sorted_names:
            original_name = lower_to_original[lower_name]
            start = 0
            while True:
                pos = content_lower.find(lower_name, start)
                if pos == -1:
                    break
                end = pos + len(lower_name)
                all_matches.append((pos, end, original_name))
                start = end

        # 按起始位置排序，优先保留长匹配（先排长名，同位置时留长的）
        all_matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

        for start, end, original_name in all_matches:
            # 检查这个区间是否与已匹配区间有重叠
            overlap = False
            for s, e in matched_spans:
                if not (end <= s or start >= e):
                    overlap = True
                    break
            if overlap:
                continue
            if original_name not in result_set:
                result.append(original_name)
                result_set.add(original_name)
                matched_spans.append((start, end))

        return result
