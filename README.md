# RealRun

沿预设路线回放 GPS，支持 iPhone、iPad 和 Google Android Emulator。桌面工作台提供实时轨迹、离线校园地图和配速显示。

**[下载 Windows 安装包](https://github.com/Obladi0617/Realrun/releases/latest/download/iOS-RealRun-Setup.exe)** · [便携版和版本记录](https://github.com/Obladi0617/Realrun/releases)

## 快速开始

Windows 10/11（64 位）可直接安装，无需配置 Python。便携版解压后运行 `iOSRealRun.exe`。

| 模式 | 准备 |
| --- | --- |
| iPhone / iPad | iOS 17.4 或更新版本。安装 Apple 设备驱动，用 USB 连接一台设备，解锁并信任电脑，开启开发者模式。 |
| Android | 安装官方 Android SDK 的 Emulator、Platform-Tools 和 Android 15 Google APIs x86_64 镜像。首次创建虚拟设备需要 Command-line Tools 和 JDK。找不到 SDK 时，在设置里填路径。 |

1. 在工作台选择设备，点击「检查设备」。
2. 选择路线、配速与时长，点击「开始定位」。默认配速是 5:00/km。
3. 结束时点击「停止定位」。iPhone 会清除模拟位置，Android 模拟器会停在最后一个位置。

Android 模式可以在「应用」页安装 APK，并在手机窗口里完成登录。地图右上角可打开独立路径窗口。

「定点定位」使用世界地图。点选地图或搜索地点、坐标，再开始定位。定位期间可继续换点。在线地点搜索由 [Photon](https://github.com/komoot/photon) 提供。

## 内置路线

- **紫金港东田径场**（默认）
- **紫金港西田径场**（约 400 米一圈）
- **玉泉**
- **海宁**

西田径场路线根据 [学校公布的跑道长度](https://tyys.zju.edu.cn/redir.php?catalog_id=172636) 和 [地图上的场地位置](https://www.openstreetmap.org/way/817997262) 拟合。所有路线都可以离线预览。

## 命令行与构建

源码运行需要 Python 3.11 或更新版本。在仓库目录运行

```powershell
python -m pip install -r requirements.txt
python worker.py --check
python worker.py --run --route ZJGWestTrack.geojson --minutes 10
```

Android 命令行加 `--backend android`，可用 `--sdk` 指定 SDK。Windows 安装包通过 `build_windows.ps1` 构建，需准备 Node.js、PyInstaller 和 Inno Setup。

## 排障

- iPhone 连不上时，检查 Apple Mobile Device 服务、USB 数据线、开发者模式和「信任此电脑」。需要下载开发者镜像时先联网。
- 在 Windows 版的「运行日志」查看报错。日志文件在 `%LOCALAPPDATA%\iOSRealRun\desktop.log`，偏好设置也保存在该目录。
- 仓库更名前的版本可通过页面顶部的安装包完成更新。

[Mozilla Public License 2.0](LICENSE) · 基于 [iOSRealRun](https://github.com/iOSRealRun/iOSRealRun-cli-17) 和 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) · 地图数据 [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright)
