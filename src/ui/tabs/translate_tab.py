"""
============================================================
模块：ui/tabs/translate_tab.py —— 频道翻译选项卡
------------------------------------------------------------
功能说明：
    主窗口的 Tab 2：频道翻译页。
    - 顶部：频道选择下拉框 + 添加/移除按钮（维护翻译白名单）
    - 中间：原文/译文对照表格（时间 | 频道 | 发送者 | 原文 / 译文）
    - 底部：选中行的快速预览框

UI 层职责约束：
    - 只负责"画界面 + 发信号 + 被动展示"
    - 配置变更 → 发射 sig_config_changed 信号，由主窗口写入配置
    - 翻译结果通过 add_translation_result 被动接收
============================================================
"""
from datetime import datetime
from typing import Iterable, List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TranslateTab(QWidget):
    """
    频道翻译选项卡页面。

    对外信号：
        sig_config_changed(List[str]): 翻译频道名单变更信号，
                                       发射当前完整的翻译中频道名列表。
    """

    MAX_ROWS = 500  # 表格最大行数，超过后自动删除最旧行

    sig_config_changed = pyqtSignal(list)  # List[str]

    def __init__(self, parent=None):
        """构建翻译页界面与内部状态。"""
        super().__init__(parent)

        # 当前正在翻译的频道名列表（去重保序）
        self._translation_channels: List[str] = []

        self._build_ui()
        self._connect_signals()

    # ============================================================
    #  UI 搭建
    # ============================================================
    def _build_ui(self) -> None:
        """搭建界面控件与布局。"""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        # ---------- 顶部栏：频道选择 + 增/减按钮 + 信息 ----------
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        top_layout.addWidget(QLabel("选择频道："))

        # 下拉框：可手动输入自定义频道名
        self.combo_channels = QComboBox()
        self.combo_channels.setEditable(True)
        self.combo_channels.setMinimumWidth(260)
        # 让用户可以直接手输不存在的频道名；默认的 completer 允许补全
        line_edit = self.combo_channels.lineEdit()
        if isinstance(line_edit, QLineEdit):
            line_edit.setPlaceholderText("输入或选择一个频道名")
        top_layout.addWidget(self.combo_channels, stretch=1)

        self.btn_add = QPushButton("添加到翻译列表")
        top_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("从翻译列表移除")
        top_layout.addWidget(self.btn_remove)

        top_layout.addStretch(1)

        self._info_label = QLabel("正在翻译 0 个频道")
        self._info_label.setObjectName("translateInfoLabel")
        top_layout.addWidget(self._info_label)

        root_layout.addLayout(top_layout)

        # ---------- 中部：翻译结果表格 ----------
        self.table_translations = QTableWidget(0, 4, self)
        self.table_translations.setHorizontalHeaderLabels(
            ["时间", "频道", "发送者", "原文 / 译文"]
        )
        self.table_translations.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_translations.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_translations.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_translations.setAlternatingRowColors(True)
        self.table_translations.verticalHeader().setVisible(False)
        self.table_translations.verticalHeader().setDefaultSectionSize(56)

        header = self.table_translations.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_translations.setColumnWidth(0, 140)
        self.table_translations.setColumnWidth(1, 140)
        self.table_translations.setColumnWidth(2, 140)

        root_layout.addWidget(self.table_translations, stretch=1)

        # ---------- 底部：快速预览 ----------
        self.sender_preview = QPlainTextEdit(self)
        self.sender_preview.setReadOnly(True)
        self.sender_preview.setMaximumHeight(150)
        self.sender_preview.setPlaceholderText(
            "快速预览：选中表格行后，详情显示在这里"
        )
        root_layout.addWidget(self.sender_preview)

    def _connect_signals(self) -> None:
        """连接按钮点击/表格选中信号。"""
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        self.table_translations.itemSelectionChanged.connect(
            self._on_selection_changed
        )

    # ============================================================
    #  按钮 / 动作槽函数
    # ============================================================
    def _current_selected_channel(self) -> str:
        """
        读取下拉框当前值（优先 currentText，兼容用户手输）。

        返回：
            去除空白后的频道名；空字符串表示无有效输入。
        """
        txt = ""
        try:
            txt = self.combo_channels.currentText()
        except Exception:  # noqa: BLE001
            txt = ""
        return txt.strip()

    def _on_add_clicked(self) -> None:
        """添加按钮：把当前选中/手输的频道加入翻译列表。"""
        ch = self._current_selected_channel()
        if not ch:
            return
        if ch in self._translation_channels:
            return
        self._translation_channels.append(ch)
        self._refresh_info_label()
        self.sig_config_changed.emit(list(self._translation_channels))

    def _on_remove_clicked(self) -> None:
        """移除按钮：把当前选中/手输的频道从翻译列表移除。"""
        ch = self._current_selected_channel()
        if not ch:
            return
        if ch not in self._translation_channels:
            return
        self._translation_channels.remove(ch)
        self._refresh_info_label()
        self.sig_config_changed.emit(list(self._translation_channels))

    def _on_selection_changed(self) -> None:
        """选中行变化：刷新预览区。"""
        rows = self.table_translations.selectionModel().selectedRows()
        if not rows:
            self.sender_preview.setPlainText("")
            return
        row = rows[0].row()

        def cell(col: int) -> str:
            it = self.table_translations.item(row, col)
            return it.text() if it is not None else ""

        time_s = cell(0)
        channel = cell(1)
        sender = cell(2)
        content = cell(3)
        preview = (
            f"时间：{time_s}\n"
            f"频道：{channel}\n"
            f"发送者：{sender}\n"
            f"────── 内容 ──────\n"
            f"{content}"
        )
        self.sender_preview.setPlainText(preview)

    # ============================================================
    #  对外公共 API
    # ============================================================
    def set_available_channels(self, channels: Iterable[str]) -> None:
        """
        重置下拉框候选频道集合（保留当前输入框里的文本）。

        参数：
            channels: 候选频道名集合（自动去重）。
        """
        current_text = self._current_selected_channel()

        seen = set()
        unique: List[str] = []
        for ch in channels:
            if not ch:
                continue
            if ch in seen:
                continue
            seen.add(ch)
            unique.append(ch)

        self.combo_channels.blockSignals(True)
        try:
            self.combo_channels.clear()
            self.combo_channels.addItems(unique)
            # 还原用户原本在输入框里的值（可能是手输的、不包含在 items 中的频道）
            if current_text:
                self.combo_channels.setEditText(current_text)
        finally:
            self.combo_channels.blockSignals(False)

    def add_translation_result(
        self,
        channel: str,
        sender: str,
        original: str,
        translated: str,
    ) -> None:
        """
        追加一条翻译结果到表格（新行出现在最底部；超过 MAX_ROWS 删最旧行）。

        参数：
            channel:    频道名
            sender:     发送者
            original:   原文
            translated: 译文（空字符串时显示为 "[无译文]"）
        """
        time_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        display_translated = translated if translated else "[无译文]"
        combined = f"{original}\n{'─' * 20}\n{display_translated}"

        row = self.table_translations.rowCount()
        self.table_translations.insertRow(row)

        items = [time_s, channel, sender, combined]
        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            if col < 3:
                # 前三列顶部对齐；最后一列默认对齐即可（含换行内容）
                item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.table_translations.setItem(row, col, item)

        self.table_translations.scrollToBottom()

        # 超过最大行数时删除最上面（最旧）的行
        while self.table_translations.rowCount() > self.MAX_ROWS:
            self.table_translations.removeRow(0)

    def set_translation_channels(self, channels: Iterable[str]) -> None:
        """
        设置"当前翻译中的频道"列表并刷新信息标签。

        说明：此方法只更新 UI 状态，不会主动发射 sig_config_changed。
        典型用于程序启动时从配置中加载已有频道名列表。

        参数：
            channels: 翻译中的频道名列表（自动去重保序）。
        """
        seen = set()
        result: List[str] = []
        for ch in channels:
            if not ch:
                continue
            if ch in seen:
                continue
            seen.add(ch)
            result.append(ch)
        self._translation_channels = result
        self._refresh_info_label()

    # ============================================================
    #  内部工具
    # ============================================================
    def _refresh_info_label(self) -> None:
        """刷新"正在翻译 N 个频道"信息标签。"""
        n = len(self._translation_channels)
        if n == 0:
            self._info_label.setText("正在翻译 0 个频道（翻译全部频道的非中文消息）")
        else:
            self._info_label.setText(f"正在翻译 {n} 个频道")
