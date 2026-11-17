# iOS RealRun

在 Windows 或 macOS 上模拟 iPhone/iPad GPS 定位，也可在电脑上的官方 Android Emulator 中沿路线推送 GPS 坐标。

项目使用 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) 连接 iOS 设备，并通过 Apple DVT `LocationSimulation` 注入定位。

Android 模式使用 Android SDK 的 ADB 与模拟器控制台，不需要连接 iPhone。它运行的是 Android APK，不是 iOS 应用。

### v1.4.4

- 修复 iPhone 启动时先经旧 USB 连接挂载镜像，导致 iOS 27 报 `RSDRequiredError` 的问题。挂载与定位均使用指定设备的 USB RSD 用户态隧道，普通权限即可运行。
- 先实际打开定位开发者服务；服务已可用时不再重复安装镜像。需要安装时通过 RSD 挂载，随后重新发现服务。
- 停止时先清除模拟定位、关闭定位通道，再释放隧道；清除失败会明确报错。
- 当前 USB 通道支持 iOS 17.4 及更新版本；已在 iOS 27.2.1 上验证短时路线推送和停止清理。

### v1.4.3

- 桌面版新建设置与命令行默认目标配速改为 5:00/km，对应约 3.3333 m/s、12 km/h。

### v1.4.2

- 修正路线段交界处按整数点数插值造成的瞬时速度异常，改为按 WGS84 路径的米数连续插值。
- 按真实经过时间推进距离，并补偿设备调用耗时；界面和 Android 速度使用一致的采样时间，设备确认后再发布位置。
- 增加“匀速”档；区分目标速度、即时配速与平均配速，同时显示单位换算。例如 4.8 m/s = 17.28 km/h ≈ 3′28″/km。
- 停止 Android 路线后将末位置的速度归零，保留轨迹与平均配速。

### v1.4.1

- 修复无窗口 Android 被固定为软件绘图的问题：自动模式优先使用电脑显卡，显卡初始化失败时尝试 SwiftShader 兼容模式；设置中可明确选择图形模式。
- 根据电脑可用内存和 CPU 分配 2560–4096 MB 内存与 1–4 核，避免固定依赖某台电脑的配置。
- 默认高分辨率虚拟手机按原始比例降低渲染尺寸并同步缩放 DPI，已有自定义尺寸与 DPI 保持不变。屏幕传输限制为 30 fps、4 Mbps，减少 CPU 编码负担。
- 不再转发无点击的鼠标悬停事件，减少 Android 输入队列积压。设置页增加“重启虚拟手机”，只重启选中的模拟器并保留数据。
- 优化不重建 AVD、不清除 App 数据；Android 图形模式在下次启动虚拟手机时生效。命令行可用 `start_android_cli.ps1 -Gpu auto` 或 `-Gpu swiftshader`。

### v1.4.0

- 新增 React 桌面工作台：工作台、应用、设置三个页面，使用系统 WebView2 显示，保留现有 Python 定位后端。
- 实时地图按设备接口成功接受的坐标更新，显示已走轨迹、当前位置、里程、配速和用时。支持跟随、放大和独立路径窗口；停止后保留轨迹。
- 内置紫金港、玉泉、海宁的 OpenStreetMap 校园离线底图，可切换在线底图。
- 应用页可下载并安装浙大体艺、钉钉的官方 APK；自动下载并校验官方 scrcpy，提供独立手机窗口完成 App 原生登录。
- 登录会话保留在固定 AVD 内；桌面端只保存用户确认登录的时间，不接收学号、手机号或密码。用户确认与 App 内定位验证分别显示。
- Android 模式按普通权限运行，iOS 模式提供管理员重启入口。关闭主窗口前先停止定位任务，单独关闭路径窗口不会结束任务。

构建后的桌面入口是 `dist\v1.4.4\iOSRealRun\iOSRealRun.exe`，同目录的 `_internal` 和 worker 需完整保留。

### v1.3.0

- 新增 Android 模拟器模式：列出虚拟设备、启动已有 AVD、安装本机 APK，并复用路线和配速设置。
- 新增程序内检查更新：从本项目 GitHub Releases 下载正式安装包，校验大小及 SHA256 后再启动安装向导。
- 停止和退出任务时界面保持响应；设备检查、镜像挂载和模拟任务按顺序运行，失败会明确显示。
- 自动保存设备类型、路线、速度、时长和 Android 设置，保存在 `%LOCALAPPDATA%\iOSRealRun\settings.json`。
- 主程序与 worker 共享打包依赖，减少重复解压；Windows 文件属性和安装程序使用统一的版本号。

源码中的版本功能需使用相应新版构建；发布页是否已有安装包，以 GitHub Release 为准。

---

## 下载与安装（推荐）

**[⬇️ 下载 iOS-RealRun-Setup.exe](https://github.com/Obladi0617/ios-realrun/releases/latest/download/iOS-RealRun-Setup.exe)** · [查看所有版本](https://github.com/Obladi0617/ios-realrun/releases)

下载后双击安装，**无需安装 Python**。安装完成后双击桌面 **iOS RealRun** 即可启动。

### 使用要求

| 项目       | 说明                                                           |
| ---------- | -------------------------------------------------------------- |
| 系统       | Windows 10/11 64 位                                            |
| iTunes     | iOS 模式需要，用于提供 Apple 设备驱动                           |
| 开发者模式 | 设备上开启一次即可长期生效（设置 → 隐私与安全性 → 开发者模式） |
| 数据线     | 连接后设备需解锁并点击“信任此电脑”                             |
| 亮屏       | 运行期间设备需保持解锁亮屏，建议把自动锁定设为“永不”           |
| iOS 版本   | 17.4 或更新版本，使用普通权限 USB RSD 通道                     |
| 设备数量   | 同时只连接一台 iOS 设备                                        |

### 使用步骤

1. 打开 **iOS RealRun**，在工作台选择 iPhone
2. 用数据线连接设备，解锁并点击“信任此电脑”
3. 点击 **检查设备** 确认连接正常
4. 选择路线、速度、运行时长和配速波动档位
5. 点击 **开始模拟**（程序会自动挂载开发者镜像并建立隧道）
6. 结束后点击 **停止** 或直接关闭窗口，程序会自动恢复真实定位

> 关闭应用会自动清除模拟定位并恢复真实 GPS。若异常退出未恢复，重启设备即可。
>
> 桌面工作台日志位于 `%LOCALAPPDATA%\iOSRealRun\desktop.log`，反馈问题时可提供该文件。

### Android 模拟器与 APK

新版桌面操作：在工作台选择 Android，点击“检查设备”启动或连接固定虚拟手机；在“应用”页点击“打开 / 登录”，在旁边的真实手机窗口完成首次协议与登录，再点击“我已完成登录”。返回工作台选择路线并开始定位。地图右上角可打开独立路径窗口，查看轨迹时仍可操作手机窗口。

Android 环境需要已安装 SDK 的 `emulator`、`platform-tools` 和 Android 15 Google APIs x86_64 镜像。SDK 自动查找失败时，在“设置”填写路径。首次创建 AVD 还需要 `cmdline-tools` 和 JDK；已有 AVD 不需要重建。高级参数中的固定数据目录与原来的 `start_android_cli.ps1` 共用，保留已安装 App 与登录状态。

支持 Google 官方 **Android Emulator**。第三方模拟器（雷电、MuMu、BlueStacks 等）的定位接口不同，当前没有适配。

1. 安装 Android SDK 的 `platform-tools`、`emulator` 和一个系统镜像，在 Android Studio 的 Device Manager 创建 AVD。
2. 在本程序顶部选择 **Android 模拟器（APK）**。SDK 目录可留空自动查找，也可手动选择（例如 `D:\Android\Sdk`）。
3. 点击 **列出虚拟设备**，把日志中的 AVD 名称填写到输入框，点击 **启动模拟器**。也可直接使用已启动的模拟器。
4. 单个模拟器不必填设备编号；多个模拟器同时运行时填写 `emulator-5554` 等具体编号。
5. 点击 **安装 APK** 选择本机安装包，然后在模拟器内打开 App、登录并授予它所需的定位权限。
6. 点击 **检查设备**，设置路线、速度和时长，再点击 **开始模拟**。

Android 模式的 **停止** 会停止坐标推送，模拟器保留最后一次位置；虚拟设备没有可供恢复的真实 GPS。默认目标里程来自 `config.yaml` 的 `speedVariation.targetDistance`（4000 米），时长设为 0 仍会在达到目标里程时停止。

APK 安装成功不等于 App 的全部功能兼容模拟器。小程序能否打开、定位是否被接受，需由目标 App 验证；此项目不修改 APK，也不修改 App 对设备或模拟定位的判断。

命令行示例（Windows，可用 SDK 路径替换示例）：

```powershell
.\venv\Scripts\python.exe worker.py --backend android --sdk D:\Android\Sdk --list-android
.\venv\Scripts\python.exe worker.py --backend android --sdk D:\Android\Sdk --start-emulator --avd Pixel_API_35
.\venv\Scripts\python.exe worker.py --backend android --sdk D:\Android\Sdk --start-emulator --avd Pixel_API_35 --headless
.\venv\Scripts\python.exe worker.py --backend android --install-apk C:\Downloads\example.apk
.\venv\Scripts\python.exe worker.py --backend android --serial emulator-5554 --run --route ZJGroute.txt --speed 4.8 --minutes 10
```

`--headless` 用于完全通过命令行调试，不显示模拟器窗口。源码运行遇到 Microsoft Store Python 的用户目录重定向问题时，可设置 `IOSREALRUN_DATA_DIR` 到可写的专用目录；安装版默认使用 `%LOCALAPPDATA%\iOSRealRun`。

本项目也提供无窗口启动脚本。已安装 SDK、Emulator 和 Android 15 Google APIs x86_64 镜像后，可以在普通 PowerShell 中执行：

```powershell
.\start_android_cli.ps1 -SdkDirectory D:\Android\Sdk
```

脚本在 SDK 旁的 `RealRunTest` 英文目录保存虚拟设备和运行缓存，优先使用已构建的 worker，并在缺少虚拟设备时创建一个；它只启动 Android，不自动安装应用或开始路线推送。可用 `-AndroidHome` 和 `-AvdName` 指定其他目录与名称。worker 会复制到独立运行目录，避免工作区遗留的低权限文件标记导致 SDK 无法写入缓存；未重新构建时会复用这份副本，不修改系统权限或关闭认证。

### 程序更新与构建

窗口右上角显示当前版本，点击 **检查更新** 查询正式 Release。网络请求和下载都在后台进行；下载失败可重试，校验失败的文件不会进入安装流程。更新时先结束正在运行的任务，再退出程序并运行安装向导，用户设置保留在安装目录之外。

Windows 构建使用 Python 环境中的 PyInstaller、pywebview，Node.js 22/24，以及 Inno Setup 6。先安装 `requirements.txt` 中的依赖。构建脚本会构建 React 前端，再生成 EXE 与安装包：

```powershell
.\build_windows.ps1
```

只构建前端可在 `frontend` 目录运行 `npm ci` 和 `npm run build`。需要重新生成 OpenStreetMap 离线底图时，运行 `scripts/build_offline_maps.py`；地图数据的来源与许可保存在 `frontend/public/maps`。

CLI 调试模式复用真实控制器与前端资源，不创建窗口：

```powershell
.\venv\Scripts\python.exe desktop_app.py --serve --connection-file build\desktop-connection.json
.\venv\Scripts\python.exe desktop_app.py --diagnose-renderer
```

连接文件包含临时本机访问令牌，仅供本机调试。服务绑定 `127.0.0.1`，接口需要令牌并拒绝其他来源；关闭服务后令牌失效。端到端验证使用 `frontend/scripts/verify-live.mjs`，需明确指定 SDK、连接文件和测试 AVD 名称。它会在测试虚拟设备推送一小段路线并停止，不涉及任何 App 的登录、考勤或运动记录提交。

版本号在 `app_info.py` 中维护。产物输出到 `dist\v<版本号>\`，其中 `installer\iOS-RealRun-Setup.exe` 和 `SHA256SUMS.txt` 可作为 Release 附件。构建脚本不自动升级依赖，也不清空其他版本产物；可用 `-PythonPath` 指定构建环境，并禁用用户级扩展包以免混入无关依赖。回归检查使用：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实 GPS 验证可使用 `tests/android_probe` 中的本地测试 APK。它没有网络权限或账号，仅记录 Android 的定位回调。准备好 SDK Build Tools 34、Android 34 平台和 JDK 后，在专用测试 AVD 上运行：

```powershell
.\tests\android_probe\build.ps1 -Sdk D:\Android\Sdk -Output D:\Android\RealRunTest\gps-probe
.\venv\Scripts\python.exe tests\verify_android_live.py --sdk D:\Android\Sdk --serial emulator-5554 --avd-name RealRun_Android15 --apk D:\Android\RealRunTest\gps-probe\RealRun-GPS-Probe.apk --report build\live-android-verification.json
```

检查会安装并启动测试 APK，推送约 10 秒路线后停止，确认坐标变化、非零速度和正常退出；可加 `--worker` 指定打包后的 worker EXE。它只验证模拟器 GPS，不验证其他 App 的业务功能。

---

## 原理

1. 通过 `pymobiledevice3` 与 iOS 设备建立 USB 远程调试连接
2. 利用 Apple DVT (Developer Tools) 框架的 `LocationSimulation` 注入虚假定位
3. 从路线文件读取坐标 → 按速度插值 → 模拟配速波动、弯道减速、疲劳和短暂恢复 → 持续发送到设备

## 测试环境

| 项目     | 版本                   |
| -------- | ---------------------- |
| 操作系统 | macOS, Windows 11      |
| Python   | 3.11+                  |
| iOS      | 17.4+，已验证 iOS 27.2.1 |

## 前置准备

1. **Windows 需要安装 iTunes**（提供设备通信驱动）
2. iOS 设备系统版本 ≥ 17.4，已验证 iOS 27.2.1
3. 源码运行需要 Python 3.11+；使用 Windows 安装包无需安装 Python
4. **只能有一台 iOS 设备连接电脑**
5. 使用普通权限 USB RSD 用户态隧道，无需管理员/root 权限

## 快速开始

### 1. 安装依赖（源码运行）

```bash
pip install -r requirements.txt
```

### 2. 连接设备

将 iPad/iPhone 通过 USB 连接到电脑，解锁并点击"信任"。

### 3. 挂载 Developer Disk Image

```bash
python worker.py --mount
```

### 4. 运行

**Windows（普通 PowerShell）：**

```powershell
python main.py
```

**macOS：**

```bash
python3 main.py
```

### 5. 退出

达到默认约 4 公里目标后程序会自动停止并恢复真实定位；也可以按 `Ctrl + C` 提前终止。程序退出时会主动清除模拟定位，如果定位未恢复，重启手机即可。

## 配置

编辑 `config.yaml`：

```yaml
v: 4.8                         # 速度 (m/s)
routeConfig: "ZJGroute.txt"   # 路线文件
speedVariation:
   profile: "recreational"      # steady / recreational / variable
   targetDistance: 4000.0       # 目标总里程（米）
```

速度模型使用连续相关的随机波动，而不是每圈突然换一次速度；同时会根据路线转角减速，并模拟非线性疲劳和偶发短暂恢复。`recreational` 适合普通跑者，`steady` 更平稳，`variable` 波动更明显。

### 路线文件

仓库内置三条路线（坐标从百度地图取的 BD-09，程序自动转为 WGS-84）：

| 文件           | 路线                   |
| -------------- | ---------------------- |
| `ZJGroute.txt` | 浙大紫金港东操（默认） |
| `YQroute.txt`  | 浙大玉泉               |
| `HNroute.txt`  | 浙大海宁               |

## 项目结构

```
ios-realrun/
├── main.py                  # 入口（支持 -m 限时运行）
├── run.py                   # 核心：坐标转换、插值、定位注入
├── config.py                # 配置加载
├── config.yaml              # 速度 / 路线配置
├── requirements.txt         # Python 依赖
├── launcher.py              # Windows 图形启动器
├── worker.py                # GUI 后台 worker
├── build_windows.ps1        # Windows 打包脚本
├── installer.iss            # Inno Setup 安装器配置
├── start.bat                # 命令行一键启动脚本
├── start.ps1                # PowerShell 版启动脚本
│
├── init/
│   ├── init.py              # 初始化
│   ├── tunnel.py            # USB 隧道
│   └── route.py             # 路线读取
│
├── driver/
│   └── connect.py           # 设备连接
│
└── util/
    └── route.py             # 路线工具
```

## 自动停止

默认达到约 4 公里后自动停止；也支持设置最长运行时长，到点自动停止并恢复真实定位：

```bash
python main.py -m 30       # 最长运行 30 分钟，或先达到 4 公里
python main.py              # 运行到约 4 公里后自动停止
```

### 一键启动脚本

**`start.bat`（推荐）** — 双击运行，自动提权 → 挂载镜像 → 启动 → 到时停止：

| 命令                 | 说明                           |
| -------------------- | ------------------------------ |
| 双击`start.bat`      | 默认跑**30 分钟**              |
| `start.bat -m 45`    | 跑 45 分钟                     |
| `start.bat -m 0`     | 不限制时间，达到目标里程后停止 |
| `start.bat -m 20 -n` | 跑 20 分钟，跳过挂载           |

**`start.ps1`** — PowerShell 版本（功能同上）

---

## 升级记录

### pymobiledevice3 4.x → 9.x

旧版 `pymobiledevice3` 在新 iOS 上可能导致 `LocationSimulation` 注入超时。本项目使用异步 DVT API，当前已验证 iOS 26.3.1。

#### 波及文件及修改

| 文件                | 变更                                                                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run.py`            | `DvtSecureSocketProxyService` → `DvtProvider`（async context manager）；`LocationSimulation.set()` 改为 `async`；同步 `time.sleep` 改为 `asyncio.sleep` |
| `init/init.py`      | `init()` 改为 `async`，适配 `connect` 模块 async 化                                                                                                     |
| `driver/connect.py` | `create_using_usbmux()` 改为 `await`；`developer_mode_status` 属性 → `get_developer_mode_status()` 方法（async）；`AmfiService` 方法均为 async          |
| `main.py`           | 新增`argparse` 支持 `-m`/`--minutes` 参数；`.init()` → `await`；捕获 `asyncio.TimeoutError` 实现自动停止                                                |
| `requirements.txt`  | `pymobiledevice3>=9.19.0`                                                                                                                               |

#### 核心 API 变化

```python
# 旧版 (4.20.20)
from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
dvt = DvtSecureSocketProxyService(rsd)
dvt.perform_handshake()
LocationSimulation(dvt).set(lat, lng)                # 同步

# 新版 (9.19.0)
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
async with DvtProvider(rsd) as dvt:
    async with LocationSimulation(dvt) as loc_sim:
        await loc_sim.set(lat, lng)                   # async
```

### v1.2.0 配速模拟更新

旧版本只在每圈开始时随机改变一次速度，圈内速度基本恒定，变化不太像真人。本版本改为连续配速模型：

- 使用相关随机过程，让速度平滑地加速和减速，避免每个定位点突然跳变
- 加入加速/减速惯性，减速响应比加速更慢
- 路线转弯时短暂降速，出弯后逐渐恢复
- 偶发短暂恢复、轻微降速和短暂加速，模拟普通跑者的状态变化
- 疲劳根据已跑距离非线性增加，默认目标约 4 公里
- 所有波动按基础速度的百分比计算，在不同配速下保持相近的相对变化幅度

GUI 提供四种配速档位：

| 档位           | 特点                                   |
| -------------- | -------------------------------------- |
| `constant`     | 沿路线保持目标速度，不加入配速波动     |
| `steady`       | 波动较小，适合模拟较稳定的跑者         |
| `recreational` | 默认模式，适合普通跑者                 |
| `variable`     | 波动更明显，适合模拟配速控制较弱的跑者 |

可在 `config.yaml` 中调整 `cvPercent`、`correlationTime`、`fatiguePercent`、`lapPercent` 和 `targetDistance`。

---

## Windows 图形版

项目提供一个名为 **iOS RealRun** 的 Windows 启动器，支持设备检查、自动挂载开发者镜像、路线/速度/时长配置以及运行日志。

- 下载安装：[Releases 页面](https://github.com/Obladi0617/ios-realrun/releases/latest)（`iOS-RealRun-Setup.exe`）
- 使用说明：见上方 [下载与安装](#下载与安装推荐)

### 从源码构建安装包

在已准备好 `venv` 的项目目录中，以 PowerShell 执行：

```powershell
.\build_windows.ps1
```

脚本会生成 `dist\v1.4.4\installer\iOS-RealRun-Setup.exe`。安装后从桌面 **iOS RealRun** 快捷方式启动。

---

## 常见问题

**"Failed to connect to usbmuxd socket"**
→ 没有安装 iTunes，或 Apple Mobile Device Service 未运行。

**"No device connected"**
→ 确保设备已解锁并点击"信任"，重插 USB 线试试。

**定位没恢复**
→ 重启手机即可恢复真实定位。

**换电脑后无法挂载开发者镜像**

首次挂载时需要联网从 GitHub 下载个性化镜像（约 15 MB），下载后会缓存到本机：

```text
%USERPROFILE%\.pymobiledevice3\Xcode_iOS_DDI_Personalized\
├── Image.dmg
├── Image.trustcache
└── BuildManifest.plist
```

在一台电脑上成功挂载后，换到新电脑会重新下载；如果新电脑访问 GitHub 受限，就会挂载失败。

**解决办法（任选其一）：**

1. **直接下载缓存包（最快）**

   **[⬇️ 下载 Xcode_iOS_DDI_Personalized.zip](https://github.com/Obladi0617/ios-realrun/releases/download/v1.1.0/Xcode_iOS_DDI_Personalized.zip)**（约 15 MB，沿用已有公开缓存）

   解压后把里面的 `Image.dmg`、`Image.trustcache`、`BuildManifest.plist` 三个文件放到：

   ```text
   C:\Users\<新电脑用户名>\.pymobiledevice3\Xcode_iOS_DDI_Personalized\
   ```

   放好后重新点击“开始模拟”即可，无需联网下载。

2. **从已成功的电脑复制**
   把已成功电脑上的整个目录复制到新电脑相同位置：

   ```text
   源：  C:\Users\<用户名>\.pymobiledevice3\Xcode_iOS_DDI_Personalized
   目标：C:\Users\<新电脑用户名>\.pymobiledevice3\Xcode_iOS_DDI_Personalized
   ```

   注意：目录要放在**实际运行程序的那个用户**的家目录下（程序以管理员运行时通常是同一个用户）。

3. **确保联网**
   新电脑需要能访问 `api.github.com` 与 Apple 的 `gs.apple.com`（用于获取个性化授权票据）。

4. **确认前置条件**
   - 使用 iOS 17.4 或更新版本，通过 USB 连接
   - 已安装 iTunes（Apple Mobile Device 服务）
   - 设备已解锁并信任此电脑，且已开启开发者模式

## 致谢

- [iOSRealRun](https://github.com/iOSRealRun/iOSRealRun-cli-17) - 原项目
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) - iOS 远程调试库
