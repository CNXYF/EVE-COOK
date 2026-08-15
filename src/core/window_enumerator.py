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
from typing import List, NamedTuple, Tuple

from utils.constants import (
    EVE_WINDOW_CLASSES,
    EVE_WINDOW_TITLE_KEYWORD,
    EVE_WINDOW_TITLE_ALTERNATIVES,
)
from utils.logger import get_logger

logger = get_logger("window_enumerator")

# 非游戏窗口类名：仅靠"标题含 EVE"命中时，只要类名属于这里就直接排除（避免把浏览器/资源管理器/启动器页签误算进去）
NON_GAME_WINDOW_CLASSES: Tuple[str, ...] = (
    "MozillaWindowClass",       # Firefox
    "Chrome_WidgetWin_1",       # Chrome / Chromium 内核（如 EVE 启动器、Edge、KOOK…）
    "Chrome_WidgetWin_0",       # Chrome 早期内核
    "CabinetWClass",            # Windows 资源管理器
    "ExplorerWClass",           # Windows 资源管理器变体
    "ApplicationFrameWindow",   # UWP 容器
    "FLUTTER_RUNNER_WIN32_WINDOW",  # Flutter
    "Qt6101QWindowToolSaveBits",    # Qt 预览窗口（如用户本机 EVE-APM Preview）
    "Qt5151QWindowIcon",        # 通用 Qt5 应用窗口
)

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
        枚举所有 EVE 客户端窗口。

        匹配策略（任一命中即算，双保险）：
          A. 窗口类名属于 EVE_WINDOW_CLASSES（默认 "trinityWindow" / "EVE"）
          B. 窗口标题包含 EVE_WINDOW_TITLE_KEYWORD（默认 "EVE"）

        返回：
            List[WindowInfo]: 匹配到的窗口列表（多开时会有多条）。
        """
        # pywin32 不可用时返回空列表，调用方按"未找到窗口"处理
        if win32gui is None:
            return []

        results: List[WindowInfo] = []

        def _matches_title(title: str) -> bool:
            """标题匹配：至少命中一个关键字（兼容 EVE Online/EVE 两种格式）。"""
            if not title:
                return False
            for kw in EVE_WINDOW_TITLE_ALTERNATIVES:
                if kw in title:
                    return True
            # 兜底：主关键字也判断一次（保证常量扩展时不遗漏）
            return bool(EVE_WINDOW_TITLE_KEYWORD and EVE_WINDOW_TITLE_KEYWORD in title)

        def _matches_class(cls: str) -> bool:
            """类名匹配：属于已知 EVE 窗口类名集合之一。"""
            if not cls:
                return False
            return cls in EVE_WINDOW_CLASSES

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
            # 未找到分隔符，再尝试只按 "-" 匹配（应对可能的空格缺失）
            sep_index2 = processed.find("-")
            if sep_index2 != -1:
                return processed[sep_index2 + 1:].strip()
            return ""

        def _enum_callback(hwnd: int, _extra) -> bool:
            """
            EnumWindows 对每个顶层窗口调用一次此函数。

            ⚠️ 注意：此回调由 C 层调用，内部禁止抛出任何异常，
            所有异常必须就地捕获，否则枚举过程会直接崩溃。
            """
            try:
                # 跳过不可见窗口
                if not win32gui.IsWindowVisible(hwnd):
                    return True

                title = win32gui.GetWindowText(hwnd)
                try:
                    cls = win32gui.GetClassName(hwnd)
                except Exception:
                    cls = ""

                # 双保险：类名 或 标题 任一命中就算 EVE 窗口
                class_hit = _matches_class(cls)
                title_hit = _matches_title(title)
                if not (class_hit or title_hit):
                    return True

                # 1) 类名已经命中：基本就是 trinityWindow，直接放行（最可靠的判断）
                # 2) 仅靠标题命中：需要再做严格过滤，避免把浏览器/资源管理器/工具窗口混进来
                if not class_hit:
                    # (a) 排除"明确不是游戏窗口"的类名（Firefox / Chrome / Explorer / Qt 预览 等）
                    if cls in NON_GAME_WINDOW_CLASSES:
                        logger.debug(f"跳过类名黑名单窗口：hwnd={hwnd} class={cls} title={title}")
                        return True

                    # (b) 关键词过滤：preview / 启动器 / launcher / installer 等
                    title_lower = title.lower()
                    exclude_terms = ("preview", "启动器", "launcher", "installer", "setup", "更新", "update", "-apm")
                    if any(t in title_lower for t in exclude_terms):
                        logger.debug(f"跳过疑似非游戏窗口（关键词命中）：hwnd={hwnd} class={cls} title={title}")
                        return True

                    # (c) 标题格式校验：EVE 游戏主窗口标题是 "EVE - 角色名" 或 "EVE Online - 角色名"
                    #     ——不满足此模式的一律排除（此条可以把 "EVE角色配置文件…"、"EVE-COOK - …" 之类误报全部过滤掉）
                    stripped = title.lstrip()
                    prefix_match = False
                    for prefix in ("EVE - ", "EVE Online - "):
                        if stripped.startswith(prefix):
                            prefix_match = True
                            break
                    if not prefix_match:
                        logger.debug(f"跳过标题格式不匹配窗口：hwnd={hwnd} class={cls} title={title}")
                        return True

                # 获取进程ID
                pid = 0
                if win32process is not None:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"获取窗口 {hwnd} 的PID失败：{e}")

                character_name = _extract_character_name(title)
                results.append(WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    pid=pid,
                    character_name=character_name
                ))

            except Exception as e:  # noqa: BLE001 —— 回调禁止抛异常
                logger.debug(f"枚举窗口 {hwnd} 时出错（已跳过）：{e}")

            return True  # 始终返回 True，继续枚举剩余窗口

        try:
            win32gui.EnumWindows(_enum_callback, None)
        except Exception as e:  # noqa: BLE001
            logger.error(f"窗口枚举失败：{e}")

        logger.info(f"找到 {len(results)} 个 EVE 窗口（类命中/EVE_WINDOW_CLASSES 或 标题含 '{EVE_WINDOW_TITLE_KEYWORD}'）")
        return results

    def scan_once(self) -> List[WindowInfo]:
        """
        便捷方法：执行一次窗口扫描，等价于调用 enumerate_eve_windows()。

        返回：
            List[WindowInfo]: 匹配到的 EVE 窗口列表
        """
        return self.enumerate_eve_windows()

    def find_by_character_name(self, character_name: str, case_sensitive: bool = False) -> List[WindowInfo]:
        """
        按角色名从当前扫描结果中筛选窗口。

        参数：
            character_name: 角色名（允许模糊包含）
            case_sensitive: 是否区分大小写
        返回：
            List[WindowInfo]: 所有包含该角色名的窗口
        """
        all_windows = self.enumerate_eve_windows()
        if not character_name:
            return all_windows
        target = character_name if case_sensitive else character_name.lower()
        result: List[WindowInfo] = []
        for w in all_windows:
            name = w.character_name if case_sensitive else w.character_name.lower()
            if target in name:
                result.append(w)
        return result
