"""
============================================================
模块：ui/tabs/monitor_tab.py —— 监控中心选项卡
------------------------------------------------------------
功能说明：
    主窗口核心页面「监控中心」，采用 QSplitter 左右分栏布局：
    - 左栏：控制按钮 + 预警参数 + 提醒开关 + 窗口列表表格
    - 右栏：状态行 + 事件日志 + 视觉预览

    UI 层职责约束：
    - 本文件只负责"画界面 + 发信号"
    - 点击按钮/切换配置 -> 发射信号，由主窗口/服务层处理
    - 日志/状态通过槽函数被动接收，不主动拉取
============================================================
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPixmap, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.window_enumerator import WindowInfo
from ui.widgets.preview_widget import PreviewWidget
from utils.constants import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_WARN,
    COLOR_TEXT,
)


class MonitorTab(QWidget):
    """
    监控中心选项卡页面。

    对外信号（由主窗口连接到服务层）：
        sig_start_all():            点击"开始监控"
        sig_stop_all():             点击"停止监控"
        sig_scan_once():            点击"扫描一次"
        sig_local_check():          点击"本地检查"
        sig_drone_check():          点击"无人机检查"
        sig_refresh_preview():      点击"刷新预览"
        sig_config_changed(dict):   预警配置/提醒开关变化（发射完整配置字典）
    """

    # ---------- 新增 Qt 信号 ----------
    sig_start_clicked = pyqtSignal()  # 旧版兼容
    sig_stop_clicked = pyqtSignal()   # 旧版兼容
    sig_start_all = pyqtSignal()
    sig_stop_all = pyqtSignal()
    sig_scan_once = pyqtSignal()
    sig_local_check = pyqtSignal()
    sig_drone_check = pyqtSignal()
    sig_refresh_preview = pyqtSignal()
    sig_config_changed = pyqtSignal(dict)
    sig_target_window_changed = pyqtSignal(int)  # 预览区选择的目标窗口变更 (hwnd)
    sig_drone_roi_changed = pyqtSignal(object)    # 无人机 ROI 区域变更 ((L,T,R,B) 或 None)
    sig_monitored_channels_changed = pyqtSignal(list)  # 监控频道白名单变化

    def __init__(self, parent=None):
        """构建监控中心页界面。"""
        super().__init__(parent)
        self._build_ui()
        self._connect_internal_signals()

    # ============================================================
    #  界面构建
    # ============================================================
    def _build_ui(self) -> None:
        """搭建界面控件与布局（纯界面代码，无业务逻辑）。"""
        # 根布局：一个水平 QSplitter，左右分栏
        root_splitter = QSplitter(Qt.Horizontal, self)
        root_splitter.setObjectName("monitorRootSplitter")
        root_splitter.setHandleWidth(2)

        # 左栏容器 + 右栏容器
        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        root_splitter.addWidget(left_panel)
        root_splitter.addWidget(right_panel)
        root_splitter.setStretchFactor(0, 4)   # 左栏占 4 份
        root_splitter.setStretchFactor(1, 6)   # 右栏占 6 份

        # 把 splitter 铺满整个 Tab
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(4, 4, 4, 4)
        outer_layout.addWidget(root_splitter)

    def _build_left_panel(self) -> QWidget:
        """构建左栏：控制按钮 + 预警配置 + 提醒开关 + 窗口列表。"""
        panel = QWidget(self)
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部：控制按钮组（Grid 两排三列） ----
        btn_group_box = QGroupBox("控制区", panel)
        btn_group_box.setObjectName("controlGroupBox")
        grid = QGridLayout(btn_group_box)
        grid.setSpacing(6)

        self.btn_scan_once = QPushButton("扫描一次", btn_group_box)
        self.btn_scan_once.setObjectName("btn_scan_once")
        grid.addWidget(self.btn_scan_once, 0, 0)

        self.btn_local_check = QPushButton("本地检查", btn_group_box)
        self.btn_local_check.setObjectName("btn_local_check")
        grid.addWidget(self.btn_local_check, 0, 1)

        self.btn_drone_check = QPushButton("无人机检查", btn_group_box)
        self.btn_drone_check.setObjectName("btn_drone_check")
        grid.addWidget(self.btn_drone_check, 0, 2)

        self.btn_refresh_preview = QPushButton("刷新预览", btn_group_box)
        self.btn_refresh_preview.setObjectName("btn_refresh_preview")
        grid.addWidget(self.btn_refresh_preview, 1, 0)

        self.btn_start = QPushButton("开始监控", btn_group_box)
        self.btn_start.setObjectName("btn_start")
        grid.addWidget(self.btn_start, 1, 1)

        self.btn_stop = QPushButton("停止监控", btn_group_box)
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)  # 初始未启动，停止按钮禁用
        grid.addWidget(self.btn_stop, 1, 2)

        layout.addWidget(btn_group_box)

        # ---- 中部：预警参数配置 ----
        cfg_group = QGroupBox("预警参数", panel)
        cfg_group.setObjectName("alertConfigGroupBox")
        form = QFormLayout(cfg_group)
        form.setSpacing(8)

        self.line_home_system = QLineEdit(cfg_group)
        self.line_home_system.setObjectName("line_home_system")
        self.line_home_system.setPlaceholderText("如 Jita")
        form.addRow("当前星系：", self.line_home_system)

        self.spin_jump_range = QSpinBox(cfg_group)
        self.spin_jump_range.setObjectName("spin_jump_range")
        self.spin_jump_range.setRange(1, 50)
        self.spin_jump_range.setValue(6)
        self.spin_jump_range.setSuffix(" 跳")
        form.addRow("跳数范围：", self.spin_jump_range)

        self.spin_alert_minutes = QSpinBox(cfg_group)
        self.spin_alert_minutes.setObjectName("spin_alert_minutes")
        self.spin_alert_minutes.setRange(1, 240)
        self.spin_alert_minutes.setValue(20)
        self.spin_alert_minutes.setSuffix(" 分钟")
        form.addRow("预警时间：", self.spin_alert_minutes)

        layout.addWidget(cfg_group)

        # ---- 提醒开关区 ----
        switch_group = QGroupBox("提醒开关", panel)
        switch_group.setObjectName("alertSwitchGroupBox")
        switch_layout = QVBoxLayout(switch_group)
        switch_layout.setSpacing(6)

        self.chk_show_overlay = QCheckBox("显示悬浮预警", switch_group)
        self.chk_show_overlay.setObjectName("chk_show_overlay")
        self.chk_show_overlay.setChecked(True)
        switch_layout.addWidget(self.chk_show_overlay)

        self.chk_voice_system = QCheckBox("星系预警语音", switch_group)
        self.chk_voice_system.setObjectName("chk_voice_system")
        self.chk_voice_system.setChecked(True)
        switch_layout.addWidget(self.chk_voice_system)

        self.chk_voice_local = QCheckBox("本地预警语音", switch_group)
        self.chk_voice_local.setObjectName("chk_voice_local")
        self.chk_voice_local.setChecked(True)
        switch_layout.addWidget(self.chk_voice_local)

        self.chk_voice_drone = QCheckBox("无人机预警语音", switch_group)
        self.chk_voice_drone.setObjectName("chk_voice_drone")
        self.chk_voice_drone.setChecked(True)
        switch_layout.addWidget(self.chk_voice_drone)

        layout.addWidget(switch_group)

        # ---- 监控频道白名单 ----
        ch_group = QGroupBox("监控频道白名单", panel)
        ch_group.setObjectName("channelWhitelistGroupBox")
        ch_layout = QVBoxLayout(ch_group)
        ch_layout.setContentsMargins(4, 4, 4, 4)
        ch_layout.setSpacing(4)

        # 输入行：频道名 + 添加按钮
        ch_input_row = QHBoxLayout()
        ch_input_row.setSpacing(4)
        self.line_channel_input = QLineEdit(ch_group)
        self.line_channel_input.setObjectName("line_channel_input")
        self.line_channel_input.setPlaceholderText("输入频道名，如 Local / Intel")
        ch_input_row.addWidget(self.line_channel_input, stretch=1)

        self.btn_add_channel = QPushButton("添加", ch_group)
        self.btn_add_channel.setObjectName("btn_add_channel")
        ch_input_row.addWidget(self.btn_add_channel)
        ch_layout.addLayout(ch_input_row)

        # 频道列表（每行带复选框）
        self.list_channels = QListWidget(ch_group)
        self.list_channels.setObjectName("list_channels")
        self.list_channels.setMaximumHeight(100)
        ch_layout.addWidget(self.list_channels)

        # 删除按钮
        self.btn_remove_channel = QPushButton("删除选中频道", ch_group)
        self.btn_remove_channel.setObjectName("btn_remove_channel")
        ch_layout.addWidget(self.btn_remove_channel)

        # 说明文字
        ch_hint = QLabel("勾选的频道日志才会被处理；未勾选或未添加的频道将被忽略。", ch_group)
        ch_hint.setWordWrap(True)
        ch_hint.setStyleSheet("QLabel { color: #889298; font-size: 11px; }")
        ch_layout.addWidget(ch_hint)

        layout.addWidget(ch_group)

        # ---- 底部：窗口列表表格 ----
        table_box = QGroupBox("游戏窗口列表", panel)
        table_box.setObjectName("windowsGroupBox")
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(4, 4, 4, 4)

        self.table_windows = QTableWidget(0, 6, table_box)
        self.table_windows.setObjectName("table_windows")
        self.table_windows.setHorizontalHeaderLabels(
            ["✓", "角色名", "进程ID", "句柄", "本地检测", "无人机检测"]
        )
        # 表头自适应与拉伸
        header = self.table_windows.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        # 行选中高亮（QSS 已定义）
        self.table_windows.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_windows.setSelectionMode(QTableWidget.SingleSelection)
        self.table_windows.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_windows.verticalHeader().setVisible(False)

        table_layout.addWidget(self.table_windows)
        layout.addWidget(table_box, stretch=1)

        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右栏：状态行 + 事件日志 + 视觉预览。"""
        panel = QWidget(self)
        panel.setObjectName("rightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部：状态行（横向） ----
        status_bar = QHBoxLayout()
        status_bar.setSpacing(16)

        self.lbl_status = QLabel("监控状态：未启动", panel)
        self.lbl_status.setObjectName("statusLabel")
        status_bar.addWidget(self.lbl_status)

        self.lbl_system = QLabel("当前星系：未知", panel)
        self.lbl_system.setObjectName("systemLabel")
        status_bar.addWidget(self.lbl_system)

        self.lbl_alert = QLabel("预警级别：-", panel)
        self.lbl_alert.setObjectName("alertLevelLabel")
        status_bar.addWidget(self.lbl_alert)

        status_bar.addStretch(1)  # 右侧弹性空白
        layout.addLayout(status_bar)

        # ---- 中部：事件日志 ----
        log_box = QGroupBox("事件日志", panel)
        log_box.setObjectName("eventLogGroupBox")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(4, 4, 4, 4)

        self.evt_log = QPlainTextEdit(log_box)
        self.evt_log.setObjectName("evt_log")
        self.evt_log.setReadOnly(True)
        self.evt_log.setFont(QFont("Consolas", 10))
        self.evt_log.setMaximumBlockCount(1000)
        log_layout.addWidget(self.evt_log)

        layout.addWidget(log_box, stretch=1)

        # ---- 底部：视觉预览（新：PreviewWidget = 下拉+刷新按钮+画布+ROI 拖拽） ----
        preview_box = QGroupBox("视觉预览 / 无人机区域框选", panel)
        preview_box.setObjectName("previewGroupBox")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(4, 4, 4, 4)
        preview_layout.setSpacing(4)

        self.preview_widget = PreviewWidget(preview_box)
        self.preview_widget.setObjectName("preview_widget")
        preview_layout.addWidget(self.preview_widget, stretch=1)

        # 旧兼容属性（外部调用 set_preview_image 的代码可以保持工作）
        self.preview_label = self.preview_widget.lbl_status

        layout.addWidget(preview_box, stretch=1)

        return panel

    # ============================================================
    #  内部信号连接（控件 -> 对外信号）
    # ============================================================
    def _connect_internal_signals(self) -> None:
        """连接按钮点击与配置控件变化 -> 对外发射信号。"""
        # 按钮组 -> 无参信号
        self.btn_scan_once.clicked.connect(self.sig_scan_once.emit)
        self.btn_local_check.clicked.connect(self.sig_local_check.emit)
        self.btn_drone_check.clicked.connect(self.sig_drone_check.emit)
        # 刷新预览按钮：优先走 PreviewWidget 自带截图（用户已经选了目标窗口时直接生效），
        # 同时也对外发信号让外层做日志记录。
        self.btn_refresh_preview.clicked.connect(self.preview_widget.refresh_preview)
        self.btn_refresh_preview.clicked.connect(self.sig_refresh_preview.emit)
        self.btn_start.clicked.connect(self.sig_start_all.emit)
        self.btn_start.clicked.connect(self.sig_start_clicked.emit)  # 旧版兼容
        self.btn_stop.clicked.connect(self.sig_stop_all.emit)
        self.btn_stop.clicked.connect(self.sig_stop_clicked.emit)    # 旧版兼容

        # 预警配置变化 -> 发射配置字典
        self.line_home_system.textChanged.connect(self._emit_config_changed)
        self.spin_jump_range.valueChanged.connect(self._emit_config_changed)
        self.spin_alert_minutes.valueChanged.connect(self._emit_config_changed)

        # 提醒开关变化 -> 发射配置字典
        self.chk_show_overlay.stateChanged.connect(self._emit_config_changed)
        self.chk_voice_system.stateChanged.connect(self._emit_config_changed)
        self.chk_voice_local.stateChanged.connect(self._emit_config_changed)
        self.chk_voice_drone.stateChanged.connect(self._emit_config_changed)

        # PreviewWidget 对外信号：目标窗口 / ROI 变化
        self.preview_widget.sig_target_changed.connect(self.sig_target_window_changed.emit)
        self.preview_widget.sig_roi_changed.connect(self.sig_drone_roi_changed.emit)

        # 监控频道白名单
        self.btn_add_channel.clicked.connect(self._on_add_channel)
        self.btn_remove_channel.clicked.connect(self._on_remove_channel)
        self.line_channel_input.returnPressed.connect(self._on_add_channel)
        self.list_channels.itemChanged.connect(self._on_channel_item_changed)

    def _emit_config_changed(self) -> None:
        """汇总当前预警配置，通过 sig_config_changed 发射。"""
        self.sig_config_changed.emit(self.get_monitor_config())

    # ============================================================
    #  监控频道白名单
    # ============================================================
    def _on_add_channel(self) -> None:
        """从输入框读取频道名，添加到列表（去重，默认勾选）。"""
        name = self.line_channel_input.text().strip()
        if not name:
            return
        # 去重检查（不区分大小写）
        existing = self.get_all_channels()
        if name.lower() in [c.lower() for c in existing]:
            self.line_channel_input.clear()
            return
        item = QListWidgetItem(name)
        item.setCheckState(Qt.Checked)  # 默认勾选
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        self.list_channels.addItem(item)
        self.line_channel_input.clear()
        self.sig_monitored_channels_changed.emit(self.get_monitored_channels())

    def _on_remove_channel(self) -> None:
        """删除列表中选中的频道项。"""
        row = self.list_channels.currentRow()
        if row < 0:
            return
        self.list_channels.takeItem(row)
        self.sig_monitored_channels_changed.emit(self.get_monitored_channels())

    def _on_channel_item_changed(self, _item) -> None:
        """复选框切换时发射信号。"""
        self.sig_monitored_channels_changed.emit(self.get_monitored_channels())

    def set_monitored_channels(self, channels: List[str]) -> None:
        """
        外部设置频道白名单（恢复配置时用）。

        参数：
            channels: 频道名列表，所有频道默认勾选。
        """
        self.list_channels.blockSignals(True)
        try:
            self.list_channels.clear()
            for name in channels:
                item = QListWidgetItem(name)
                item.setCheckState(Qt.Checked)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                self.list_channels.addItem(item)
        finally:
            self.list_channels.blockSignals(False)

    def get_monitored_channels(self) -> List[str]:
        """返回已勾选的频道名列表。"""
        result: List[str] = []
        for i in range(self.list_channels.count()):
            item = self.list_channels.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result

    def get_all_channels(self) -> List[str]:
        """返回所有已添加的频道名列表（含未勾选的）。"""
        return [self.list_channels.item(i).text() for i in range(self.list_channels.count())]

    # ============================================================
    #  对外公共方法
    # ============================================================
    def set_running(self, running: bool) -> None:
        """
        刷新监控状态显示 & 按钮启用互斥。

        参数：
            running: True=监控运行中（禁用"开始"，启用"停止"）；False=未启动。
        """
        if running:
            self.lbl_status.setText("监控状态：运行中")
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
        else:
            self.lbl_status.setText("监控状态：未启动")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def set_running_state(self, running: bool) -> None:
        """set_running 的别名，保持旧版接口兼容。"""
        self.set_running(running)

    def set_current_system(self, system: str) -> None:
        """
        刷新"当前星系"显示标签。

        参数：
            system: 当前星系名称（空字符串或 None 显示"未知"）。
        """
        if system:
            self.lbl_system.setText(f"当前星系：{system}")
        else:
            self.lbl_system.setText("当前星系：未知")

    def set_alert_level(self, text: str, color: Optional[str] = None) -> None:
        """
        刷新"预警级别"显示标签。

        参数：
            text:  预警级别文字（如"安全"/"警惕"/"危险"）。
            color: 可选，文字颜色 hex 值，不传则使用默认文字色。
        """
        self.lbl_alert.setText(f"预警级别：{text}")
        if color:
            self.lbl_alert.setStyleSheet(f"QLabel#alertLevelLabel {{ color: {color}; }}")
        else:
            self.lbl_alert.setStyleSheet(f"QLabel#alertLevelLabel {{ color: {COLOR_TEXT}; }}")

    def append_log(self, level: str, text: str) -> None:
        """
        在事件日志区追加一条带时间戳的分级着色日志。

        参数：
            level: 日志级别（"INFO" / "WARNING" / "ERROR"，未知级别用默认色）。
            text:  日志内容。
        """
        ts = datetime.now().strftime("%H:%M:%S")
        level_upper = level.upper()

        # 级别对应颜色映射
        color_map = {
            "ERROR": COLOR_ERROR,
            "WARNING": COLOR_WARN,
            "INFO": COLOR_INFO,
        }
        color = color_map.get(level_upper, COLOR_TEXT)

        # 转义 HTML 特殊字符，防止日志内容破坏排版
        safe_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

        # 组装一行带颜色的 HTML 并追加显示
        html = (
            f'<span style="color:{COLOR_TEXT};">[{ts}]</span> '
            f'<span style="color:{color};">[{level_upper}] {safe_text}</span>'
        )
        self.evt_log.appendHtml(html)

    def set_windows(
        self,
        windows: List[WindowInfo],
        monitored: Optional[Dict[int, bool]] = None,
        local_enabled: Optional[Dict[int, bool]] = None,
        drone_enabled: Optional[Dict[int, bool]] = None,
    ) -> None:
        """
        刷新窗口列表表格，并同步窗口列表到预览区的"目标窗口"下拉。

        参数：
            windows:       WindowInfo 列表。
            monitored:     {hwnd: bool} 指定哪些窗口勾选监控，默认空字典。
            local_enabled: {hwnd: bool} 指定哪些窗口开启本地检测，默认空字典。
            drone_enabled: {hwnd: bool} 指定哪些窗口开启无人机检测，默认空字典。
        """
        if monitored is None:
            monitored = {}
        if local_enabled is None:
            local_enabled = {}
        if drone_enabled is None:
            drone_enabled = {}

        # 同步到预览控件的窗口下拉（顺便记住之前选中的 hwnd，尽量不破坏用户选择）
        previous_hwnd = self.preview_widget.current_hwnd()
        self.preview_widget.set_windows(windows)
        if previous_hwnd != 0:
            self.preview_widget.set_target_hwnd(previous_hwnd)
        else:
            # 没选过时：如果窗口列表不为空，默认选第一个（更"开箱即用"）
            if windows:
                self.preview_widget.set_target_hwnd(windows[0].hwnd)

        # 清空旧行
        self.table_windows.setRowCount(0)

        for win in windows:
            row = self.table_windows.rowCount()
            self.table_windows.insertRow(row)

            # 第 0 列：复选框
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if monitored.get(win.hwnd, False):
                chk_item.setCheckState(Qt.Checked)
            else:
                chk_item.setCheckState(Qt.Unchecked)
            self.table_windows.setItem(row, 0, chk_item)

            # 第 1 列：角色名（从 WindowInfo 取，为空则显示窗口标题）
            char_name = win.character_name if win.character_name else win.title
            name_item = QTableWidgetItem(char_name)
            name_item.setData(Qt.UserRole, win.hwnd)  # 把 hwnd 存到 UserRole 方便读取
            self.table_windows.setItem(row, 1, name_item)

            # 第 2 列：进程ID
            pid_item = QTableWidgetItem(str(win.pid))
            self.table_windows.setItem(row, 2, pid_item)

            # 第 3 列：句柄（十六进制显示，更符合 Windows 习惯）
            hwnd_item = QTableWidgetItem(f"0x{win.hwnd:X}")
            self.table_windows.setItem(row, 3, hwnd_item)

            # 第 4 列：本地检测（QComboBox：开启/关闭）
            local_combo = QComboBox(self.table_windows)
            local_combo.setObjectName(f"local_combo_{win.hwnd}")
            local_combo.addItems(["开启", "关闭"])
            local_combo.setCurrentIndex(0 if local_enabled.get(win.hwnd, True) else 1)
            local_combo.currentIndexChanged.connect(self._emit_config_changed)
            self.table_windows.setCellWidget(row, 4, local_combo)

            # 第 5 列：无人机检测（QComboBox：开启/关闭）
            drone_combo = QComboBox(self.table_windows)
            drone_combo.setObjectName(f"drone_combo_{win.hwnd}")
            drone_combo.addItems(["开启", "关闭"])
            drone_combo.setCurrentIndex(0 if drone_enabled.get(win.hwnd, True) else 1)
            drone_combo.currentIndexChanged.connect(self._emit_config_changed)
            self.table_windows.setCellWidget(row, 5, drone_combo)

    def set_preview_image(self, image_or_none: Optional[QPixmap]) -> None:
        """
        兼容旧接口：设置视觉预览图像。

        说明：新代码推荐直接用 self.preview_widget.refresh_preview() 按真实窗口截图，
        但外部若仍然传入 QPixmap（比如本地关系图、无人机目标可视化），这里也能正常显示。
        """
        # 走 PreviewWidget 画布的 set_content 把图显示上去（并清空 ROI 矩形显示，因为不是同一张图了）
        self.preview_widget.canvas.set_content(image_or_none)
        self.preview_widget.canvas.set_roi(None)

    # ============================================================
    #  新增：预览区对外快捷方法（目标窗口 / ROI）
    # ============================================================
    def current_preview_hwnd(self) -> int:
        """预览区当前选中的目标窗口句柄（0 代表未选中）。"""
        return self.preview_widget.current_hwnd()

    def current_drone_roi(self):
        """
        预览区当前框选的无人机 ROI。

        返回：
            (L, T, R, B) 相对真实窗口客户区坐标；未框选时为 None。
        """
        return self.preview_widget.current_roi()

    def set_preview_target_hwnd(self, hwnd: int) -> None:
        """编程方式设置预览区目标窗口；0 表示取消选择。"""
        self.preview_widget.set_target_hwnd(hwnd)

    def set_drone_roi(self, roi) -> None:
        """编程方式设置预览区 ROI。"""
        self.preview_widget._roi_window = roi
        self.preview_widget.canvas.set_roi(roi)
        self.preview_widget._refresh_display_state_label()

    def refresh_preview_now(self) -> None:
        """编程方式触发『刷新预览』。"""
        self.preview_widget.refresh_preview()

    def get_monitor_config(self) -> dict:
        """
        提取当前预警配置字典（与 sig_config_changed 发射内容一致）。

        返回 dict 键：
            home_system, jump_range, alert_window_minutes,
            show_overlay, voice_system_warning, voice_local_warning, voice_drone_warning
        """
        return {
            "home_system": self.line_home_system.text().strip(),
            "jump_range": self.spin_jump_range.value(),
            "alert_window_minutes": self.spin_alert_minutes.value(),
            "show_overlay": self.chk_show_overlay.isChecked(),
            "voice_system_warning": self.chk_voice_system.isChecked(),
            "voice_local_warning": self.chk_voice_local.isChecked(),
            "voice_drone_warning": self.chk_voice_drone.isChecked(),
        }

    def get_window_monitoring(self) -> Tuple[List[int], Dict[int, bool], Dict[int, bool]]:
        """
        返回当前表格中窗口的监控配置。

        返回：
            (checked_hwnd_list, local_map, drone_map)
            - checked_hwnd_list: 勾选了监控的窗口句柄列表
            - local_map:         {hwnd: bool} 本地检测是否开启
            - drone_map:         {hwnd: bool} 无人机检测是否开启
        """
        checked_hwnds: List[int] = []
        local_map: Dict[int, bool] = {}
        drone_map: Dict[int, bool] = {}

        for row in range(self.table_windows.rowCount()):
            # 从第 1 列（角色名）的 UserRole 取回 hwnd
            name_item = self.table_windows.item(row, 1)
            if name_item is None:
                continue
            hwnd = name_item.data(Qt.UserRole)
            if hwnd is None:
                continue

            # 第 0 列：复选框
            chk_item = self.table_windows.item(row, 0)
            if chk_item is not None and chk_item.checkState() == Qt.Checked:
                checked_hwnds.append(hwnd)

            # 第 4 列：本地检测 ComboBox
            local_combo = self.table_windows.cellWidget(row, 4)
            if isinstance(local_combo, QComboBox):
                local_map[hwnd] = (local_combo.currentIndex() == 0)

            # 第 5 列：无人机检测 ComboBox
            drone_combo = self.table_windows.cellWidget(row, 5)
            if isinstance(drone_combo, QComboBox):
                drone_map[hwnd] = (drone_combo.currentIndex() == 0)

        return checked_hwnds, local_map, drone_map
