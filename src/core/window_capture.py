"""
============================================================
模块：core/window_capture.py —— Windows 窗口截图引擎
------------------------------------------------------------
功能说明：
    基于 pywin32 的 BitBlt（GDI）+ PIL.Image 实现窗口级截图，
    支持截整个窗口、或按相对矩形截取窗口局部（例如无人机面板）。

设计契约：
    - 坐标空间：所有"矩形 ROI"使用"相对窗口客户区左上角"的坐标，
      这样即使窗口在桌面上移动，ROI 也不会失效。
    - 返回值统一为 PIL.Image.Image（RGB），便于 PIL 处理或转换为 QPixmap。
    - 失败统一返回 None，调用方按"无法截图"处理，不抛异常。

⚠️ 注意：仅限 Windows 系统（pywin32 / win32gui / win32ui / win32con）
============================================================
"""
from typing import Optional, Tuple, TYPE_CHECKING

from utils.logger import get_logger

logger = get_logger("window_capture")

# pywin32 仅在 Windows 可用（非 Windows 返回 None，让 UI 优雅降级）
try:
    import win32gui
    import win32ui
    import win32con
    from ctypes import windll
except ImportError:  # pragma: no cover - 非 Windows 平台
    win32gui = None  # type: ignore
    win32ui = None  # type: ignore
    win32con = None  # type: ignore
    windll = None  # type: ignore

# PIL 是 requirements.txt 里的硬依赖，但也做容错
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


# 给类型检查器看的 ROI 别名
if TYPE_CHECKING:
    Rect = Tuple[int, int, int, int]  # (left, top, right, bottom) 相对客户区


def _ensure_window_valid(hwnd: int) -> bool:
    """检查 hwnd 是否仍然是一个有效、可见的窗口句柄。"""
    if win32gui is None or hwnd == 0:
        return False
    try:
        return bool(win32gui.IsWindow(hwnd)) and bool(win32gui.IsWindowVisible(hwnd))
    except Exception:  # noqa: BLE001 —— 任何异常都视为无效
        return False


def capture_window(hwnd: int) -> Optional["Image.Image"]:
    """
    截取指定窗口的"客户区"（不含标题栏/边框的游戏画面区域）。

    参数：
        hwnd: 目标窗口句柄

    返回：
        PIL.Image（RGB 模式），截图失败返回 None。
    """
    if not _ensure_window_valid(hwnd):
        logger.debug(f"窗口句柄无效或不可见：hwnd={hwnd}")
        return None
    if win32gui is None or win32ui is None or Image is None:
        logger.debug("截图依赖缺失（pywin32 / PIL 未安装），跳过截图")
        return None

    try:
        # ---- 1. 拿到客户区尺寸 ----
        client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
        width = client_right - client_left
        height = client_bottom - client_top
        if width <= 0 or height <= 0:
            logger.debug(f"窗口客户区尺寸为 0：hwnd={hwnd}，可能最小化")
            return None

        # ---- 2. 通过窗口句柄创建设备上下文 ----
        hwnd_dc = win32gui.GetWindowDC(hwnd)  # 从系统拿到 DC（含释放责任）
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        # ---- 3. 创建位图承载截图 ----
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)

        # ---- 4. 把客户区像素 BitBlt 到我们的位图 ----
        # SRCCOPY = 0x00CC0020，win32con.SRCCOPY 等价
        save_dc.BitBlt(
            (0, 0),
            (width, height),
            mfc_dc,
            (0, 0),
            win32con.SRCCOPY if win32con is not None else 0x00CC0020,
        )

        # ---- 5. 把 win32 位图数据取出来转成 PIL.Image ----
        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits(True)  # True = 返回 bytes（BGRA 顺序）
        img = Image.frombuffer(
            "RGB",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_bits,
            "raw",
            "BGRX",
            0,
            1,  # 1 = 自上而下（屏幕坐标顺序）
        )

        # ---- 6. 释放 GDI 资源（顺序重要：先删 DC，再释放句柄）----
        mfc_dc.DeleteDC()
        save_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        # win32 位图对象也需要手动释放句柄，避免 GDI 泄漏
        try:
            bmp_handle = bmp.GetHandle()
            if windll is not None:
                windll.gdi32.DeleteObject(bmp_handle)
        except Exception:  # noqa: BLE001
            pass

        return img

    except Exception as e:  # noqa: BLE001
        logger.warning(f"窗口截图失败：hwnd={hwnd}，err={e}")
        return None


def capture_window_region(hwnd: int, rect: "Rect") -> Optional["Image.Image"]:
    """
    截取指定窗口的客户区中一个子矩形。

    参数：
        hwnd: 目标窗口句柄
        rect: (left, top, right, bottom)，相对客户区左上角；
              越界部分会被安全裁切到客户区范围内。

    返回：
        PIL.Image（RGB），失败或 rect 为空则返回 None。
    """
    if not _ensure_window_valid(hwnd):
        return None
    if win32gui is None:
        return None

    img = capture_window(hwnd)
    if img is None:
        return None

    # 拿到客户区真实尺寸并安全夹取，避免越界裁剪
    img_w, img_h = img.size
    left, top, right, bottom = rect
    left = max(0, min(left, img_w))
    top = max(0, min(top, img_h))
    right = max(0, min(right, img_w))
    bottom = max(0, min(bottom, img_h))

    if right <= left or bottom <= top:
        logger.debug(f"裁剪矩形为空：rect={rect}，窗口尺寸={img_w}x{img_h}")
        return None

    return img.crop((left, top, right, bottom))
