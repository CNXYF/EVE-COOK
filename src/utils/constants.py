"""
============================================================
模块：constants.py —— 全局常量定义
------------------------------------------------------------
功能说明：
    把整个项目会用到的"固定值"集中放在这里，
    避免在代码里散落各种"魔法字符串"（写死且含义不明的字符串）。
    小白理解：常量就像给某个数字/文字起了个好记的名字，
              以后要改只需改这一处。
============================================================
"""
import os
from pathlib import Path

# ---------- 应用基本信息 ----------
APP_NAME = "EVE-COOK"          # 应用名称（显示在窗口标题等位置）
APP_VERSION = "0.1.0"          # 版本号（语义化版本：主.次.修订）

# ---------- 路径相关（统一用 pathlib.Path，禁止字符串拼接路径） ----------
# Path(__file__) 指向当前文件，.parent 逐级向上找到项目根目录
# 目录结构：项目根/src/utils/constants.py -> 向上三级即项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"                    # 源码目录
DATA_DIR = PROJECT_ROOT / "data"                  # 运行时数据目录（配置/SDE）
CONFIG_DIR = DATA_DIR / "config"                  # 配置文件目录
CONFIG_FILE = CONFIG_DIR / "app_config.json"      # 主配置文件路径
SDE_DIR = DATA_DIR / "sde"                        # SDE 星图数据目录
LOG_DIR = PROJECT_ROOT / "logs"                   # 日志输出目录

# ---------- UI 主题色（QSS 深色科技风） ----------
COLOR_BG = "#0a0e14"           # 背景色（深蓝黑）
COLOR_PRIMARY = "#00d4aa"      # 主色（青绿色）
COLOR_TEXT = "#c5c8c6"         # 普通文字颜色
COLOR_ERROR = "#ff5555"        # 错误日志颜色（红）
COLOR_WARN = "#f1fa8c"         # 警告日志颜色（黄）
COLOR_INFO = "#8be9fd"         # 信息日志颜色（青）

# ---------- EVE 客户端相关 ----------
# 真实窗口类名（通过本机 pywin32 枚举实测）：
#   - 游戏主窗口："trinityWindow"（国服/欧服通用，最可靠的匹配依据）
#   - 历史上老版本/启动器可能使用过 "EVE"，保留兼容
# ⚠️ 注意：仅限 Windows 系统
EVE_WINDOW_CLASSES = ("trinityWindow", "EVE")  # 窗口类名集合，任一命中就算
EVE_WINDOW_TITLE_KEYWORD = "EVE"  # 窗口标题关键字（实测标题为 "EVE - 角色名"，不包含 Online）
EVE_WINDOW_TITLE_ALTERNATIVES = ("EVE", "EVE Online")  # 标题备用关键字，做双保险

# EVE 聊天日志默认目录：文档\EVE\logs\Chatlogs
# （与客户端安装位置无关，国服/欧服都放在"文档"下）
# ⚠️ 注意：仅限 Windows 系统（使用 USERPROFILE 环境变量）
DEFAULT_CHATLOGS_DIR = Path(os.environ.get("USERPROFILE", "")) / "Documents" / "EVE" / "logs" / "Chatlogs"

# 本地频道的可能名称（国服从"本地"，欧服叫 "Local"）
# 用集合存放，判断时用 `in` 即可，避免写死单一名称
LOCAL_CHANNEL_NAMES = {"本地", "Local"}

# ---------- 网络请求 ----------
HTTP_TIMEOUT = 5               # 网络请求超时秒数（强制约束：>=5s）

# ---------- 日志级别 ----------
LOG_LEVEL_DEBUG = "DEBUG"
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"
