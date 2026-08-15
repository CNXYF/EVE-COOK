"""
============================================================
模块：core/chatlog_parser.py —— EVE 聊天日志解析器
------------------------------------------------------------
功能说明：
    解析 EVE 客户端（国服）聊天日志的每一行内容，
    并从日志文件名中识别所属频道。

    真实日志格式（已通过本机日志验证）：
    - 文件编码：UTF-16 LE（带 BOM），每条消息行首可能带 \\ufeff
    - 文件名：  频道名_日期_时间_监听者ID.txt
                例如 本地_20260323_232140_2117006221.txt
    - 消息行：  [ 2026.03.23 23:21:44 ] 发送者 > 消息内容
    - 系统消息：发送者为 "EVE系统"，例如
                EVE系统 > 频道更换为本地：OBK-K8*

    强制约束：本层为纯逻辑，不依赖 PyQt5，可独立测试。
============================================================
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger("chatlog_parser")

# ---------- 消息行正则 ----------
# 匹配形如 "[ 2026.03.23 23:21:44 ] 发送者 > 内容" 的行：
#   (?P<xxx>...) 是"命名分组"，解析后可以直接按名字取内容
_MESSAGE_PATTERN = re.compile(
    r"^\[\s*(?P<timestamp>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]\s*"
    r"(?P<sender>.+?)\s*>\s*(?P<content>.*)$"
)

# ---------- 系统消息发送者名称 ----------
# 国服为 "EVE系统"，欧服为 "EVE System"，两个都兼容
SYSTEM_SENDERS = {"EVE系统", "EVE System"}

# ---------- 本地频道"切换星系"消息的前缀 ----------
# 国服：频道更换为本地：星系名*     欧服：Channel changed to Local: 星系名*
_LOCAL_CHANGE_PREFIX_CN = "频道更换为本地："
_LOCAL_CHANGE_PREFIX_EN = "Channel changed to Local: "


@dataclass
class ChatMessage:
    """
    一条聊天消息的数据结构。

    字段：
        timestamp: 消息时间（原始字符串，如 "2026.03.23 23:21:44"）
        sender:    发送者名称（玩家名或 "EVE系统"）
        content:   消息正文
        channel:   所属频道名（从日志文件名解析得到）
    """
    timestamp: str
    sender: str
    content: str
    channel: str = ""

    @property
    def is_system(self) -> bool:
        """是否为系统消息（发送者是 EVE系统/EVE System）。"""
        return self.sender in SYSTEM_SENDERS


def parse_line(line: str, channel: str = "") -> Optional[ChatMessage]:
    """
    解析一行日志为 ChatMessage。

    参数：
        line: 日志中的一行文本（可以带 BOM/空白，内部会清理）
        channel: 该行所属频道名（可选，用于填充结果）

    返回：
        ChatMessage: 解析成功时返回消息对象
        None: 不是消息行时返回（文件头、分隔线、空行等）
    """
    # 清理行首的 BOM 字符（\ufeff）和首尾空白
    # EVE 日志每条消息行首都可能带一个 BOM，必须先去掉再匹配
    cleaned = line.lstrip("\ufeff").strip()
    if not cleaned:
        return None

    match = _MESSAGE_PATTERN.match(cleaned)
    if match is None:
        # 不是消息行（比如文件头部的 Channel ID 信息、分隔线）
        return None

    return ChatMessage(
        timestamp=match.group("timestamp"),
        sender=match.group("sender").strip(),
        content=match.group("content").strip(),
        channel=channel,
    )


def channel_name_from_file(file_path: Path) -> str:
    """
    从日志文件名解析频道名。

    文件名规律：频道名_日期_时间_监听者ID.txt
    例如 "本地_20260323_232140_2117006221.txt" -> "本地"
         "southeast.imperium_20260323_232140_2117006221.txt"
             -> "southeast.imperium"

    参数：
        file_path: 日志文件路径。

    返回：
        str: 频道名；无法识别时返回去掉扩展名的完整文件名。
    """
    stem = file_path.stem          # 文件名去掉 .txt 后缀
    parts = stem.split("_")

    # 倒数第 3 段应为 8 位日期（如 20260323），据此定位频道名边界
    # 频道名本身可能含下划线，所以用 "_".join 把前面的段拼回去
    if len(parts) >= 4 and len(parts[-3]) == 8 and parts[-3].isdigit():
        return "_".join(parts[:-3])

    # 不符合命名规律，兜底返回整个文件名（不含扩展名）
    logger.debug(f"日志文件名不符合常规命名：{file_path.name}")
    return stem


def extract_local_system(content: str) -> Optional[str]:
    """
    从"切换本地频道"的系统消息中提取星系名。

    参数：
        content: 消息正文，例如 "频道更换为本地：OBK-K8*"

    返回：
        str: 星系名（已去掉结尾的 * 号），例如 "OBK-K8"
        None: 该消息不是切换星系消息
    """
    for prefix in (_LOCAL_CHANGE_PREFIX_CN, _LOCAL_CHANGE_PREFIX_EN):
        if content.startswith(prefix):
            system_name = content[len(prefix):].strip()
            # EVE 在星系名后附加 * 号（表示主权星系），去掉得到纯星系名
            return system_name.rstrip("*").strip()
    return None
