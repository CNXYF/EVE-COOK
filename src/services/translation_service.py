"""
============================================================
模块：services/translation_service.py —— 翻译服务
------------------------------------------------------------
功能说明：
    把 Intel 频道里的外文内容翻译成中文，方便快速阅读。

    强制约束：
    - 网络请求必须设置 timeout >= 5s
    - 网络请求必须在子线程执行（本服务本身就是 QThread）
    - 翻译结果必须缓存（用 dict 做简单缓存，避免重复请求）

    🔒 线程安全说明：
      缓存字典只在本服务线程内读写（请求与写缓存都在 run 循环中），
      无跨线程竞争；如未来多线程访问需加锁。
============================================================
"""
from PyQt5.QtCore import pyqtSignal

from services.base_service import BaseService
from utils.constants import HTTP_TIMEOUT
from utils.logger import get_logger

logger = get_logger("translation_service")

# 延迟导入 requests：网络库初始化慢，且允许未安装时模块仍可导入
try:
    import requests
except ImportError:
    requests = None
    logger.warning("requests 未安装，翻译功能不可用")


class TranslationService(BaseService):
    """
    翻译服务：接收待翻译文本队列，逐个请求翻译接口并返回结果。

    新增信号：
        sig_translation_ready(str, str): 翻译完成信号，
                                         参数为 (原文, 译文)。
    """

    sig_translation_ready = pyqtSignal(str, str)  # (原文, 译文)

    def __init__(self, parent=None):
        """初始化翻译服务与结果缓存。"""
        super().__init__(service_name="Translation", parent=parent)
        # 翻译结果缓存：{原文: 译文}，命中缓存直接返回，不再发请求
        self._cache: dict = {}
        # 待翻译队列：UI 通过 submit() 投递文本，run 循环逐个处理
        self._pending: list = []

    def submit(self, text: str) -> None:
        """
        提交一段待翻译文本（UI 或其他服务调用）。

        参数：
            text: 需要翻译的原文。
        """
        if text and text.strip():
            self._pending.append(text.strip())

    def run(self) -> None:
        """线程主体：循环处理待翻译队列。"""
        try:
            self.emit_log("INFO", "翻译服务已就绪")

            # 🔒 线程安全说明：循环检查 _running 标志位，响应 stop()
            while self._running:
                if self._pending:
                    text = self._pending.pop(0)  # 取出最早提交的一条
                    self._translate(text)
                else:
                    self.msleep(100)  # 队列为空时短暂休眠，避免空转

        except Exception as e:  # noqa: BLE001 —— 异常通过信号发给 UI
            self.emit_error(f"翻译服务运行异常：{e}")
        finally:
            self.emit_log("INFO", "翻译服务已退出")
            self.sig_finished.emit(self.service_name)

    def _translate(self, text: str) -> None:
        """
        执行单条翻译：先查缓存，未命中再请求网络接口。

        参数：
            text: 待翻译原文。
        """
        # ---- 第一步：查缓存（强制约束：翻译结果必须缓存） ----
        if text in self._cache:
            self.sig_translation_ready.emit(text, self._cache[text])
            return

        # ---- 第二步：网络请求（强制约束：timeout>=5s 且在子线程） ----
        if requests is None:
            self.emit_error("requests 未安装，无法执行翻译")
            return

        try:
            # 骨架阶段：翻译接口地址待配置，这里仅搭好请求流程
            # TODO: 接入真实翻译 API（如 DeepL / 百度翻译 / 有道）
            response = requests.post(
                url="https://example.com/api/translate",  # 占位地址，待替换
                json={"text": text, "target_lang": "zh"},
                timeout=HTTP_TIMEOUT,  # 强制约束：超时不低于 5 秒
            )
            response.raise_for_status()  # 非 2xx 状态码主动抛 HTTPError
            result = response.json().get("translation", "")

            # 写入缓存并发射结果信号
            self._cache[text] = result
            self.sig_translation_ready.emit(text, result)

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
