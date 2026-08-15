"""
============================================================
模块：services/base_service.py —— 服务基类
------------------------------------------------------------
功能说明：
    所有后台服务的父类，继承自 QThread（Qt 的线程类）。
    统一规定：
    - 子类必须实现 run()（后台干的活）和 stop()（优雅停止）
    - 通过 Qt 信号（Signal）把日志/结果/错误发给 UI，
      绝不直接操作任何 QWidget（跨线程操作 UI 会崩溃）

    通俗类比：
      BaseService 像"员工手册"，每个服务（员工）上岗前
      都要遵守同一套打卡、汇报、下班流程。

    🔒 线程安全说明：
      - stop() 只设置布尔标志位 _running，由 run() 循环自行检查退出，
        严禁使用 QThread.terminate()（官方明令禁止，可能导致资源泄漏）
      - 标志位是简单布尔值，Python 赋值是原子操作，多线程读写安全
============================================================
"""
from PyQt5.QtCore import QThread, pyqtSignal


class BaseService(QThread):
    """
    后台服务基类。

    对外信号（UI 层订阅这些信号即可，无需关心服务内部实现）：
        sig_log(str, str):    日志信号，参数为 (级别, 内容)，
                              级别取值 "INFO" / "WARNING" / "ERROR" 等
        sig_error(str):       错误信号，参数为错误描述，UI 收到后显示红色日志
        sig_finished(str):    结束信号，参数为服务名，UI 可据此更新状态
    """

    # ---- Qt 信号定义 ----
    # pyqtSignal(参数类型...)：声明一个可携带参数的信号
    sig_log = pyqtSignal(str, str)      # (日志级别, 日志内容)
    sig_error = pyqtSignal(str)         # (错误信息)
    sig_finished = pyqtSignal(str)      # (服务名称)

    def __init__(self, service_name: str, parent=None):
        """
        参数：
            service_name: 服务名称（用于日志标识与生命周期管理）
            parent: Qt 父对象，一般传 None
        """
        super().__init__(parent)
        self._service_name = service_name
        # 🔒 线程安全说明：运行标志位，stop() 置 False 后 run() 循环自行退出
        self._running = False

    @property
    def service_name(self) -> str:
        """只读属性：服务名称。"""
        return self._service_name

    def is_running(self) -> bool:
        """服务是否处于运行状态。"""
        return self._running

    def start_service(self) -> None:
        """
        启动服务。

        说明：不直接覆盖 QThread.start()，而是包一层，
        先置标志位再启动线程，语义更清晰。
        """
        if self._running:
            self.emit_log("WARNING", f"服务 {self._service_name} 已在运行，忽略重复启动")
            return
        self._running = True
        self.start()  # QThread.start() 会在新线程中调用 run()
        self.emit_log("INFO", f"服务 {self._service_name} 已启动")

    def stop(self) -> None:
        """
        优雅停止服务。

        🔒 线程安全说明：
          只把标志位置为 False，run() 里的循环检测到后自行退出。
          严禁调用 terminate()——Qt 官方文档明确警告：
          terminate() 不会释放线程持有的任何锁和资源，可能引发崩溃。
        """
        self._running = False
        self.emit_log("INFO", f"服务 {self._service_name} 收到停止指令")

    def wait_for_stop(self, timeout_ms: int = 3000) -> bool:
        """
        等待线程真正结束（用于程序退出时收尾）。

        参数：
            timeout_ms: 最长等待毫秒数。
        返回：
            bool: 线程在超时前结束返回 True。
        """
        return self.wait(timeout_ms)

    # ---- 供子类使用的便捷方法：发日志 / 发错误 ----
    def emit_log(self, level: str, message: str) -> None:
        """发送一条日志信号给 UI（跨线程安全，Qt 信号天然支持）。"""
        self.sig_log.emit(level, message)

    def emit_error(self, message: str) -> None:
        """发送一条错误信号给 UI。"""
        self.sig_error.emit(message)

    # ---- 子类必须实现的方法 ----
    def run(self) -> None:
        """
        线程主体：子类必须重写。

        规范：
        - 循环体内必须检查 self._running，保证能响应 stop()
        - 所有异常捕获具体类型，并通过 emit_error 发给 UI
        - 结束前发射 sig_finished
        """
        raise NotImplementedError("子类必须实现 run() 方法")
