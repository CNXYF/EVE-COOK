"""
============================================================
模块：core/log_watcher.py —— EVE 日志监视器（观察者模式）
------------------------------------------------------------
功能说明：
    使用 watchdog 库监听 EVE 客户端日志目录的文件变化
    （Observer 模式，非轮询），把新增的日志行广播给所有订阅者。

    观察者模式通俗解释：
      像"订阅公众号"——多个服务（Local监控/Intel监控）先"关注"本监视器，
      一旦日志有新内容，监视器自动把内容推送给所有关注者。

    🔒 线程安全说明：
      watchdog 的回调运行在它自己的后台线程中，
      订阅者列表的增删用 threading.Lock 保护，防止并发修改出错。
============================================================
"""
import threading
from pathlib import Path
from typing import Callable, List

from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from watchdog.observers import Observer

from utils.logger import get_logger

logger = get_logger("log_watcher")

# 订阅者回调的类型别名：接收一个参数（新增的日志行文本）
LogLineCallback = Callable[[str], None]


class _LogFileHandler(FileSystemEventHandler):
    """
    watchdog 事件处理器：只关心 .txt 日志文件的"修改"事件。

    说明：
        watchdog 会在文件发生变化时调用 on_modified 方法，
        我们在这里读取文件新增的内容并交给 LogWatcher 广播。
    """

    def __init__(self, watcher: "LogWatcher"):
        """持有外层 LogWatcher 的引用，用于回调广播。"""
        super().__init__()
        self._watcher = watcher

    def on_modified(self, event):
        """
        文件被修改时由 watchdog 自动调用。

        ⚠️ 注意：此回调运行在 watchdog 的后台线程，
        内部绝不能抛出异常，否则会导致监听中断。
        """
        try:
            # 只处理文件修改事件，忽略目录事件
            if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".txt"):
                self._watcher.handle_file_change(Path(event.src_path))
        except Exception as e:  # noqa: BLE001 —— 回调必须吞掉所有异常
            # 兜底保护：任何异常都只记日志，不向外抛
            logger.error(f"日志事件处理异常（已拦截）：{e}")


class LogWatcher:
    """
    EVE 日志监视器：监听目录 -> 读取新增行 -> 广播给订阅者。
    """

    def __init__(self, watch_dir: Path):
        """
        参数：
            watch_dir: 要监听的 EVE 日志目录（如 Chatlogs 目录）。
        """
        self._watch_dir = watch_dir
        self._observer = Observer()                       # watchdog 观察者实例
        self._subscribers: List[LogLineCallback] = []     # 订阅者回调列表
        self._lock = threading.Lock()                     # 🔒 保护订阅者列表
        # 记录每个文件已读到的字节位置，下次只读"新增部分"
        self._file_positions: dict = {}

    def subscribe(self, callback: LogLineCallback) -> None:
        """
        订阅日志行。服务层调用此方法注册回调。

        🔒 线程安全说明：加锁修改订阅者列表。
        """
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: LogLineCallback) -> None:
        """取消订阅（服务停止时调用，防止内存泄漏）。"""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def start(self) -> None:
        """启动监听。非阻塞：watchdog 在自己的后台线程运行。"""
        if not self._watch_dir.exists():
            # 目录不存在时先创建，避免 watchdog 报错
            self._watch_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"监听目录不存在，已自动创建：{self._watch_dir}")

        handler = _LogFileHandler(self)
        # recursive=False：只监听当前目录，不递归子目录（EVE 日志是平铺的）
        self._observer.schedule(handler, str(self._watch_dir), recursive=False)
        self._observer.daemon = True  # 守护线程：主程序退出时自动结束
        self._observer.start()
        logger.info(f"日志监视器已启动，监听目录：{self._watch_dir}")

    def stop(self) -> None:
        """停止监听并释放资源（优雅退出）。"""
        self._observer.stop()
        self._observer.join(timeout=3)  # 最多等 3 秒让后台线程收尾
        logger.info("日志监视器已停止")

    def handle_file_change(self, file_path: Path) -> None:
        """
        某个日志文件发生变化：读取新增行并广播。

        实现原理：
            记住上次读到的字节位置，本次从该位置继续读，
            只把"新增的内容"按行广播，避免重复处理旧日志。
        """
        try:
            # 以二进制模式打开，用字节偏移定位最可靠（避免编码干扰）
            with open(file_path, "rb") as f:
                last_pos = self._file_positions.get(file_path, 0)
                f.seek(0, 2)                 # 移动到文件末尾
                current_size = f.tell()      # 当前文件大小

                # 文件被截断/重建（EVE 有时会清空日志）：从头读
                if current_size < last_pos:
                    last_pos = 0

                if current_size == last_pos:
                    return  # 没有新增内容

                f.seek(last_pos)
                new_bytes = f.read()
                self._file_positions[file_path] = f.tell()

            # EVE 日志通常为 UTF-16 LE 编码；解码失败时用 errors="replace" 兜底
            try:
                text = new_bytes.decode("utf-16-le")
            except UnicodeDecodeError:
                text = new_bytes.decode("utf-8", errors="replace")

            # 按行广播给所有订阅者
            for line in text.splitlines():
                if line.strip():  # 跳过空行
                    self._broadcast(line)

        except OSError as e:
            # 文件可能正好被 EVE 占用/删除，只记日志不抛异常
            logger.error(f"读取日志文件失败 {file_path.name}：{e}")

    def _broadcast(self, line: str) -> None:
        """把一行日志推送给所有订阅者。"""
        with self._lock:
            subscribers = list(self._subscribers)  # 拷贝一份，缩短持锁时间

        for callback in subscribers:
            try:
                callback(line)
            except Exception as e:  # noqa: BLE001 —— 单个订阅者出错不影响其他人
                logger.error(f"订阅者回调异常（已拦截）：{e}")
