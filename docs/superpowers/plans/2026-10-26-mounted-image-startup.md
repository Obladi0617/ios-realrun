# Mounted Developer Image Startup Implementation Plan

> **For agentic workers:** Implement inline in this workspace. Do not launch the packaged EXE.

**Goal:** Let the EXE continue when a Developer Disk Image is already mounted, without hiding genuine mount failures.

**Architecture:** Query `CopyDevices` for a mounted Developer Disk Image at `/System/Developer`; if unsupported, query `Developer` and `Personalized` image types. On a mount error, re-query and suppress only if an image is confirmed mounted. Rebuild to a separate output directory.

**Tech Stack:** Python 3.11, pymobiledevice3, PyInstaller, PowerShell.

**Spec:** `docs/superpowers/specs/2026-10-26-mounted-image-startup-design.md`

## Constraints

- Keep the current iOS 17+ DVT path and version gate unchanged.
- Do not add multi-device selection.
- Do not ignore genuine image mount or connection errors.
- Preserve existing `dist` artifacts; build under `dist/mount-fix`.
- Do not launch the packaged EXE or add/run tests unless asked.

---

### Task 1: Make image mounting idempotent

**Files:**
- Modify: `worker.py`

- [x] Query `CopyDevices` and detect an active Developer Disk Image at `/System/Developer`, with the image-type lookup fallback.
- [x] Skip `auto_mount()` when the required image is already present.
- [x] If an error occurs, re-query and continue only if a mounted image is confirmed; otherwise re-raise the original failure.
- [x] Run `python -m py_compile worker.py`.

### Task 2: Rebuild Windows bundle

**Files:**
- Create build output: `dist/device-version-compatible/iOSRealRun/`

- [x] Run PyInstaller with isolated `--workpath` and `--distpath`, without deleting existing outputs.
- [x] Verify both launcher and worker EXEs exist and source mount behavior against the connected device.
