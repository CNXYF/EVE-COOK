# EVE-COOK

EVE Online 桌面辅助工具：Local/Intel 频道监控、无人机状态监控、跳数计算、语音预警。

> 面向编程小白的说明文档。每一步都尽量写清楚"做什么、为什么、怎么做"。

---

## 一、这个项目是干什么的？

`EVE-COOK` 是一个运行在 Windows 上的 EVE Online 辅助桌面工具，主要功能：

| 功能 | 说明 |
| --- | --- |
| Local 频道监控 | 实时监视本地频道人员变化，发现危险玩家时预警 |
| Intel 频道监控 | 监视情报频道关键字，出现威胁词时弹出悬浮预警 |
| 无人机状态监控 | 通过截图识别无人机状态，异常时提醒 |
| 跳数计算 | 基于本地 SDE 星图数据，计算两个星系之间的跳数 |
| 语音预警 | 用 TTS 语音 + 音效播报危险信息 |

---

## 二、技术栈（为什么选这些？）

- **UI 框架：PyQt5** —— 用来画界面。注意：本项目固定用 PyQt5，不用 PySide6。
- **样式：QSS 深色科技风** —— 背景 `#0a0e14`，主色 `#00d4aa`。
- **并发：QThread + Signal/Slot** —— 后台干活、前台显示，互不卡死。
- **文件监控：watchdog** —— 用"观察者模式"监听日志文件变化，不用轮询。
- **Windows API：pywin32** —— 枚举窗口、截图。⚠️ 仅限 Windows。
- **图算法：networkx** —— 计算星系间跳数。
- **音频/TTS：pyttsx3 + playsound** —— 语音播报和音效。
- **数据：JSON（配置）、SQLite/Pickle（SDE 星图）**。
- **打包：PyInstaller** —— 把脚本打包成 `.exe`。

---

## 三、环境要求

- **操作系统：Windows 10 / 11**（EVE 客户端只支持 Windows）
- **Python：3.10 或 3.11**（不要用 3.12，部分依赖有兼容性问题）
- **Git**：用于拉取代码

检查版本（在 PowerShell 里输入）：

```powershell
python --version   # 应显示 3.10.x 或 3.11.x
git --version
```

---

## 四、安装步骤（小白版）

### 1. 克隆仓库到本地

```powershell
git clone https://github.com/CNXYF/EVE-COOK.git
cd EVE-COOK
```

### 2. 创建并激活虚拟环境

虚拟环境就像一个"独立的小房间"，装的依赖不会污染你电脑上的其他项目。

```powershell
# 创建虚拟环境（只需一次）
python -m venv venv

# 激活虚拟环境（每次打开新终端都要执行一次）
.\venv\Scripts\Activate.ps1
```

> ⚠️ 如果提示"禁止运行脚本"，先执行一次：
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，输入 `Y` 确认。

激活成功后，命令行前面会出现 `(venv)` 字样。

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

> 如果下载很慢，可以换国内镜像源：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 4. 运行程序

```powershell
python src/main.py
```

---

## 五、目录结构说明

```
EVE-COOK/
├── src/
│   ├── main.py              # 程序入口（含中文启动流程注释）
│   ├── ui/                  # UI 层：只负责画界面、发信号
│   │   ├── main_window.py   # 主窗口
│   │   ├── tabs/            # 功能选项卡
│   │   ├── widgets/         # 自定义控件
│   │   └── styles/          # QSS 样式文件
│   ├── services/            # 服务层：后台线程，通过信号与 UI 通信
│   │   ├── base_service.py  # 服务基类（含线程安全示例）
│   │   ├── service_manager.py
│   │   ├── local_monitor.py
│   │   ├── intel_monitor.py
│   │   ├── drone_monitor.py
│   │   └── translation_service.py
│   ├── core/                # 核心引擎层：纯逻辑，不依赖 PyQt5
│   │   ├── log_watcher.py
│   │   ├── window_enumerator.py
│   │   ├── jump_calculator.py
│   │   └── audio_manager.py
│   ├── data/                # 数据层：配置、SDE 加载、数据模型
│   │   ├── config_manager.py
│   │   ├── sde_loader.py
│   │   └── models/
│   └── utils/               # 工具：日志、常量
│       ├── logger.py
│       └── constants.py
├── requirements.txt
├── README.md
└── .gitignore
```

### 分层架构（为什么要分层？）

把代码按"职责"分开，就像餐厅里"前台服务员、后厨、仓库"各司其职：

1. **UI 层（ui/）**：只负责显示和接收用户操作，绝不直接读写文件或发网络请求。
2. **服务层（services/）**：后台线程，干活的地方，通过"信号"把结果告诉 UI。
3. **核心引擎层（core/）**：纯逻辑工具，不依赖 PyQt5，方便单独测试。
4. **数据层（data/）**：管理配置和数据加载。

---

## 六、常见问题（FAQ）

**Q1：运行报 `ModuleNotFoundError: No module named 'PyQt5'`？**
A：说明没激活虚拟环境，或没装依赖。先 `.\venv\Scripts\Activate.ps1`，再 `pip install -r requirements.txt`。

**Q2：报"禁止运行脚本"？**
A：执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 并确认。

**Q3：pywin32 安装失败？**
A：确认 Python 是 3.10/3.11 且为 Windows 系统；可尝试升级 pip：`python -m pip install --upgrade pip`。

---

## 七、许可证

仅供学习与个人使用。请遵守 EVE Online 用户协议（EULA）。
