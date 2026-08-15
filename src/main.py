"""
============================================================
模块：main.py —— 程序入口
------------------------------------------------------------
功能说明：
    整个程序的启动流程都在这里串起来。

    启动流程（按顺序）：
    1. 把 src 目录加入模块搜索路径（保证各层能互相 import）
    2. 创建 QApplication（Qt 程序的"总开关"，必须最先创建）
    3. 加载 QSS 样式文件（深色科技风）
    4. 加载配置（ConfigManager）
    5. 创建核心引擎（LogWatcher / AudioManager）
    6. 创建并注册各后台服务（ServiceManager 统一管理）
    7. 创建主窗口并完成信号接线
    8. 进入 Qt 事件循环（程序开始运行）
============================================================
"""
import sys
from pathlib import Path

# ---- 第 1 步：设置模块搜索路径 ----
# 直接运行 python src/main.py 时，Python 默认只认识 src 目录，
# 把 src 加入 sys.path 后，才能用 `from services.xxx import ...`
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PyQt5.QtWidgets import QApplication  # noqa: E402 —— 必须在 sys.path 设置后导入

from core.audio_manager import AudioManager      # noqa: E402
from core.log_watcher import LogWatcher          # noqa: E402
from data.config_manager import ConfigManager    # noqa: E402
from services.drone_monitor import DroneMonitorService        # noqa: E402
from services.intel_monitor import IntelMonitorService        # noqa: E402
from services.local_monitor import LocalMonitorService        # noqa: E402
from services.service_manager import ServiceManager           # noqa: E402
from services.translation_service import TranslationService   # noqa: E402
from ui.main_window import MainWindow            # noqa: E402
from utils.constants import (                    # noqa: E402
    APP_NAME,
    DEFAULT_CHATLOGS_DIR,
    SRC_DIR as CONST_SRC_DIR,
)
from utils.logger import get_logger              # noqa: E402

logger = get_logger("main")


def load_stylesheet(app: QApplication) -> None:
    """
    加载 QSS 样式文件并应用到整个应用。

    参数：
        app: QApplication 实例。

    说明：QSS 文件随代码放在 ui/styles/ 目录，
    用 pathlib 定位路径（打包时需把该文件一并打包）。
    """
    qss_path = CONST_SRC_DIR / "ui" / "styles" / "dark_tech.qss"
    try:
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        logger.info("QSS 样式加载成功")
    except OSError as e:
        # 样式加载失败不影响程序运行，只记录警告
        logger.warning(f"QSS 样式加载失败，使用默认样式：{e}")


def main() -> None:
    """程序主入口：按启动流程逐步初始化。"""
    # ---- 第 2 步：创建 QApplication ----
    # 任何 Qt 程序有且只能有一个 QApplication，必须早于所有控件创建
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # ---- 第 3 步：加载深色科技风样式 ----
    load_stylesheet(app)

    # ---- 第 4 步：加载配置 ----
    config_manager = ConfigManager()
    config = config_manager.load()
    logger.info("配置加载完成")

    # ---- 第 5 步：创建核心引擎 ----
    # 日志监视目录定位规则（优先级从高到低）：
    #   1. 配置文件里手动指定的 eve_log_dir
    #   2. 默认路径：文档\EVE\logs\Chatlogs（国服/欧服通用）
    # ⚠️ 注意：EVE 聊天日志不在客户端安装目录，而在"文档"文件夹
    if config.monitor.eve_log_dir:
        watch_dir = Path(config.monitor.eve_log_dir)
    else:
        watch_dir = DEFAULT_CHATLOGS_DIR

    if not watch_dir.exists():
        logger.warning(
            f"未找到 EVE 日志目录：{watch_dir}。"
            "请确认已运行过 EVE 客户端，或在配置中手动指定 eve_log_dir"
        )

    log_watcher = LogWatcher(watch_dir)      # 日志监视器（观察者模式）
    audio_manager = AudioManager()           # 音频/TTS 管理器
    audio_manager.set_enabled(config.monitor.enable_voice)

    # ---- 第 6 步：创建并注册后台服务 ----
    service_manager = ServiceManager()
    service_manager.register(LocalMonitorService(log_watcher))
    service_manager.register(
        IntelMonitorService(
            log_watcher,
            audio_manager,
            config.monitor.danger_keywords,
            config.monitor.intel_channels,
        )
    )
    service_manager.register(DroneMonitorService())
    service_manager.register(TranslationService())

    # ---- 第 7 步：创建主窗口（内部完成信号接线） ----
    window = MainWindow(service_manager)
    window.show()

    logger.info(f"{APP_NAME} 启动完成，进入事件循环")

    # ---- 第 8 步：进入 Qt 事件循环 ----
    # exec_() 会一直运行，直到窗口关闭；返回值作为进程退出码
    exit_code = app.exec_()

    # 事件循环结束后再做一次兜底清理（正常关窗时已停过服务）
    service_manager.stop_all()
    sys.exit(exit_code)


# 程序入口守卫：只有直接运行本文件才执行 main()，
# 被其他模块 import 时不会自动启动
if __name__ == "__main__":
    main()
