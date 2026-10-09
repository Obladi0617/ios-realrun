import importlib.metadata
from pathlib import Path
from packaging.requirements import Requirement

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


root = Path(SPECPATH)
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


launcher_analysis = Analysis([str(root / "launcher.py")], pathex=[str(root)], datas=[], binaries=[], hiddenimports=[], noarchive=False)
worker_analysis = Analysis([str(root / "worker.py")], pathex=[str(root)], datas=route_datas, binaries=binaries, hiddenimports=hiddenimports, noarchive=False)

launcher = EXE(PYZ(launcher_analysis.pure), launcher_analysis.scripts, launcher_analysis.binaries, launcher_analysis.datas, [], name="iOSRealRun", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, uac_admin=True)
worker = EXE(PYZ(worker_analysis.pure), worker_analysis.scripts, worker_analysis.binaries, worker_analysis.datas, [], name="iOSRealRun-worker", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True, uac_admin=True)

coll = COLLECT(launcher, worker, launcher_analysis.binaries, launcher_analysis.datas, worker_analysis.binaries, worker_analysis.datas, strip=False, upx=False, name="iOSRealRun")