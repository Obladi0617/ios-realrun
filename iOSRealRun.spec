from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata


root = Path(SPECPATH)
datas = [(str(root / name), ".") for name in ("config.yaml", "ZJGroute.txt", "YQroute.txt", "HNroute.txt")]
hiddenimports = []
binaries = []
for package in ("pymobiledevice3", "developer_disk_image", "geopy"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)

datas.extend(copy_metadata("pyimg4"))


launcher_analysis = Analysis([str(root / "launcher.py")], pathex=[str(root)], datas=datas, binaries=binaries, hiddenimports=hiddenimports, noarchive=False)
worker_analysis = Analysis([str(root / "worker.py")], pathex=[str(root)], datas=datas, binaries=binaries, hiddenimports=hiddenimports, noarchive=False)

launcher = EXE(PYZ(launcher_analysis.pure), launcher_analysis.scripts, launcher_analysis.binaries, launcher_analysis.datas, [], name="iOSRealRun", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, uac_admin=True)
worker = EXE(PYZ(worker_analysis.pure), worker_analysis.scripts, worker_analysis.binaries, worker_analysis.datas, [], name="iOSRealRun-worker", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True, uac_admin=True)

coll = COLLECT(launcher, worker, launcher_analysis.binaries, launcher_analysis.datas, worker_analysis.binaries, worker_analysis.datas, strip=False, upx=False, name="iOSRealRun")