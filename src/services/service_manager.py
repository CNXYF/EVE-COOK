"""
============================================================
模块：services/service_manager.py —— 服务生命周期管理器
------------------------------------------------------------
功能说明：
    统一管理所有后台服务（BaseService 子类）的"注册、启动、停止"。
    程序退出时由它负责把所有服务优雅地停掉，避免线程残留。

    通俗类比：
      ServiceManager 像"总调度室"，
      每个服务是一台机器，调度室负责统一开机、统一关机。

    🔒 线程安全说明：
      服务的注册/遍历在主线程完成；
      每个服务自身的启停由其内部标志位保证线程安全。
============================================================
"""
from typing import Dict, List

from services.base_service import BaseService
from utils.logger import get_logger

logger = get_logger("service_manager")


class ServiceManager:
    """
    服务管理器：集中管理所有 BaseService 实例的生命周期。
    """

    def __init__(self):
        """初始化一个空的服务注册表（字典：服务名 -> 服务实例）。"""
        self._services: Dict[str, BaseService] = {}

    def register(self, service: BaseService) -> None:
        """
        注册一个服务到管理器。

        参数：
            service: BaseService 的子类实例。

        说明：同名服务重复注册时，后者覆盖前者并记录警告。
        """
        name = service.service_name
        if name in self._services:
            logger.warning(f"服务 {name} 重复注册，将被覆盖")
        self._services[name] = service
        logger.info(f"已注册服务：{name}")

    def get(self, name: str) -> BaseService:
        """
        按名称获取服务实例。

        参数：
            name: 服务名称。
        返回：
            BaseService: 对应服务；不存在时返回 None。
        """
        return self._services.get(name)

    def start_all(self) -> None:
        """启动所有已注册的服务。"""
        for name, service in self._services.items():
            try:
                service.start_service()
            except RuntimeError as e:
                # QThread 启动失败（如线程对象已被销毁）
                logger.error(f"启动服务 {name} 失败：{e}")

    def stop_all(self, timeout_ms: int = 3000) -> None:
        """
        停止所有服务并等待线程结束（程序退出时调用）。

        参数：
            timeout_ms: 每个服务最长等待毫秒数。

        流程：先给所有服务发停止指令，再逐个等待线程收尾，
        这样比"停一个等一个"更快。
        """
        # 第一步：统一下达停止指令
        for name, service in self._services.items():
            try:
                service.stop()
            except Exception as e:  # noqa: BLE001 —— 退出阶段兜底
                logger.error(f"停止服务 {name} 时出错：{e}")

        # 第二步：逐个等待线程真正结束
        for name, service in self._services.items():
            if not service.wait_for_stop(timeout_ms):
                logger.warning(f"服务 {name} 未在 {timeout_ms}ms 内结束")

        logger.info("所有服务已停止")

    def list_services(self) -> List[str]:
        """返回所有已注册服务的名称列表（供 UI 展示状态）。"""
        return list(self._services.keys())
