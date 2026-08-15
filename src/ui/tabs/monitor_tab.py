"""
============================================================
模块：ui/tabs/monitor_tab.py —— 监控中心选项卡
------------------------------------------------------------
功能说明：
    主窗口核心页面「监控中心」，采用 QSplitter 左右分栏布局：
    - 左栏：控制按钮 + 预警参数 + 提醒开关 + 频道发现与监控 + 无人机预警关键字 + 窗口列表
    - 右栏：状态行 + 事件日志

    变更说明：
        - 已移除"视觉预览 / 无人机 ROI 框选"区域（无人机改为日志关键字监控）
        - 新增"频道发现"功能：扫描 Chatlogs 目录自动列出所有频道供勾选
        - 新增"无人机预警关键字"可编辑区

    UI 层职责约束：
    - 本文件只负责"画界面 + 发信号"
    - 点击按钮/切换配置 -> 发射信号，由主窗口/服务层处理
    - 日志/状态通过槽函数被动接收，不主动拉取
============================================================
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
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
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.window_enumerator import WindowInfo
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
        sig_scan_once():            点击"扫描窗口"（枚举 EVE 窗口）
        sig_local_check():          点击"本地检查"
        sig_drone_check():          点击"无人机检查"
        sig_config_changed(dict):   预警配置/提醒开关变化（发射完整配置字典）
        sig_monitored_channels_changed(list): 监控频道勾选变化
        sig_discover_channels():    点击"扫描频道"（请求扫描 Chatlogs 目录）
        sig_drone_keywords_changed(list): 无人机关键字列表变化
    """

    # ---------- Qt 信号 ----------
    sig_start_clicked = pyqtSignal()  # 旧版兼容
    sig_stop_clicked = pyqtSignal()   # 旧版兼容
    sig_start_all = pyqtSignal()
    sig_stop_all = pyqtSignal()
    sig_scan_once = pyqtSignal()
    sig_local_check = pyqtSignal()
    sig_drone_check = pyqtSignal()
    sig_config_changed = pyqtSignal(dict)
    sig_monitored_channels_changed = pyqtSignal(list)  # 监控频道白名单变化
    sig_discover_channels = pyqtSignal()               # 请求扫描频道目录
    sig_drone_keywords_changed = pyqtSignal(list)       # 无人机关键字变化

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
        """构建左栏：控制按钮 + 预警配置 + 提醒开关 + 频道发现 + 无人机关键字 + 窗口列表。"""
        panel = QWidget(self)
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部：控制按钮组 ----
        btn_group_box = QGroupBox("控制区", panel)
        btn_group_box.setObjectName("controlGroupBox")
        grid = QGridLayout(btn_group_box)
        grid.setSpacing(6)

        self.btn_scan_once = QPushButton("扫描窗口", btn_group_box)
        self.btn_scan_once.setObjectName("btn_scan_once")
        grid.addWidget(self.btn_scan_once, 0, 0)

        self.btn_local_check = QPushButton("本地检查", btn_group_box)
        self.btn_local_check.setObjectName("btn_local_check")
        grid.addWidget(self.btn_local_check, 0, 1)

        self.btn_drone_check = QPushButton("无人机检查", btn_group_box)
        self.btn_drone_check.setObjectName("btn_drone_check")
        grid.addWidget(self.btn_drone_check, 0, 2)

        self.btn_start = QPushButton("开始监控", btn_group_box)
        self.btn_start.setObjectName("btn_start")
        grid.addWidget(self.btn_start, 1, 0)

        self.btn_stop = QPushButton("停止监控", btn_group_box)
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)  # 初始未启动，停止按钮禁用
        grid.addWidget(self.btn_stop, 1, 1)

        layout.addWidget(btn_group_box)

        # ---- 预警参数配置 ----
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

        # ---- 频道发现与监控 ----
        ch_group = QGroupBox("频道发现与监控", panel)
        ch_group.setObjectName("channelDiscoverGroupBox")
        ch_layout = QVBoxLayout(ch_group)
        ch_layout.setContentsMargins(4, 4, 4, 4)
        ch_layout.setSpacing(4)

        # 扫描频道按钮 + 手动添加输入框
        ch_top_row = QHBoxLayout()
        ch_top_row.setSpacing(4)
        self.btn_discover_channels = QPushButton("扫描频道", ch_group)
        self.btn_discover_channels.setObjectName("btn_discover_channels")
        ch_top_row.addWidget(self.btn_discover_channels)

        self.line_channel_input = QLineEdit(ch_group)
        self.line_channel_input.setObjectName("line_channel_input")
        self.line_channel_input.setPlaceholderText("或手动输入频道名")
        ch_top_row.addWidget(self.line_channel_input, stretch=1)

        self.btn_add_channel = QPushButton("添加", ch_group)
        self.btn_add_channel.setObjectName("btn_add_channel")
        ch_top_row.addWidget(self.btn_add_channel)
        ch_layout.addLayout(ch_top_row)

        # 频道列表（每行带复选框，勾选=监控）
        self.list_channels = QListWidget(ch_group)
        self.list_channels.setObjectName("list_channels")
        self.list_channels.setMaximumHeight(120)
        ch_layout.addWidget(self.list_channels)

        # 删除按钮
        self.btn_remove_channel = QPushButton("删除选中频道", ch_group)
        self.btn_remove_channel.setObjectName("btn_remove_channel")
        ch_layout.addWidget(self.btn_remove_channel)

        # 说明文字
        ch_hint = QLabel("点击「扫描频道」自动发现；勾选的频道才会被监控。", ch_group)
        ch_hint.setWordWrap(True)
        ch_hint.setStyleSheet("QLabel { color: #889298; font-size: 11px; }")
        ch_layout.addWidget(ch_hint)

        layout.addWidget(ch_group)

        # ---- 无人机预警关键字 ----
        kw_group = QGroupBox("无人机预警关键字", panel)
        kw_group.setObjectName("droneKeywordsGroupBox")
        kw_layout = QVBoxLayout(kw_group)
        kw_layout.setContentsMargins(4, 4, 4, 4)
        kw_layout.setSpacing(4)

        # 关键字输入行
        kw_input_row = QHBoxLayout()
        kw_input_row.setSpacing(4)
        self.line_keyword_input = QLineEdit(kw_group)
        self.line_keyword_input.setObjectName("line_keyword_input")
        self.line_keyword_input.setPlaceholderText("输入关键字，如 无人机受损")
        kw_input_row.addWidget(self.line_keyword_input, stretch=1)

        self.btn_add_keyword = QPushButton("添加", kw_group)
        self.btn_add_keyword.setObjectName("btn_add_keyword")
        kw_input_row.addWidget(self.btn_add_keyword)
        kw_layout.addLayout(kw_input_row)

        # 关键字列表（不带复选框，所有项都生效）
        self.list_keywords = QListWidget(kw_group)
        self.list_keywords.setObjectName("list_keywords")
        self.list_keywords.setMaximumHeight(80)
        kw_layout.addWidget(self.list_keywords)

        # 删除按钮
        self.btn_remove_keyword = QPushButton("删除选中关键字", kw_group)
        self.btn_remove_keyword.setObjectName("btn_remove_keyword")
        kw_layout.addWidget(self.btn_remove_keyword)

        # 说明文字
        kw_hint = QLabel("日志命中任一关键字即报警；留空使用默认关键字。", kw_group)
        kw_hint.setWordWrap(True)
        kw_hint.setStyleSheet("QLabel { color: #889298; font-size: 11px; }")
        kw_layout.addWidget(kw_hint)

        layout.addWidget(kw_group)

        # ---- 底部：窗口列表表格（信息展示） ----
        table_box = QGroupBox("游戏窗口列表", panel)
        table_box.setObjectName("windowsGroupBox")
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(4, 4, 4, 4)

        self.table_windows = QTableWidget(0, 3, table_box)
        self.table_windows.setObjectName("table_windows")
        self.table_windows.setHorizontalHeaderLabels(["角色名", "进程ID", "句柄"])
        header = self.table_windows.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_windows.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_windows.setSelectionMode(QTableWidget.SingleSelection)
        self.table_windows.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_windows.verticalHeader().setVisible(False)

        table_layout.addWidget(self.table_windows)
        layout.addWidget(table_box, stretch=1)

        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右栏：状态行 + 事件日志。"""
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

        # ---- 事件日志（占满右栏） ----
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

        # 频道发现与监控
        self.btn_discover_channels.clicked.connect(self.sig_discover_channels.emit)
        self.btn_add_channel.clicked.connect(self._on_add_channel)
        self.btn_remove_channel.clicked.connect(self._on_remove_channel)
        self.line_channel_input.returnPressed.connect(self._on_add_channel)
        self.list_channels.itemChanged.connect(self._on_channel_item_changed)

        # 无人机关键字
        self.btn_add_keyword.clicked.connect(self._on_add_keyword)
        self.btn_remove_keyword.clicked.connect(self._on_remove_keyword)
        self.line_keyword_input.returnPressed.connect(self._on_add_keyword)

    def _emit_config_changed(self) -> None:
        """汇总当前预警配置，通过 sig_config_changed 发射。"""
        self.sig_config_changed.emit(self.get_monitor_config())

    # ============================================================
    #  频道发现与监控
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

    def set_discovered_channels(self, channels: List[str]) -> None:
        """
        把扫描到的频道列表填入 UI（保留已勾选状态，新增项默认勾选）。

        参数：
            channels: 扫描到的频道名列表。
        """
        # 记住当前已勾选的频道（不区分大小写）
        old_checked = {c.lower() for c in self.get_monitored_channels()}
        # 记住所有已有频道（用于判断是否新增）
        old_all = {c.lower() for c in self.get_all_channels()}

        self.list_channels.blockSignals(True)
        try:
            self.list_channels.clear()
            for name in channels:
                item = QListWidgetItem(name)
                # 已存在且曾被取消勾选的，保持原状态；其余默认勾选
                if name.lower() in old_checked or name.lower() not in old_all:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                self.list_channels.addItem(item)
        finally:
            self.list_channels.blockSignals(False)

        # 扫描后通知外层更新白名单（勾选状态可能变化）
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
    #  无人机预警关键字
    # ============================================================
    def _on_add_keyword(self) -> None:
        """从输入框读取关键字，添加到列表（去重）。"""
        kw = self.line_keyword_input.text().strip()
        if not kw:
            return
        existing = self.get_drone_keywords()
        if kw.lower() in [k.lower() for k in existing]:
            self.line_keyword_input.clear()
            return
        item = QListWidgetItem(kw)
        self.list_keywords.addItem(item)
        self.line_keyword_input.clear()
        self.sig_drone_keywords_changed.emit(self.get_drone_keywords())

    def _on_remove_keyword(self) -> None:
        """删除列表中选中的关键字。"""
        row = self.list_keywords.currentRow()
        if row < 0:
            return
        self.list_keywords.takeItem(row)
        self.sig_drone_keywords_changed.emit(self.get_drone_keywords())

    def set_drone_keywords(self, keywords: List[str]) -> None:
        """
        外部设置关键字列表（恢复配置时用）。

        参数：
            keywords: 关键字列表。
        """
        self.list_keywords.blockSignals(True)
        try:
            self.list_keywords.clear()
            for kw in keywords:
                self.list_keywords.addItem(QListWidgetItem(kw))
        finally:
            self.list_keywords.blockSignals(False)

    def get_drone_keywords(self) -> List[str]:
        """返回当前所有关键字列表。"""
        return [self.list_keywords.item(i).text() for i in range(self.list_keywords.count())]

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
        """刷新"当前星系"显示标签。"""
        if system:
            self.lbl_system.setText(f"当前星系：{system}")
        else:
            self.lbl_system.setText("当前星系：未知")

    def set_alert_level(self, text: str, color: Optional[str] = None) -> None:
        """刷新"预警级别"显示标签。"""
        self.lbl_alert.setText(f"预警级别：{text}")
        if color:
            self.lbl_alert.setStyleSheet(f"QLabel#alertLevelLabel {{ color: {color}; }}")
        else:
            self.lbl_alert.setStyleSheet(f"QLabel#alertLevelLabel {{ color: {COLOR_TEXT}; }}")

    def append_log(self, level: str, text: str) -> None:
        """在事件日志区追加一条带时间戳的分级着色日志。"""
        ts = datetime.now().strftime("%H:%M:%S")
        level_upper = level.upper()

        color_map = {
            "ERROR": COLOR_ERROR,
            "WARNING": COLOR_WARN,
            "INFO": COLOR_INFO,
        }
        color = color_map.get(level_upper, COLOR_TEXT)

        # 转义 HTML 特殊字符
        safe_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

        html = (
            f'<span style="color:{COLOR_TEXT};">[{ts}]</span> '
            f'<span style="color:{color};">[{level_upper}] {safe_text}</span>'
        )
        self.evt_log.appendHtml(html)

    def set_windows(self, windows: List[WindowInfo]) -> None:
        """
        刷新窗口列表表格（纯信息展示：角色名/PID/句柄）。

        参数：
            windows: WindowInfo 列表。
        """
        self.table_windows.setRowCount(0)
        for win in windows:
            row = self.table_windows.rowCount()
            self.table_windows.insertRow(row)

            # 角色名（为空则显示窗口标题）
            char_name = win.character_name if win.character_name else win.title
            name_item = QTableWidgetItem(char_name)
            name_item.setData(Qt.UserRole, win.hwnd)
            self.table_windows.setItem(row, 0, name_item)

            # 进程ID
            self.table_windows.setItem(row, 1, QTableWidgetItem(str(win.pid)))

            # 句柄（十六进制）
            self.table_windows.setItem(row, 2, QTableWidgetItem(f"0x{win.hwnd:X}"))

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
