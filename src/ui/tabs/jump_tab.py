"""
============================================================
模块：ui/tabs/jump_tab.py —— 跳数计算选项卡
------------------------------------------------------------
功能说明：
    输入起点/终点星系，点击计算后显示跳数结果。
    UI 层只负责收集输入、发射信号、展示结果，
    真正的图计算在 core/jump_calculator.py 完成。
============================================================
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class JumpTab(QWidget):
    """
    跳数计算选项卡页面。

    对外信号：
        sig_calculate(str, str): 用户点击计算按钮，
                                 参数为 (起点星系名, 终点星系名)。
    """

    sig_calculate = pyqtSignal(str, str)

    def __init__(self, parent=None):
        """构建跳数计算页界面。"""
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """搭建界面控件与布局。"""
        root_layout = QVBoxLayout(self)

        # ---- 输入行：起点 + 终点 + 计算按钮 ----
        input_layout = QHBoxLayout()

        input_layout.addWidget(QLabel("起点星系："))
        self._from_input = QLineEdit()
        self._from_input.setPlaceholderText("例如：Jita")  # 占位提示文字
        input_layout.addWidget(self._from_input)

        input_layout.addWidget(QLabel("终点星系："))
        self._to_input = QLineEdit()
        self._to_input.setPlaceholderText("例如：Amarr")
        input_layout.addWidget(self._to_input)

        # 计算按钮：点击时把两个输入框内容通过信号发出去
        self._calc_button = QPushButton("计算跳数")
        self._calc_button.clicked.connect(self._on_calc_clicked)
        input_layout.addWidget(self._calc_button)

        root_layout.addLayout(input_layout)

        # ---- 结果展示标签 ----
        self._result_label = QLabel("计算结果将显示在这里")
        self._result_label.setObjectName("jumpResultLabel")
        root_layout.addWidget(self._result_label)

        root_layout.addStretch()  # 底部弹性空白，把内容顶到上方

    def _on_calc_clicked(self) -> None:
        """计算按钮点击处理：发射信号（不在 UI 层做计算）。"""
        from_text = self._from_input.text().strip()
        to_text = self._to_input.text().strip()
        self.sig_calculate.emit(from_text, to_text)

    def show_result(self, text: str) -> None:
        """
        显示计算结果（供主窗口在收到计算结果后调用）。

        参数：
            text: 结果描述文本，如 "Jita -> Amarr：14 跳"。
        """
        self._result_label.setText(text)
