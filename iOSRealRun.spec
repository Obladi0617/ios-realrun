import importlib.metadata
import runpy
from pathlib import Path
from packaging.requirements import Requirement

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata
from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo


root = Path(SPECPATH)
app_version = runpy.run_path(str(root / "app_info.py"))["APP_VERSION"]
version_numbers = tuple(int(part) for part in app_version.split(".")) + (0,)


def version_info(filename):
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=version_numbers, prodvers=version_numbers, mask=0x3f,
                          flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "iOS RealRun"),
            StringStruct("FileVersion", app_version),
            StringStruct("ProductName", "iOS RealRun"),
            StringStruct("ProductVersion", app_version),
            StringStruct("OriginalFilename", filename),
        ])]), VarFileInfo([VarStruct("Translation", [0x409, 1200])])],
    )
route_datas = [(str(root / name), ".") for name in ("config.yaml", "ZJGroute.txt", "YQroute.txt", "HNroute.txt")]
hiddenimports = []
binaries = []
for package in ("pymobiledevice3", "developer_disk_image", "geopy", "pytun_pmd3"):
    route_datas.extend(collect_data_files(package))
    binaries.extend(collect_dynamic_libs(package))

hiddenimports.extend((
    "pymobiledevice3.cli.lockdown",
    "pymobiledevice3.cli.remote",
    "pymobiledevice3.cli.cli_common",
    "pymobiledevice3.exceptions",
    "pymobiledevice3.lockdown",
    "pymobiledevice3.remote.remote_service_discovery",
    "pymobiledevice3.remote.common",
    "pymobiledevice3.remote.tunnel_service",
    "pymobiledevice3.services.amfi",
    "pymobiledevice3.services.mobile_image_mounter",
    "pymobiledevice3.services.dvt.instruments.location_simulation",
    "pymobiledevice3.services.dvt.instruments.dvt_provider",
    "pytun_pmd3",
    "pytun_pmd3.wintun",
))

def dependency_metadata(roots):
    """Keep metadata for the device stack, without bundling the whole venv."""
    pending = list(roots)
    visited = set()
    names = []
    while pending:
        name = pending.pop()
        key = name.lower().replace("_", "-")
        if key in visited:
            continue
        visited.add(key)
        names.append(name)
        try:
            requirements = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            requirements = []
        for requirement_text in requirements:
            requirement = Requirement(requirement_text)
            if requirement.marker is None or requirement.marker.evaluate():
                pending.append(requirement.name)
    metadata = []
    for name in names:
        try:
            metadata.extend(copy_metadata(name))
        except importlib.metadata.PackageNotFoundError:
            pass
    return metadata

route_datas.extend(dependency_metadata((
    "pymobiledevice3", "developer-disk-image", "geopy", "pytun-pmd3",
    "PyYAML", "coloredlogs", "pyimg4", "readchar",
)))


desktop_datas = [(str(root / "frontend" / "web-dist"), "frontend/web-dist")]
desktop_datas.extend(collect_data_files("webview"))
desktop_datas.extend(collect_data_files("pythonnet"))
desktop_datas.extend(copy_metadata("pywebview"))
desktop_binaries = collect_dynamic_libs("webview") + collect_dynamic_libs("clr_loader")
launcher_analysis = Analysis([str(root / "desktop_app.py")], pathex=[str(root)], datas=desktop_datas, binaries=desktop_binaries,
                             hiddenimports=["webview.platforms.winforms", "webview.platforms.edgechromium"],
                             excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cef", "webview.platforms.android", "webview.platforms.cocoa"], noarchive=False)
worker_analysis = Analysis([str(root / "worker.py")], pathex=[str(root)], datas=route_datas, binaries=binaries, hiddenimports=hiddenimports, noarchive=False)

launcher = EXE(PYZ(launcher_analysis.pure), launcher_analysis.scripts, [], exclude_binaries=True, name="iOSRealRun", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, uac_admin=False, version=version_info("iOSRealRun.exe"))
worker = EXE(PYZ(worker_analysis.pure), worker_analysis.scripts, [], exclude_binaries=True, name="iOSRealRun-worker", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True, version=version_info("iOSRealRun-worker.exe"))

coll = COLLECT(launcher, worker, launcher_analysis.binaries, launcher_analysis.datas, worker_analysis.binaries, worker_analysis.datas, strip=False, upx=False, name="iOSRealRun")
