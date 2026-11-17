# Mounted Developer Image Startup Design

## Intent

Allow the Windows EXE to start on the current supported iOS systems when the required Developer Disk Image is already mounted, including cases where the device reports it under either `Developer` or `Personalized` image type.

## Findings

`worker.mount_image()` called `pymobiledevice3.auto_mount()` and only treated `AlreadyMountedError` as success. On the connected iOS 27.0.1 device, `LookupImage` returned no signature for either image type, but `CopyDevices` showed a mounted Personalized Developer Disk Image at `/System/Developer`. A duplicate mount returned `ImageMountFailed` even though the image was already active.

## Approaches

1. Catch and ignore all mount errors. Rejected because genuine mount, pairing, or connectivity failures would be hidden.
2. Check mounted devices for an active image at `/System/Developer`, then fall back to the `Developer` and `Personalized` lookups when `CopyDevices` is unsupported. If mounting still fails, recheck and continue only when an image is confirmed mounted. Selected because it handles the observed cryptex DDI state while preserving real errors.

## Design

- Keep the existing iOS 17+ DVT location path and version floor unchanged.
- In `worker.py`, use `MobileImageMounterService.copy_devices()` to detect an active image mounted at `/System/Developer`.
- If `CopyDevices` is unsupported, check `Developer` and `Personalized` with `is_image_mounted()`.
- Skip `auto_mount()` when an image is already present. If mounting fails, recheck and suppress the error only when the image is confirmed mounted; otherwise propagate it.
- Rebuild the Windows bundle to a new output directory so existing EXEs/installers remain intact. Do not launch the packaged EXE.
- No tests were added or run. Python syntax compilation and a PyInstaller build succeeded, and the source mount flow was verified against the connected iOS 27.0.1 device. The packaged EXE was not launched.
