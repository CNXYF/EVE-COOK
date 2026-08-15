"""
============================================================
模块：services/translation_service.py —— 翻译服务（事件驱动型）
------------------------------------------------------------
功能说明：
    订阅 LogWatcher 的日志行事件，实时监听 EVE 聊天频道中的外文消息，
    调用 MyMemory 免费翻译 API 将其翻译成中文，并通过信号发射翻译结果。

    设计特点：
    - 事件驱动：不再依赖 submit 队列，直接订阅 LogWatcher 回调
    - 频道白名单：可指定只翻译特定频道，空列表表示监控所有频道
    - 中文检测：主要内容为中文（>=30% 中文字符）的消息自动跳过
    - 结果缓存：相同原文不重复请求 API，减少网络调用

    强制约束：
    - 网络请求必须设置 timeout >= 5s（使用 constants.HTTP_TIMEOUT）
    - 翻译结果必须缓存（用 dict 做简单缓存，避免重复请求）
    - 所有异常必须兜底捕获，绝不向外抛出影响 LogWatcher 广播

    🔒 线程安全说明：
      LogWatcher 的回调运行在 watchdog 后台线程，_on_log_line 会
      在该线程中执行；缓存字典只在 _on_log_line 内读写（单写者），
      无跨线程竞争；如未来多线程访问需加锁。
============================================================
"""
import re
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import pyqtSignal

from services.base_service import BaseService
from core.log_watcher import LogWatcher
from core.chatlog_parser import parse_line, channel_name_from_file, ChatMessage
from core.audio_manager import AudioManager
from utils.constants import HTTP_TIMEOUT
from utils.logger import get_logger

logger = get_logger("translation_service")

# 延迟导入 requests：网络库初始化慢，且允许未安装时模块仍可导入
try:
    import requests
except ImportError:
    requests = None
    logger.warning("requests 未安装，翻译功能不可用")

# 中文字符检测正则：匹配 Unicode 中日韩统一表意文字基本区 + 扩展 A
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


class TranslationService(BaseService):
    """
    翻译服务（事件驱动型）：订阅 LogWatcher，实时翻译聊天频道的外文消息。

    新增信号：
        sig_translation_ready(str, str, str, str): 翻译完成信号，
            四个参数依次为 (频道名, 发送者, 原文, 译文)。
    """

    # ---- Qt 信号：翻译完成（频道名, 发送者, 原文, 译文）----
    sig_translation_ready = pyqtSignal(str, str, str, str)

    def __init__(
        self,
        log_watcher: LogWatcher,
        target_channels: List[str],
        audio_manager: Optional[AudioManager] = None,
        parent=None,
    ):
        """
        初始化翻译服务。

        参数：
            log_watcher:      LogWatcher 实例，用于订阅日志行事件
            target_channels:  频道白名单（仅翻译列表中的频道）；
                              传空列表 [] 表示监控所有频道
            audio_manager:    AudioManager 实例（可选，预留用于未来 TTS 播报译文）
            parent:           Qt 父对象，一般传 None
        """
        super().__init__(service_name="Translation", parent=parent)

        # ---- 依赖注入 ----
        self._log_watcher = log_watcher          # 日志监视器（订阅源）
        self._target_channels: List[str] = list(target_channels)  # 频道白名单（拷贝一份防外部修改）
        self._audio_manager: Optional[AudioManager] = audio_manager  # 音频管理器（预留）

        # ---- 内部状态 ----
        self._cache: dict = {}                    # 翻译结果缓存：{原文: 译文}
        self._chinese_threshold: float = 0.30     # 中文比例阈值：>=30% 视为中文消息，跳过翻译

    # ============================================================
    # 线程主体：订阅 → 等待 → 取消订阅
    # ============================================================
    def run(self) -> None:
        """
        线程主体：订阅 LogWatcher 的日志行事件，然后循环等待停止指令。

        流程：
            1. 订阅 _on_log_line 回调到 LogWatcher
            2. 进入 msleep 循环，持续检查 _running 标志位
            3. 收到 stop() 后 _running=False，跳出循环
            4. finally 中取消订阅，确保资源释放
        """
        try:
            self.emit_log("INFO", "翻译服务已就绪")

            # ---- 第一步：订阅 LogWatcher 的日志行事件 ----
            # LogWatcher 每次检测到新日志行都会回调 _on_log_line(file_path, line)
            self._log_watcher.subscribe(self._on_log_line)

            # 白名单信息（便于调试）
            if self._target_channels:
                self.emit_log(
                    "INFO",
                    f"频道白名单已启用，仅翻译：{', '.join(self._target_channels)}",
                )
            else:
                self.emit_log("INFO", "未设置频道白名单，将监控所有频道")

            # ---- 第二步：循环等待停止指令 ----
            # 🔒 线程安全说明：循环检查 _running 标志位，响应 stop()
            # 事件驱动模型下本线程无需做其他事，只负责"活着"并响应停止
            while self._running:
                self.msleep(200)  # 短暂休眠，避免空转占用 CPU

        except Exception as e:  # noqa: BLE001 —— 异常通过信号发给 UI
            self.emit_error(f"翻译服务运行异常：{e}")
        finally:
            # ---- 第三步：无论如何都要取消订阅，防止内存泄漏 ----
            try:
                self._log_watcher.unsubscribe(self._on_log_line)
            except Exception as e:  # noqa: BLE001 —— 取消订阅失败只记日志
                logger.error(f"取消 LogWatcher 订阅失败：{e}")

            self.emit_log("INFO", "翻译服务已退出")
            self.sig_finished.emit(self.service_name)

    # ============================================================
    # LogWatcher 回调：处理每一行新日志
    # ============================================================
    def _on_log_line(self, file_path: Path, line: str) -> None:
        """
        LogWatcher 订阅回调：处理每一行新增的日志。

        ⚠️ 注意：此回调运行在 watchdog 的后台线程中，
        必须吞掉所有异常，绝不能向外抛出（否则会导致 LogWatcher 广播中断）。

        处理流程：
            1. 从文件名解析频道名 → 白名单过滤
            2. 解析日志行为 ChatMessage → 跳过系统消息/非玩家发言
            3. 中文检测 → 跳过主要由中文组成的消息
            4. 查缓存 → 命中直接发射结果
            5. 调用 MyMemory API 翻译 → 写缓存 → 发射结果
        """
        try:
            # ---- 1. 频道过滤：从日志文件名解析频道名 ----
            channel = channel_name_from_file(file_path)

            # 白名单非空时，只翻译指定频道；不在白名单则直接返回
            if self._target_channels and channel not in self._target_channels:
                return

            # ---- 2. 解析日志行为 ChatMessage ----
            message: Optional[ChatMessage] = parse_line(line, channel=channel)

            # 解析失败（非消息行，如文件头、分隔线）→ 跳过
            if message is None:
                return

            # 系统消息（EVE系统/EVE System）→ 跳过，只翻译玩家发言
            if message.is_system:
                return

            # 消息内容为空 → 跳过
            content = message.content.strip()
            if not content:
                return

            # ---- 3. 中文检测：主要由中文组成的消息跳过翻译 ----
            if self._is_mostly_chinese(content):
                return

            # ---- 4. 查缓存：命中直接发射结果，不再请求 API ----
            if content in self._cache:
                translated = self._cache[content]
                self.sig_translation_ready.emit(
                    channel, message.sender, content, translated
                )
                return

            # ---- 5. 调用 MyMemory 免费翻译 API ----
            translated = self._translate_via_mymemory(content)

            # 翻译失败（返回空字符串）→ 不发射信号，静默跳过
            if not translated:
                return

            # 写入缓存（即使译文为空，为避免下次重复请求，也可缓存；
            # 但这里仅缓存非空结果，因为空值可能是临时网络问题）
            self._cache[content] = translated

            # 发射翻译完成信号
            self.sig_translation_ready.emit(
                channel, message.sender, content, translated
            )

        except Exception as e:  # noqa: BLE001 —— 回调必须吞掉所有异常
            # 任何异常都只记日志，绝不向外抛出（否则影响其他订阅者）
            logger.error(f"翻译回调处理异常（已拦截）：{e}")

    # ============================================================
    # 内部工具：中文检测
    # ============================================================
    def _is_mostly_chinese(self, text: str) -> bool:
        """
        判断一段文本是否主要由中文组成。

        判断规则：
            统计文本中的中文字符数占"总非空白字符数"的比例，
            若 >= 30% 则视为"主要由中文组成"，跳过翻译。

        使用"非空白字符"做分母是为了避免空白/标点稀释比例。

        参数：
            text: 待检测文本

        返回：
            bool: True 表示主要是中文，应跳过翻译
        """
        try:
            # 去掉所有空白字符后计算有效字符总数
            non_whitespace = re.sub(r"\s+", "", text)
            total = len(non_whitespace)

            # 空文本视为"非中文"（上层也会跳过，但这里兜底）
            if total == 0:
                return False

            # 统计中文字符数
            chinese_chars = _CJK_PATTERN.findall(non_whitespace)
            chinese_count = len(chinese_chars)

            # 计算比例并与阈值比较
            ratio = chinese_count / total
            return ratio >= self._chinese_threshold

        except Exception as e:  # noqa: BLE001 —— 检测失败兜底：当作非中文，继续翻译
            logger.error(f"中文检测异常（默认继续翻译）：{e}")
            return False

    # ============================================================
    # 内部工具：调用 MyMemory 翻译 API
    # ============================================================
    def _translate_via_mymemory(self, text: str) -> str:
        """
        调用 MyMemory 免费翻译 API，将文本翻译为简体中文。

        API 说明：
            - 接口：GET https://api.mymemory.translated.net/get
            - 参数：
                q:        待翻译文本（URL 编码后拼入 URL）
                langpair: 语言对，格式 "源语言|目标语言"，这里固定 "en|zh-CN"
            - 响应 JSON 中 responseData.translatedText 即译文

        异常处理：
            - requests 未安装 → 返回空字符串
            - 超时 / HTTP 错误 / 网络异常 / JSON 解析失败 → 返回空字符串

        参数：
            text: 待翻译原文

        返回：
            str: 翻译后的中文文本；失败时返回空字符串 ""
        """
        # requests 未安装 → 直接返回空
        if requests is None:
            self.emit_error("requests 未安装，无法执行翻译")
            return ""

        try:
            # 构造请求 URL：text 会被 requests 自动 URL 编码（params 参数方式更安全）
            # 这里用 params 传参，避免手动拼接 URL 时特殊字符出错
            url = "https://api.mymemory.translated.net/get"
            params = {
                "q": text,
                "langpair": "en|zh-CN",  # 固定：从英文翻译到简体中文
            }

            # 发送 GET 请求，设置超时（强制约束：timeout >= HTTP_TIMEOUT）
            response = requests.get(
                url=url,
                params=params,
                timeout=HTTP_TIMEOUT,
            )

            # 非 2xx 状态码 → 主动抛 HTTPError
            response.raise_for_status()

            # 解析 JSON 响应
            data = response.json()

            # 从嵌套结构中取出译文：responseData → translatedText
            response_data = data.get("responseData", {})
            translated = response_data.get("translatedText", "")

            # 译文可能是 None 或空白，做一次清理
            translated = (translated or "").strip()

            return translated

        except requests.Timeout:
            # 超时：网络慢或接口无响应
            self.emit_error(f"翻译超时（>{HTTP_TIMEOUT}s）：{text[:30]}...")
        except requests.HTTPError as e:
            # 接口返回错误状态码（4xx/5xx）
            self.emit_error(f"翻译接口返回错误：{e}")
        except requests.RequestException as e:
            # 其他网络异常（断网、DNS 失败等）
            self.emit_error(f"翻译网络请求失败：{e}")
        except ValueError as e:
            # response.json() 解析失败（接口返回了非 JSON 内容）
            self.emit_error(f"翻译结果解析失败：{e}")
        except Exception as e:  # noqa: BLE001 —— 兜底：任何未知异常
            logger.error(f"MyMemory 翻译未知异常：{e}")
            self.emit_error(f"翻译未知异常：{e}")

        # 任何异常都返回空字符串
        return ""
