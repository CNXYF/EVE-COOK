"""
============================================================
模块：core/window_enumerator.py —— Windows 窗口枚举器
------------------------------------------------------------
功能说明：
    封装 pywin32 的窗口枚举 API，找出所有 EVE Online 客户端窗口。
    后续无人机监控会用到窗口句柄进行截图。

    ⚠️ 注意：仅限 Windows 系统
    （pywin32 的 win32gui 只能在 Windows 上运行）

    强制约束：回调函数禁止抛异常——
    EnumWindows 是 C 层回调，异常穿透会导致整个枚举崩溃。
============================================================
"""
from typing import List, NamedTuple

from utils.constants import EVE_WINDOW_TITLE_KEYWORD
from utils.logger import get_logger

logger = get_logger("window_enumerator")

# ⚠️ 注意：仅限 Windows 系统
# pywin32 只在 Windows 可导入，用 try 包裹给出友好报错
try:
    import win32gui
except ImportError:
    win32gui = None
    logger.error("pywin32 未安装或非 Windows 系统，窗口枚举功能不可用")


class WindowInfo(NamedTuple):
    """
    窗口信息结构。

    字段：
        hwnd: 窗口句柄（Windows 内部唯一编号，截图时用）
        title: 窗口标题（EVE 窗口标题通常含角色名）
    """
    hwnd: int
    title: str


class WindowEnumerator:
    """
    窗口枚举器：列出所有可见的 EVE 客户端窗口。
    """

    def enumerate_eve_windows(self) -> List[WindowInfo]:
        """
        枚举所有标题包含 EVE 关键字的可见窗口。

        返回：
            List[WindowInfo]: 匹配到的窗口列表（可能多开，所以是列表）。
        """
        # pywin32 不可用时返回空列表，调用方按"未找到窗口"处理
        if win32gui is None:
            return []

        results: List[WindowInfo] = []

        def _enum_callback(hwnd: int, _extra) -> bool:
            """
            EnumWindows 对每个顶层窗口调用一次此函数。

            ⚠️ 注意：此回调由 C 层调用，内部禁止抛出任何异常，
            所有异常必须就地捕获，否则枚举过程会直接崩溃。

            参数：
                hwnd: 当前窗口句柄
                _extra: EnumWindows 透传的附加参数（这里用不到）
            返回：
                bool: 返回 True 表示继续枚举下一个窗口
            """
            try:
                # 跳过不可见窗口（最小化的 EVE 也保留，IsWindowVisible 会过滤）
                if not win32gui.IsWindowVisible(hwnd):
                    return True

                title = win32gui.GetWindowText(hwnd)
                # 标题包含 EVE 关键字即认为是 EVE 客户端窗口
                if title and EVE_WINDOW_TITLE_KEYWORD in title:
                    results.append(WindowInfo(hwnd=hwnd, title=title))

            except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
                # 某些窗口（如权限受限的系统窗口）读取标题会失败，跳过即可
                logger.debug(f"枚举窗口 {hwnd} 时出错（已跳过）：{e}")

            return True  # 始终返回 True，继续枚举剩余窗口

        try:
            # EnumWindows：让 Windows 把所有顶层窗口逐个交给回调函数
            win32gui.EnumWindows(_enum_callback, None)
        except Exception as e:  # noqa: BLE001 —— 兜底保护
            logger.error(f"窗口枚举失败：{e}")

        logger.info(f"找到 {len(results)} 个 EVE 窗口")
        return results
