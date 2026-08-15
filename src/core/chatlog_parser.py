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
from typing import Optional, List, Iterable

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

# ---------- 进出星系事件正则 ----------
# 国服格式："玩家 进入星系 某某星系" / "玩家 离开星系 某某星系"
_LOCAL_EVENT_PATTERN_CN = re.compile(
    r"^(?P<player>.+?)\s+(?P<type>进入|离开)星系\s+(?P<system>.+?)$"
)
# 欧服格式："Player has entered system XXX" / "Player has left the system XXX"
_LOCAL_EVENT_ENTER_PATTERN_EN = re.compile(
    r"^(?P<player>.+?)\s+has entered system\s+(?P<system>.+?)$"
)
_LOCAL_EVENT_LEAVE_PATTERN_EN = re.compile(
    r"^(?P<player>.+?)\s+has left the system\s+(?P<system>.+?)$"
)

# ---------- 星系 ID 代号正则（EVE 空星系编号形态多样化）----------
# 典型格式：OBK-K8（3-2）、GE-8JV（2-3）、6-CZ49（1-5）、H-5GU（1-4）、1DQ1-A（4-1）
# 规则：
#   左半 1~6 字母数字 + 连字符 + 右半 1~6 字母数字
#   整体前后两侧不能紧邻字母数字（保证是"一个词"而不是长片段的中间）
#   末尾可选跟 *（星系名高亮标记），结果里不包含 *
_SYSTEM_ID_PATTERN = re.compile(
    r"(?<![A-Z0-9])[A-Z0-9]{1,6}-[A-Z0-9]{1,6}(?=\*)?(?![A-Z0-9])",
    re.IGNORECASE,
)


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


@dataclass
class LocalEvent:
    """
    本地频道进出星系事件的数据结构。

    字段：
        type:   事件类型，"enter" 表示进入星系，"leave" 表示离开星系
        player: 触发事件的玩家名称
        system: 星系名称
    """
    type: str
    player: str
    system: str


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


def extract_local_event(message: ChatMessage) -> Optional[LocalEvent]:
    """
    从系统消息中解析进出星系事件。

    仅在 message.is_system 为 True 时尝试解析，否则直接返回 None。
    支持国服和欧服两种消息格式。

    参数：
        message: 聊天消息对象

    返回：
        LocalEvent: 解析成功时返回事件对象（type 为 "enter"/"leave"）
        None: 非系统消息或不是进出事件时返回
    """
    if not message.is_system:
        return None

    content = message.content.strip()

    # ---- 国服格式：玩家 进入/离开星系 星系名 ----
    match = _LOCAL_EVENT_PATTERN_CN.match(content)
    if match:
        event_type = "enter" if match.group("type") == "进入" else "leave"
        return LocalEvent(
            type=event_type,
            player=match.group("player").strip(),
            system=match.group("system").strip().rstrip("*"),
        )

    # ---- 欧服格式：进入事件 ----
    match = _LOCAL_EVENT_ENTER_PATTERN_EN.match(content)
    if match:
        return LocalEvent(
            type="enter",
            player=match.group("player").strip(),
            system=match.group("system").strip().rstrip("*"),
        )

    # ---- 欧服格式：离开事件 ----
    match = _LOCAL_EVENT_LEAVE_PATTERN_EN.match(content)
    if match:
        return LocalEvent(
            type="leave",
            player=match.group("player").strip(),
            system=match.group("system").strip().rstrip("*"),
        )

    return None


def match_hostile(players: Iterable[str], hostile_list: Iterable[str]) -> List[str]:
    """
    不区分大小写比对玩家列表与敌对名单，返回匹配到的敌对子集。

    匹配规则：双方均转为小写后比对，返回结果保留 players 中的原始大小写。
    若同一玩家（忽略大小写）在 players 中出现多次，结果中也会保留多次。

    参数：
        players:      待检测的玩家名称集合
        hostile_list: 敌对玩家名单

    返回：
        List[str]: 匹配到的敌对玩家列表（来自 players，保留原始大小写）
    """
    hostile_lower = {name.lower() for name in hostile_list}
    result: List[str] = []
    for player in players:
        if player.lower() in hostile_lower:
            result.append(player)
    return result


def extract_system_names_from_text(content: str) -> List[str]:
    """
    从 intel 文本中初步提取星系 ID 代号。

    提取规则：匹配形如 [A-Z]{3}-[A-Z0-9]{3} 的星系代号（如 OBK-K8），
    允许末尾带可选的 * 号（但结果中不包含 *），返回匹配到的大写字符串列表。

    参数：
        content: 任意文本内容（如玩家聊天发送的 intel 报告）

    返回：
        List[str]: 匹配到的星系 ID 列表（大写，按出现顺序，不自动去重）
    """
    matches = _SYSTEM_ID_PATTERN.findall(content)
    return [m.upper() for m in matches]


def listener_id_from_file(file_path: Path) -> Optional[str]:
    """
    从日志文件名解析"监听者ID"（即角色的数字 ID）。

    文件名规律：频道名_日期_时间_监听者ID.txt
    例如 "本地_20260323_232140_2117006221.txt" -> "2117006221"
         "southeast.imperium_20260323_232140_2117006221.txt" -> "2117006221"

    参数：
        file_path: 日志文件路径。

    返回：
        str: 监听者ID（纯数字字符串）；无法识别时返回 None。
    """
    stem = file_path.stem  # 文件名去掉 .txt 后缀
    parts = stem.split("_")

    # 合法规律：至少 4 段，倒数第 3 段为 8 位日期，倒数第 2 段为 6 位时间，
    # 最后 1 段为纯数字监听者ID
    if len(parts) >= 4 and len(parts[-3]) == 8 and parts[-3].isdigit() \
            and len(parts[-2]) == 6 and parts[-2].isdigit() \
            and parts[-1].isdigit():
        return parts[-1]

    return None


def scan_channels(log_dir: Path) -> List[str]:
    """
    扫描 Chatlogs 目录，提取所有不同的频道名。

    用途：让用户在界面上看到"当前有哪些频道可监控"，再勾选要监控的频道。
    不区分监听者ID（多开角色时同一频道会出现多份日志，只取唯一频道名）。

    参数：
        log_dir: Chatlogs 目录路径。

    返回：
        List[str]: 去重后的频道名列表，按字母/拼音顺序排序。
                   目录不存在或无日志时返回空列表。
    """
    if not log_dir.exists() or not log_dir.is_dir():
        logger.debug(f"频道扫描：目录不存在或非目录 {log_dir}")
        return []

    channels: set = set()
    try:
        for txt_file in log_dir.glob("*.txt"):
            name = channel_name_from_file(txt_file)
            if name:
                channels.add(name)
    except OSError as e:
        logger.error(f"扫描频道目录失败 {log_dir}：{e}")
        return []

    # 排序返回（中文频道名按 Unicode 排序，可读性尚可）
    return sorted(channels)
