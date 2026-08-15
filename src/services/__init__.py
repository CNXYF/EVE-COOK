"""
============================================================
模块：services 包初始化文件
------------------------------------------------------------
功能说明：
    services 是"服务层"，所有后台监控/翻译服务都在这里：
    - base_service.py          服务基类（QThread）
    - service_manager.py       服务生命周期管理器
    - local_monitor.py         Local 频道监控
    - intel_monitor.py         Intel 频道监控
    - drone_monitor.py         无人机状态监控
    - translation_service.py   翻译服务

    强制约束：
    - 所有服务继承 BaseService(QThread)
    - 必须实现 run() 和 stop()，支持优雅退出
    - 通过信号与 UI 通信，禁止直接操作 QWidget
============================================================
"""
