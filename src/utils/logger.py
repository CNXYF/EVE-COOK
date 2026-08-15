"""
============================================================
模块：logger.py —— 统一日志工具
------------------------------------------------------------
功能说明：
    封装 Python 标准库 logging，提供全项目统一的日志接口。
    - 日志同时输出到"控制台"和"日志文件"（logs/ 目录）。
    - 各层（services/core/data）都通过 get_logger() 获取日志器，
      保证格式一致、便于排查问题。
    小白理解：日志就是程序的"日记本"，出错时翻日记找原因。
============================================================
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from utils.constants import LOG_DIR, APP_NAME


def _ensure_log_dir() -> Path:
    """
    确保日志目录存在。
    如果 logs/ 文件夹不存在就自动创建，避免写日志时报错。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def get_logger(name: str = APP_NAME) -> logging.Logger:
    """
    获取一个配置好的日志器（Logger）。

    参数：
        name: 日志器名称，一般传当前模块名，便于区分日志来源。

    返回：
        logging.Logger: 已配置好输出格式与目标的日志器对象。

    说明：
        - 同一个 name 多次调用会复用已有配置，不会重复添加 handler。
        - 日志文件采用 RotatingFileHandler：单文件超过 1MB 自动轮转，
          最多保留 3 个备份，防止日志无限膨胀。
    """
    logger = logging.getLogger(name)

    # 如果已经配置过（有 handler），直接复用，避免重复输出
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # 捕获所有级别，具体输出由 handler 决定

    # 统一日志格式：时间 | 级别 | 模块名 | 内容
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- 输出到控制台（开发调试时直接看） ----
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ---- 输出到文件（出问题时回查） ----
    log_dir = _ensure_log_dir()
    file_handler = RotatingFileHandler(
        filename=log_dir / f"{APP_NAME}.log",
        maxBytes=1024 * 1024,   # 单文件最大 1MB
        backupCount=3,          # 最多保留 3 个历史文件
        encoding="utf-8",       # 用 utf-8 防止中文乱码
    )
    file_handler.setLevel(logging.INFO)  # 文件只记录 INFO 及以上，减少噪音
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
