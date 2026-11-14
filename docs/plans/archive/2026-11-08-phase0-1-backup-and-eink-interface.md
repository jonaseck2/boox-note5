# Phase 0–1: Backup and e-ink interface map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** The Boox Note5 is fully backed up to the Mac with a tested restore path. A root shell command on stock firmware triggers a full e-ink refresh and switches refresh modes, as confirmed by the camera.

**Scope.** In: phase 0 (temporary root, partition dump, `/sdcard` export, restore script, EDL research) and phase 1 (e-ink kernel interface map) of the design. Out: flashing any GSI (phase 2), permanent changes to the active slot, entering EDL mode.

**Verification:**
- `python3 scripts/check_context_budget.py && python3 -m pytest -q tools` exits 0. The CI gate runs this exact command (Task 1 adds it to `.github/workflows/gate.yml`).
- `python3 -m booxctl backup verify ~/boox-backups/<date>` prints `OK <n> partitions` and exits 0.
- `python3 -m booxctl epd probe` (device on stock, temporary root active) prints `full_refresh: VISIBLE` and `mode_switch: VISIBLE` and exits 0. VISIBLE is decided from camera frames.
- **Prerequisites:** the device is connected over USB with debugging authorised. The adb server runs with `ADB_LIBUSB=1`. The camera position is unchanged since 2026-11-08 (see the runbook). At least 60 GB is free on the Mac at `~/boox-backups`. `jadx` is installed (`brew install jadx`).

**Architecture:** `booxctl` is a stdlib-only Python package under `tools/` and the single entry point to the device: adb/fastboot calls, screencap, camera, backup, EPD probing. All device calls go through one `Runner` so tests replace it with a fake. Proprietary Onyx files and partition dumps stay outside the repo, in `~/boox-backups`. Findings land in `docs/runbooks/` and a description-matched skill.

**Tech Stack:** Python 3.10 stdlib, pytest, adb/fastboot (Homebrew), ffmpeg (avfoundation), Magisk (`magiskboot`), jadx, Ghidra (only if Java decompilation does not reveal the interface).

**Spec:** [docs/plans/2026-11-08-eink-aosp-design.md](2026-11-08-eink-aosp-design.md)

## Global Constraints

- Device serial `$BOOX_SERIAL`. Every adb/fastboot call passes `-s $BOOX_SERIAL`, because another adb device (a TV) is also on the network.
- Never write to the active slot (`_b`) or to slot-independent partitions before Task 5 verifies the backup. A write to inactive slot `_a` is allowed.
- Never write `xbl*`, `abl*`, `tz*`, `hyp*`, `rpm*`, `devcfg*`, `keymaster*` or any partition listed by the bootloader as critical. Do not enter EDL. Either one needs the owner's approval first.
- Backups go to `$BOOX_BACKUP_DIR` (default `~/boox-backups`), never into the repo.
- Steps that need the owner (buttons, sign-in) are batched and asked for in a morning or evening window.
- Stock screencap prints `capture from screenshot!` to stdout. Use `screencap -p /sdcard/<f>` and pull.

## Review Focus

1. **The device reboots or drops off USB mid-dump.** Expected: backup resumes per partition, and a partial file never counts as done. Pinned by `test_backup_skips_verified_and_redoes_partial` (Task 5).
2. **The temporary root is gone after a reboot** (`fastboot boot` does not persist). Expected: commands needing root fail with `RootRequired`, never with a silent empty result. Pinned by `test_su_missing_raises_root_required` (Task 1).
3. **A second adb device appears** (the TV). Expected: every call stays pinned to `$BOOX_SERIAL`. Pinned by `test_runner_always_passes_serial` (Task 1).
4. **The camera image is unchanged because the panel did not refresh,** not because the command failed. Expected: the probe reports `NOT_VISIBLE` and the measured diff, not a pass. Pinned by `test_probe_reports_not_visible_on_identical_frames` (Task 8).
5. **The restore script includes a bootloader-chain partition.** Expected: excluded unless `--include-critical` is passed. Pinned by `test_restore_excludes_critical_by_default` (Task 5).

---

### Task 1: `booxctl` core — runner, adb, screencap, camera, gate

**Files:**
- Create: `tools/booxctl/__init__.py`, `tools/booxctl/__main__.py`, `tools/booxctl/runner.py`, `tools/booxctl/device.py`, `tools/booxctl/camera.py`
- Create: `tools/tests/conftest.py` (a `FakeRunner` fixture that records argv and returns scripted outputs), `tools/tests/test_device.py`
- Create: `.claude/skills/boox-device/SKILL.md`
- Modify: `.github/workflows/gate.yml` (add `python3 -m pip install pytest && python3 -m pytest -q tools` after the budget step), `pyproject.toml` (new: `[tool.pytest.ini_options] pythonpath = ["tools"]`)

**Interfaces:**
- Produces:
  - `Runner.run(argv: list[str], *, input: bytes | None = None, timeout: float = 120) -> Result(returncode: int, stdout: bytes, stderr: bytes)`
  - `Device(runner, serial="$BOOX_SERIAL")` with `shell(cmd: str) -> str`, `su(cmd: str) -> str` (raises `RootRequired`), `pull(remote: str, local: Path)`, `screencap(local: Path)`, `getprop(name: str) -> str`, `fastboot(*args: str) -> str`, `reboot(target: str | None)`, `wait_for(state: Literal["device","bootloader","fastbootd"], timeout: float)`
  - `camera.capture(path: Path, device_index=0, settle_s=2.0) -> Path`, run via ffmpeg `-f avfoundation -framerate 30 -video_size 1920x1080 -pixel_format nv12 -i "0:none" -ss <settle> -frames:v 1`
  - CLI: `python -m booxctl shot <dir>` writes `screen.png` and `camera.jpg`

- [x] **Step 1: Write failing tests** in `tools/tests/test_device.py`: `test_runner_always_passes_serial` (every recorded argv for `shell`, `pull`, `fastboot` contains `-s $BOOX_SERIAL`), `test_su_missing_raises_root_required` (fake stdout `/system/bin/sh: su: inaccessible or not found` raises `RootRequired`), `test_screencap_writes_to_sdcard_then_pulls` (argv sequence: `shell screencap -p /sdcard/booxctl.png`, `pull`, `shell rm`), `test_adb_env_sets_libusb` (Runner env has `ADB_LIBUSB=1`).
- [x] **Step 2: Run** `python3 -m pytest -q tools`. Expected: 4 FAIL (import errors).
- [x] **Step 3: Implement** the runner, device and camera modules and the `shot` CLI.
- [x] **Step 4: Run** `python3 -m pytest -q tools`. Expected: 4 passed. Prove each test RED by stubbing its code path (copy the file first, restore from the copy).
- [x] **Step 5: Real device check.** Run `python3 -m booxctl shot /tmp/x`. Expected: `screen.png` is 1872x1404 (`file` shows PNG), and `camera.jpg` shows the panel.
- [x] **Step 6: Write the `boox-device` skill.** Description: "Use when touching the Boox Note5 over adb/fastboot, capturing its screen or camera, flashing, backing up, or working on e-ink refresh." The body points to `docs/runbooks/device-facts.md`, `docs/runbooks/eink-interface.md` (Task 7) and `booxctl` usage, and carries the Global Constraints above. Run `python3 scripts/check_context_budget.py`. Expected: exit 0.
- [x] **Step 7: Commit** `feat(booxctl): device runner, screencap, camera; boox-device skill; pytest in gate`.

### Task 2: Export `/sdcard` to the Mac

**Files:** Create `tools/booxctl/export.py`, `tools/tests/test_export.py`.

**Interfaces:** Produces `export_sdcard(dev: Device, dest: Path) -> ExportReport(files: int, bytes: int)` and CLI `python -m booxctl export-sdcard [dest]` (default `$BOOX_BACKUP_DIR/<YYYY-MM-DD>/sdcard`).

- [x] **Step 1: Write failing test** `test_export_compares_counts`: the fake `find /sdcard -type f | wc -l` returns `120`, and a local count of 119 makes `export_sdcard` raise `ExportIncomplete`.
- [x] **Step 2: Run.** Expected: FAIL.
- [x] **Step 3: Implement** with `adb pull /sdcard/. dest`, then compare the file count and total bytes (`du -sb` on device vs local).
- [x] **Step 4: Run tests,** expected pass. Then run on the real device. Expected: the report's file count equals the device's count.
- [x] **Step 5: Commit.**

### Task 3: Obtain the stock `boot` image for firmware 4.0.2

Investigation task. Its output is a file and a runbook entry.

**Files:** Modify `docs/runbooks/device-facts.md` (new section "Stock images").

- [x] **Step 1: Try `fastboot fetch`.** Run `adb reboot bootloader`, then `fastboot -s $BOOX_SERIAL getvar all` (save the output to `~/boox-backups/<date>/getvar.txt`), then `fastboot fetch boot_b boot_b.img`. Return with `fastboot reboot`. Record whether `fetch` is supported and whether `fastboot boot` is supported (`getvar` and the bootloader's response).
- [x] **Step 2: If fetch is unsupported,** find Onyx's OTA package for the Note5 firmware `4.0.2-rel_0617`. Sources: the OTA URL in `logcat`/settings of the Onyx update service, community archives (MobileRead), and community Boox firmware decryption tools for encrypted `update.upx` packages. Extract `boot.img` from `payload.bin` with `payload-dumper-go`.
- [x] **Step 3: Check.** `file boot.img` shows an Android boot image. Its `magiskboot unpack` header OS version matches Android 11 and patch level `2024-02`. Record the SHA-256 and source in the runbook.
- [x] **Step 4: If neither path yields `boot.img`,** stop and report to the owner, with the remaining options: an EDL read with a firehose loader, or flashing a self-built boot image to slot `_a`.
- [x] **Step 5: Commit** the runbook update.

### Task 4: Temporary root via `fastboot boot`

**Files:** Create `tools/booxctl/root.py`, `tools/tests/test_root.py`. Modify the runbook.

**Interfaces:** Produces `patch_boot(dev, stock: Path, out: Path) -> Path` (pushes the image and Magisk's `magiskboot`/`boot_patch.sh` from a pinned Magisk release APK, runs the patch as the shell user, pulls `new-boot.img`), `temp_root(dev, patched: Path) -> None` (`adb reboot bootloader`, then `fastboot boot patched`, then `wait_for("device")`, then asserts `su -c id` contains `uid=0`). CLI `python -m booxctl root [--patched path]`.

- [x] **Step 1: Write failing test** `test_temp_root_never_flashes`: the recorded fastboot argv contains `boot` and never `flash`.
- [x] **Step 2: Run.** Expected: FAIL.
- [x] **Step 3: Implement.** Pin the Magisk version in `root.py` (latest stable release at implementation time, recorded with its SHA-256). Root via `fastboot boot` also needs the Magisk app installed to grant `su` to the shell user. Install it with `adb install` and pre-grant the shell with `magisk --sqlite` policy insert.
- [x] **Step 4: Run** tests, then the real device. Expected: `adb shell su -c id` prints `uid=0(root)`. A reboot returns the device to stock, unrooted. Check: after `adb reboot`, `su` raises `RootRequired`.
- [x] **Step 5: If `fastboot boot` is refused,** flash the patched image to `boot_a` only (allowed, inactive slot), run `fastboot --set-active=a`, and record that the fallback is `--set-active=b`. Ask the owner first if this step is reached in a window where they are unavailable for button recovery.
- [x] **Step 6: Commit.**

### Task 5: Full partition backup, verify and restore script

**Files:** Create `tools/booxctl/backup.py`, `tools/tests/test_backup.py`.

**Interfaces:** Consumes `Device.su`, `Device.pull`. Produces:
- `list_partitions(dev) -> list[Partition(name: str, size: int)]` from `/dev/block/bootdevice/by-name` and `blockdev --getsize64`
- `dump(dev, dest: Path, skip=("userdata",)) -> Manifest` writes `<name>.img` and `manifest.json` (`{name, size, sha256_device, sha256_local}` per partition)
- `verify(dest: Path) -> VerifyReport` re-hashes local files against the manifest
- `restore_script(manifest, include_critical=False) -> str` emits `fastboot -s $BOOX_SERIAL flash <name> <file>` lines, for fastbootd or the bootloader as each partition requires
- CLI: `backup dump|verify|restore-script`

- [x] **Step 1: Write failing tests:** `test_backup_skips_verified_and_redoes_partial` (an existing `.img` whose hash matches the manifest is skipped, and a size mismatch is re-dumped), `test_verify_flags_hash_mismatch`, `test_restore_excludes_critical_by_default` (no line for `xbl_a`, `abl_b`, `tz_a`, and they appear with `include_critical=True`), `test_dump_skips_userdata`.
- [x] **Step 2: Run.** Expected: 4 FAIL.
- [x] **Step 3: Implement.** Per partition: `su -c 'dd if=/dev/block/bootdevice/by-name/<p> of=/data/local/tmp/<p>.img bs=4M'`, compute `sha256sum` on the device, pull, hash locally, delete the device copy. `super` (several GB) streams through `adb exec-out su -c 'cat …'` to avoid filling `/data`.
- [x] **Step 4: Run** tests, then the real device: `backup dump`, then `backup verify`. Expected: `OK <n> partitions` with n = number of by-name entries minus `userdata`. Paste the output into this plan.
- [x] **Step 5: Dry-run the restore.** `backup restore-script > restore.sh`. Each `flash` target must be a by-name entry, and the script contains no critical partitions. Save it next to the manifest.
- [x] **Step 6: Commit.**

### Task 6: Pull Onyx artefacts and the EDL status

**Files:** Modify `docs/runbooks/device-facts.md` (sections "EDL" and "Analysis artefacts").

- [x] **Step 1: Pull, as root,** to `~/boox-backups/<date>/analysis/`: `/system/framework`, `/system/priv-app` and `/system/app` (Onyx packages), `/system/lib64/libonyx_*`, `/vendor/etc/init`, `/vendor/etc/selinux`, `/system/etc/selinux`, `/proc/config.gz`, `dmesg`, `ls -lZR /dev`, `/sys/class` listing, and `service list`.
- [x] **Step 2: Check.** `ls analysis/framework | grep -c jar` is above 0, and `zcat config.gz | grep -i epd` lists the EPD driver config.
- [x] **Step 3: EDL research, without entering EDL.** Find whether a firehose programmer for SM6115 with the Note5's hardware ID (`getvar all`, `/proc/cpuinfo` serial) is public. Record yes or no, the source and the risks in the runbook.
- [x] **Step 4: Commit** the runbook.

### Task 7: Map the e-ink interface

Investigation task. Output: `docs/runbooks/eink-interface.md`.

- [x] **Step 1: Decompile** the Onyx framework jars with `jadx -d out analysis/framework/<onyx jars>` and the system_server classes. Locate the implementations of `IOnyxDeviceService` and the EPD calls (search for `ioctl`, `/dev/`, `/sys/`, `native` methods, `libonyx_epd`).
- [x] **Step 2: Trace live.** Find the process that hosts `onyx_device_service` (`dumpsys -l`, `ls -l /proc/*/fd`). Push a static arm64 `strace` and attach while switching the refresh mode in Onyx's Refresh Mode Settings. The switch is driven by `input tap` from the screencap layout, not by the owner. Record the device node, ioctl numbers and argument structs, or the sysfs paths.
- [x] **Step 3: Write `eink-interface.md`:** the node/HAL, the operations (full refresh, refresh/waveform modes, dither, any region update), the argument layout, the SELinux context of the node (`ls -Z`), and which side (system or vendor) opens it. Include the rejected candidates and why.
- [x] **Step 4: Commit.**

### Task 8: `epd probe` — camera-verified control from the shell

**Files:** Create `tools/booxctl/epd.py`, `tools/booxctl/vision.py`, `tools/tests/test_epd.py`, `tools/tests/test_vision.py`.

**Interfaces:** Produces:
- `vision.warp_to_screen(camera: Path, size=(1872, 1404)) -> Image` (4-corner detection plus perspective warp. numpy and opencv-python are allowed as dev dependencies of `tools/` only, if stdlib is not enough. They are then added to the gate install line.)
- `vision.diff_score(a, b, mask_left_px=300) -> float` (mean absolute grey difference, glare strip masked)
- `epd.full_refresh(dev)` and `epd.set_mode(dev, mode: str)` using the interface from Task 7, through `su`
- CLI `epd probe` prints `full_refresh: VISIBLE|NOT_VISIBLE (<score>)` and `mode_switch: …`, and exits non-zero if either is NOT_VISIBLE

- [x] **Step 1: Write failing tests:** `test_probe_reports_not_visible_on_identical_frames` (two identical frames give a score under the threshold, `NOT_VISIBLE` and exit 1), `test_diff_score_masks_glare_strip` (a difference only at x<300 scores 0).
- [x] **Step 2: Run.** Expected: FAIL.
- [x] **Step 3: Implement.** The full-refresh probe draws a high-contrast pattern (a pushed PNG opened by an image intent), switches to a white screen without full refresh, captures the ghost, runs `full_refresh` and captures again. VISIBLE means the ghost score dropped by at least 50%. The mode-switch probe runs a fixed scroll in two modes and compares ghost scores.
- [x] **Step 4: Run** tests, then the real device. Expected: both lines VISIBLE, exit 0. Paste the output and both before/after camera frames into the plan.
- [x] **Step 5: Commit,** and update `docs/ROADMAP.md`: this plan moves to shipped via `close-out`, and the phase 2 GSI plan goes under Next.

## Outcome (2026-11-09)

- Verification: `python3 scripts/check_context_budget.py && pytest -q tools` → 29 passed. `booxctl backup verify ~/boox-backups/2026-11-08/edl/rl` → `OK 82 partitions`. `booxctl epd probe` → `full_refresh: VISIBLE`. The negative control with the refresh stubbed out returns False.
- **Deviation:** `mode_switch` is still NOT_VISIBLE on stock firmware. Onyx's SurfaceFlinger attaches its own per-update waveforms that override `force_waveform`, and it resets the value on every app launch. The camera proof of refresh modes moves to phase 2 (GSI via DSU). The kernel accepts and logs every mode set by `ebcctl`.
- Route changes, with the reasons in the ledger rulings:
  - Root and backup went through EDL, because Onyx removed fastboot `boot`, `flash`, `erase` and `fetch`.
  - The patched boot went to `boot_b`, because slot `a` cannot boot.
  - Shell root came from a Magisk module.
