"""
============================================================
模块：ui/widgets/preview_widget.py —— 预览 + 无人机区域框选控件
------------------------------------------------------------
功能说明：
    自绘控件，解决两个用户痛点：
      (a) 看不到任何预览 —— 截选中的 EVE 客户区图并缩放显示
      (b) 没法框选无人机监控区域 —— 鼠标在预览图上拖一个矩形，
          自动把矩形"从预览缩放坐标"换算回"真实窗口客户区坐标"

对外 API：
    set_windows(List[WindowInfo])  —— 填充"目标窗口下拉"（选项含角色名+PID+句柄）
    set_target_hwnd(int)           —— 编程方式选中某个目标窗口
    refresh_preview()              —— 立即对选中目标窗口截图并刷新
    clear_roi()                    —— 清除当前 ROI
    current_hwnd() -> int          —— 当前选中的目标句柄（未选中为 0）
    current_roi() -> tuple or None —— 当前 ROI，相对真实窗口客户区：(L, T, R, B)

对外信号：
    sig_target_changed(int)              —— 用户切换了目标窗口（新 hwnd）
    sig_roi_changed(tuple or None)       —— 用户画了/清除了 ROI（(L,T,R,B) 或 None）
    sig_preview_failed(str)              —— 截图失败，附带描述，用于 UI 日志提示
============================================================
"""
import io
from typing import List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.window_capture import capture_window
from core.window_enumerator import WindowInfo
from utils.logger import get_logger

logger = get_logger("preview_widget")

# ROI 矩形（相对真实窗口客户区）的类型别名
RoiRect = Tuple[int, int, int, int]


class PreviewWidget(QWidget):
    """预览 + 无人机 ROI 框选自绘控件。"""

    sig_target_changed = pyqtSignal(int)              # 目标句柄变更（hwnd / 0）
    sig_roi_changed = pyqtSignal(object)              # ROI 变更：(L,T,R,B) 或 None
    sig_preview_failed = pyqtSignal(str)              # 截图失败描述

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # ---- 内部状态 ----
        self._windows: List[WindowInfo] = []
        self._target_hwnd: int = 0              # 真实目标句柄（0 = 未选中）
        self._full_pixmap: Optional[QPixmap] = None  # 真实窗口截图（原始尺寸）
        self._display_rect: QRect = QRect()     # pixmap 在控件里的显示矩形（用于坐标换算）
        self._roi_window: Optional[RoiRect] = None  # ROI，真实窗口客户区坐标系 (L,T,R,B)

        # ---- 鼠标拖拽相关 ----
        self._drag_start: Optional[QPoint] = None  # 鼠标按下点（控件坐标系）
        self._drag_end: Optional[QPoint] = None    # 鼠标当前点（控件坐标系）
        self._dragging: bool = False

        self._build_ui()

    # ============================================================
    #  界面构建
    # ============================================================
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # ---- 顶部工具条：窗口下拉 + 刷新 + 清除ROI ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.combo_windows = QComboBox(self)
        self.combo_windows.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_windows.setObjectName("previewWindowCombo")
        self.combo_windows.addItem("（未选中窗口）", userData=0)
        self.combo_windows.currentIndexChanged.connect(self._on_combo_changed)
        toolbar.addWidget(self.combo_windows, stretch=1)

        self.btn_refresh = QPushButton("刷新预览", self)
        self.btn_refresh.setObjectName("previewRefreshBtn")
        self.btn_refresh.clicked.connect(self.refresh_preview)
        toolbar.addWidget(self.btn_refresh)

        self.btn_clear_roi = QPushButton("清除区域", self)
        self.btn_clear_roi.setObjectName("previewClearRoiBtn")
        self.btn_clear_roi.clicked.connect(self.clear_roi)
        toolbar.addWidget(self.btn_clear_roi)

        outer.addLayout(toolbar)

        # ---- 中部：自绘预览画布 ----
        # 直接用 QWidget + paintEvent 实现（避免套一层 QLabel 导致坐标换算更绕）
        self.canvas = _PreviewCanvas(self)
        self.canvas.setMinimumSize(480, 300)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 把画布内部事件转成外部可见的信号/状态
        self.canvas.sig_drag_started.connect(self._on_drag_started)
        self.canvas.sig_drag_moved.connect(self._on_drag_moved)
        self.canvas.sig_drag_finished.connect(self._on_drag_finished)
        outer.addWidget(self.canvas, stretch=1)

        # ---- 底部：状态标签（坐标 / 尺寸） ----
        self.lbl_status = QLabel("暂无预览。请先在上方选择目标窗口，然后点『刷新预览』。", self)
        self.lbl_status.setObjectName("previewStatusLabel")
        self.lbl_status.setWordWrap(True)
        outer.addWidget(self.lbl_status)

    # ============================================================
    #  对外 API
    # ============================================================
    def set_windows(self, windows: List[WindowInfo]) -> None:
        """把最新枚举的 EVE 窗口填充到下拉列表，保留当前选中项。"""
        self._windows = list(windows)
        current_hwnd = self._target_hwnd

        self.combo_windows.blockSignals(True)
        try:
            self.combo_windows.clear()
            self.combo_windows.addItem("（未选中窗口）", userData=0)
            for w in self._windows:
                label = f"{w.character_name or w.title}  (PID {w.pid}, 句柄 0x{w.hwnd:X})"
                self.combo_windows.addItem(label, userData=w.hwnd)
            # 尝试恢复之前选中的 hwnd
            idx = self.combo_windows.findData(current_hwnd)
            if idx >= 0:
                self.combo_windows.setCurrentIndex(idx)
            else:
                self.combo_windows.setCurrentIndex(0)
                self._target_hwnd = 0
        finally:
            self.combo_windows.blockSignals(False)

    def set_target_hwnd(self, hwnd: int) -> None:
        """编程方式选中某个目标窗口；不存在则回到『未选中』。"""
        idx = self.combo_windows.findData(hwnd) if hwnd else -1
        if idx >= 0:
            self.combo_windows.setCurrentIndex(idx)
        else:
            if self.combo_windows.currentIndex() != 0:
                self.combo_windows.setCurrentIndex(0)
            else:
                self._target_hwnd = 0
                self._refresh_display_state_label()

    def current_hwnd(self) -> int:
        """当前选中的目标窗口句柄（0 表示未选中）。"""
        return self._target_hwnd

    def current_roi(self) -> Optional[RoiRect]:
        """
        当前 ROI 矩形。

        返回：
            (L, T, R, B)，坐标是"真实窗口客户区"像素级坐标系；
            若用户尚未画过 ROI 或已清除，则返回 None。
        """
        return self._roi_window

    def refresh_preview(self) -> None:
        """立即截图并刷新画布。"""
        if self._target_hwnd == 0:
            self._set_status("请先选择一个目标窗口，再刷新预览。", warn=True)
            self._full_pixmap = None
            self.canvas.set_content(None)
            self._refresh_display_state_label()
            self.sig_preview_failed.emit("未选中目标窗口")
            return

        pil_img = capture_window(self._target_hwnd)
        if pil_img is None:
            msg = f"目标窗口 0x{self._target_hwnd:X} 截图失败（可能窗口最小化或权限不足）"
            self._set_status(msg, warn=True)
            self._full_pixmap = None
            self.canvas.set_content(None)
            self._refresh_display_state_label()
            self.sig_preview_failed.emit(msg)
            return

        # PIL -> QPixmap
        qim = self._pil_to_qimage(pil_img)
        self._full_pixmap = QPixmap.fromImage(qim)

        self.canvas.set_content(self._full_pixmap)
        self.canvas.set_roi(self._roi_window)  # 把旧 ROI 重绘上去（如果有的话）
        self._refresh_display_state_label()

    def clear_roi(self) -> None:
        """清除当前 ROI（对外发射 sig_roi_changed(None)）。"""
        self._roi_window = None
        self._drag_start = None
        self._drag_end = None
        self._dragging = False
        self.canvas.set_roi(None)
        self.canvas.set_drag_rect(None)
        self.sig_roi_changed.emit(None)
        self._refresh_display_state_label()

    # ============================================================
    #  内部槽：下拉切换 / 鼠标拖拽三段事件
    # ============================================================
    def _on_combo_changed(self, _idx: int) -> None:
        data = self.combo_windows.currentData()
        try:
            new_hwnd = int(data) if data is not None else 0
        except (TypeError, ValueError):
            new_hwnd = 0
        if new_hwnd == self._target_hwnd:
            return
        self._target_hwnd = new_hwnd
        # 切换目标后自动截图一次，让预览立刻生效
        self.refresh_preview()
        self.sig_target_changed.emit(self._target_hwnd)

    def _on_drag_started(self, widget_pt: QPoint) -> None:
        if self._full_pixmap is None or self._full_pixmap.isNull():
            return  # 没有图就不允许画
        self._dragging = True
        self._drag_start = widget_pt
        self._drag_end = widget_pt
        self.canvas.set_drag_rect(self._widget_rect_from_points(self._drag_start, self._drag_end))

    def _on_drag_moved(self, widget_pt: QPoint) -> None:
        if not self._dragging or self._drag_start is None:
            return
        self._drag_end = widget_pt
        self.canvas.set_drag_rect(self._widget_rect_from_points(self._drag_start, self._drag_end))

    def _on_drag_finished(self, widget_pt: QPoint) -> None:
        if not self._dragging or self._drag_start is None:
            return
        self._drag_end = widget_pt
        self._dragging = False
        widget_rect = self._widget_rect_from_points(self._drag_start, self._drag_end)
        self.canvas.set_drag_rect(None)

        # 太小的拖拽视为无效（防止鼠标抖动误画）
        if widget_rect is None or widget_rect.width() < 6 or widget_rect.height() < 6:
            self.canvas.set_roi(self._roi_window)  # 还原上一次有效 ROI
            return

        # 把控件坐标系的矩形 -> 真实窗口客户区的矩形
        roi = self._widget_rect_to_window_rect(widget_rect)
        if roi is None:
            self.canvas.set_roi(self._roi_window)
            return

        self._roi_window = roi
        self.canvas.set_roi(roi)
        self.sig_roi_changed.emit(roi)
        self._refresh_display_state_label()

    # ============================================================
    #  坐标换算工具（控件像素 <-> 真实窗口客户区像素）
    # ============================================================
    def _widget_rect_from_points(self, a: QPoint, b: QPoint) -> Optional[QRect]:
        x1, y1 = a.x(), a.y()
        x2, y2 = b.x(), b.y()
        left, right = (x1, x2) if x1 <= x2 else (x2, x1)
        top, bottom = (y1, y2) if y1 <= y2 else (y2, y1)

        # 把拖拽严格约束到"真实图像显示区域"内部，防止画到了黑边
        dr = self.canvas.display_rect()
        if dr is not None and dr.isValid():
            left = max(left, dr.left())
            right = min(right, dr.right())
            top = max(top, dr.top())
            bottom = min(bottom, dr.bottom())

        if right <= left or bottom <= top:
            return None
        return QRect(left, top, right - left, bottom - top)

    def _widget_rect_to_window_rect(self, widget_rect: QRect) -> Optional[RoiRect]:
        """把控件坐标矩形换算成真实窗口客户区坐标矩形。"""
        if self._full_pixmap is None or self._full_pixmap.isNull():
            return None
        dr = self.canvas.display_rect()
        if dr is None or not dr.isValid() or dr.width() <= 0 or dr.height() <= 0:
            return None

        # 先把 widget 坐标换算成"缩放后显示图片内部"的坐标
        img_disp_x = widget_rect.left() - dr.left()
        img_disp_y = widget_rect.top() - dr.top()
        img_disp_w = widget_rect.width()
        img_disp_h = widget_rect.height()

        # 缩放到"原始窗口客户区像素"
        scale_x = self._full_pixmap.width() / dr.width()
        scale_y = self._full_pixmap.height() / dr.height()
        L = int(round(img_disp_x * scale_x))
        T = int(round(img_disp_y * scale_y))
        R = int(round((img_disp_x + img_disp_w) * scale_x))
        B = int(round((img_disp_y + img_disp_h) * scale_y))

        # 最终再夹一次，确保在真实图片范围内
        L = max(0, min(L, self._full_pixmap.width()))
        R = max(0, min(R, self._full_pixmap.width()))
        T = max(0, min(T, self._full_pixmap.height()))
        B = max(0, min(B, self._full_pixmap.height()))
        if R <= L or B <= T:
            return None
        return (L, T, R, B)

    # ============================================================
    #  杂项工具
    # ============================================================
    def _pil_to_qimage(self, pil_img) -> QImage:
        """PIL.Image(RGB) -> QImage。走 BytesIO 最快也最稳定。"""
        buffer = io.BytesIO()
        pil_img.save(buffer, format="BMP")
        qim = QImage.fromData(buffer.getvalue(), "BMP")
        return qim.copy()  # 复制一份，避免 buffer 被回收后 QImage 悬空

    def _set_status(self, text: str, warn: bool = False) -> None:
        self.lbl_status.setText(text)
        if warn:
            self.lbl_status.setStyleSheet("QLabel#previewStatusLabel { color: #ff6b6b; }")
        else:
            self.lbl_status.setStyleSheet("QLabel#previewStatusLabel { color: #c8d0d8; }")

    def _refresh_display_state_label(self) -> None:
        if self._target_hwnd == 0:
            self._set_status("暂无预览。请先在上方选择目标窗口，然后点『刷新预览』。")
            return
        if self._full_pixmap is None:
            self._set_status(f"已选择句柄 0x{self._target_hwnd:X}，但暂未成功获取预览图。", warn=True)
            return
        w, h = self._full_pixmap.width(), self._full_pixmap.height()
        if self._roi_window is None:
            self._set_status(
                f"窗口尺寸 {w}×{h}（句柄 0x{self._target_hwnd:X}）。"
                " 拖拽鼠标即可框选无人机监控区域（保存为相对窗口坐标）。"
            )
        else:
            L, T, R, B = self._roi_window
            self._set_status(
                f"窗口尺寸 {w}×{h}。已框选区域 "
                f"({L},{T}) → ({R},{B})  {R-L}×{B-T} 像素。"
            )


# ============================================================
#  私有类：_PreviewCanvas —— 自绘画布
#  对外通过 sig_drag_* 暴露鼠标拖拽事件
# ============================================================
class _PreviewCanvas(QWidget):
    sig_drag_started = pyqtSignal(object)   # QPoint
    sig_drag_moved = pyqtSignal(object)     # QPoint
    sig_drag_finished = pyqtSignal(object)  # QPoint

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._display_rect: QRect = QRect()
        self._roi: Optional[RoiRect] = None
        self._drag_rect: Optional[QRect] = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 300)
        # 设置一个有边框风格，让用户明显知道这是预览区
        self.setStyleSheet(
            "_PreviewCanvas {"
            "  border: 1px solid #1a2a2a;"
            "  background-color: #0d1219;"
            "}"
        )

    # ----- 对外 API -----
    def set_content(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self.update()

    def set_roi(self, roi: Optional[RoiRect]) -> None:
        self._roi = roi
        self.update()

    def set_drag_rect(self, rect: Optional[QRect]) -> None:
        self._drag_rect = rect
        self.update()

    def display_rect(self) -> Optional[QRect]:
        """返回当前图像在本控件中的显示矩形（用于坐标换算），无效时返回 None。"""
        if not self._display_rect.isValid():
            return None
        return QRect(self._display_rect)

    # ----- 绘制 -----
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            # 背景（在 QSS 之外再填一次，避免主题变化时透底）
            p.fillRect(self.rect(), QColor("#0d1219"))

            if self._pixmap is None or self._pixmap.isNull():
                # 无图占位：画提示文字
                p.setPen(QColor("#555b63"))
                p.drawText(self.rect(), Qt.AlignCenter,
                           "（此处显示 EVE 窗口画面预览）\n"
                           "选择窗口后点『刷新预览』；\n"
                           "然后在画面上拖拽鼠标框选无人机监控区域。")
                return

            # 计算"保持比例居中"的显示矩形
            cw, ch = self.width(), self.height()
            iw, ih = self._pixmap.width(), self._pixmap.height()
            if iw <= 0 or ih <= 0 or cw <= 0 or ch <= 0:
                return

            ratio = min(cw / iw, ch / ih)
            dw, dh = int(iw * ratio), int(ih * ratio)
            dx = (cw - dw) // 2
            dy = (ch - dh) // 2
            self._display_rect = QRect(dx, dy, dw, dh)

            p.drawPixmap(self._display_rect, self._pixmap)

            # 画 ROI 矩形（已保存）
            if self._roi is not None and self._display_rect.isValid():
                L, T, R, B = self._roi
                win_rect_widget = self._window_rect_to_widget_rect(L, T, R, B)
                if win_rect_widget is not None:
                    pen = QPen(QColor("#00d4aa"))
                    pen.setWidth(2)
                    pen.setStyle(Qt.SolidLine)
                    p.setPen(pen)
                    p.setBrush(QColor(0, 212, 170, 30))  # 半透明青绿
                    p.drawRect(win_rect_widget)
                    # 文字标签
                    p.setPen(QColor("#00d4aa"))
                    tag = f"ROI  ({R-L}×{B-T})"
                    p.drawText(win_rect_widget.adjusted(2, -16, -2, -2),
                               Qt.AlignLeft | Qt.AlignBottom, tag)

            # 画拖拽中的临时矩形
            if self._drag_rect is not None and self._drag_rect.isValid():
                pen = QPen(QColor("#ffd166"))
                pen.setWidth(2)
                pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.setBrush(QColor(255, 209, 102, 35))  # 半透明琥珀色
                p.drawRect(self._drag_rect)

        finally:
            p.end()

    # ----- 鼠标事件（转发为对外信号） -----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.sig_drag_started.emit(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.LeftButton:
            self.sig_drag_moved.emit(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.sig_drag_finished.emit(event.pos())
        super().mouseReleaseEvent(event)

    # ----- 坐标换算：真实窗口 ROI -> 控件显示矩形 -----
    def _window_rect_to_widget_rect(self, L: int, T: int, R: int, B: int) -> Optional[QRect]:
        if self._pixmap is None or self._pixmap.isNull() or not self._display_rect.isValid():
            return None
        if self._display_rect.width() <= 0 or self._display_rect.height() <= 0:
            return None
        scale_x = self._display_rect.width() / self._pixmap.width()
        scale_y = self._display_rect.height() / self._pixmap.height()
        x = self._display_rect.left() + int(round(L * scale_x))
        y = self._display_rect.top() + int(round(T * scale_y))
        w = int(round((R - L) * scale_x))
        h = int(round((B - T) * scale_y))
        if w <= 0 or h <= 0:
            return None
        return QRect(x, y, w, h)
