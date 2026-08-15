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
    import win32process
except ImportError:
    win32gui = None
    win32process = None
    logger.error("pywin32 未安装或非 Windows 系统，窗口枚举功能不可用")


class WindowInfo(NamedTuple):
    """
    窗口信息结构。

    字段：
        hwnd: 窗口句柄（Windows 内部唯一编号，截图时用）
        title: 窗口标题（EVE 窗口标题通常含角色名）
        pid: 进程ID（通过窗口句柄获取的对应进程PID，pywin32不可用时为0）
        character_name: 角色名（从标题"EVE - 角色名"提取，不含分隔符则为空字符串）
    """
    hwnd: int
    title: str
    pid: int = 0
    character_name: str = ""


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

        def _extract_character_name(title: str) -> str:
            """
            从窗口标题中提取角色名。

            标题格式兼容：
                - "EVE - 角色名"          → 提取 "角色名"
                - "EVE Online - 角色名"   → 先去除 "EVE Online" 再提取 "角色名"
                - 不含 "- " 的标题         → 返回空字符串
            """
            # 先去除 "EVE Online" 前缀（兼容写法）
            processed = title.replace("EVE Online", "EVE", 1)
            # 在处理后的标题中查找 "- " 分隔符
            sep_index = processed.find("- ")
            if sep_index != -1:
                # 分隔符之后的部分即为角色名
                return processed[sep_index + 2:].strip()
            # 未找到分隔符，返回空字符串
            return ""

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
                    # 获取进程ID：win32process 不可用时 pid 保持为 0
                    pid = 0
                    if win32process is not None:
                        try:
                            # GetWindowThreadProcessId 返回 (线程ID, 进程ID)，取第二个值
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        except Exception as e:  # noqa: BLE001
                            logger.debug(f"获取窗口 {hwnd} 的PID失败：{e}")

                    # 从标题提取角色名
                    character_name = _extract_character_name(title)

                    results.append(WindowInfo(
                        hwnd=hwnd,
                        title=title,
                        pid=pid,
                        character_name=character_name
                    ))

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

    def scan_once(self) -> List[WindowInfo]:
        """
        便捷方法：执行一次窗口扫描，等价于调用 enumerate_eve_windows()。

        此方法作为更直观的对外别名，保留 enumerate_eve_windows() 作为底层实现。

        返回：
            List[WindowInfo]: 匹配到的 EVE 窗口列表
        """
        return self.enumerate_eve_windows()
