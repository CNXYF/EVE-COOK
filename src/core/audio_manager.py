"""
============================================================
模块：core/audio_manager.py —— 音频 / TTS 管理器
------------------------------------------------------------
功能说明：
    统一管理两类声音输出：
    1. TTS 语音播报（pyttsx3）—— 把文字读出来，如"本地频道出现危险玩家"
    2. 音效播放（playsound）—— 播放 .mp3/.wav 提示音

    🔒 线程安全说明：
      pyttsx3 的引擎实例不是线程安全的，
      每个线程必须拥有自己独立的引擎实例（官方文档明确要求）。
      因此本类不在 __init__ 里创建引擎，
      而是由调用方在自己的线程中调用 speak() 时按需创建。

    强制约束：本层为纯逻辑，不依赖 PyQt5。
============================================================
"""
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger("audio_manager")

# 延迟导入：pyttsx3 / playsound 初始化较慢，且可能因缺少依赖报错，
# 放到函数内部导入，保证模块本身可以被安全 import
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    logger.warning("pyttsx3 未安装，TTS 语音功能不可用")

try:
    from playsound import playsound
except ImportError:
    playsound = None
    logger.warning("playsound 未安装，音效播放功能不可用")


class AudioManager:
    """
    音频管理器：TTS 播报 + 音效播放。
    """

    def __init__(self, rate: int = 180, volume: float = 1.0):
        """
        参数：
            rate: TTS 语速（每分钟词数，中文场景 180 左右较清晰）
            volume: 音量 0.0 ~ 1.0
        """
        self._rate = rate
        self._volume = volume
        self._enabled = True  # 总开关：配置里可关闭语音

    def set_enabled(self, enabled: bool) -> None:
        """开启 / 关闭声音输出（对应配置项 enable_voice）。"""
        self._enabled = enabled

    def speak(self, text: str) -> None:
        """
        用 TTS 朗读一段文字。

        🔒 线程安全说明：
          每次调用都新建一个 pyttsx3 引擎实例并在用完后销毁。
          虽然略有开销，但这是官方推荐的多线程安全用法，
          避免多个服务线程共用一个引擎导致崩溃。

        参数：
            text: 要朗读的文字（如"注意，本地出现危险玩家"）
        """
        if not self._enabled:
            return

        if pyttsx3 is None:
            logger.warning("TTS 引擎不可用，跳过语音播报")
            return

        try:
            engine = pyttsx3.init()      # 在当前线程创建独立引擎
            engine.setProperty("rate", self._rate)
            engine.setProperty("volume", self._volume)
            engine.say(text)             # 把文字加入朗读队列
            engine.runAndWait()          # 阻塞直到朗读完毕
            engine.stop()                # 释放引擎资源
        except Exception as e:  # noqa: BLE001 —— 音频失败不应影响主流程
            logger.error(f"TTS 播报失败：{e}")

    def play_sound(self, sound_file: Path) -> None:
        """
        播放一个音效文件（.mp3 / .wav）。

        参数：
            sound_file: 音效文件路径。
        """
        if not self._enabled:
            return

        if playsound is None:
            logger.warning("playsound 不可用，跳过音效播放")
            return

        if not sound_file.exists():
            logger.warning(f"音效文件不存在：{sound_file}")
            return

        try:
            # playsound 第二个参数 False 表示异步播放（不阻塞当前线程）
            playsound(str(sound_file), False)
        except Exception as e:  # noqa: BLE001 —— 同上，音频失败只记日志
            logger.error(f"音效播放失败：{e}")
