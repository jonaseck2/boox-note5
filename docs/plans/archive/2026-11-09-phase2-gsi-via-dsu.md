# Phase 2: generic Android image via DSU — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** A current Google generic Android image (GSI) with Google apps boots on the Note5 and draws on the e-ink panel. Refresh modes and full refresh are camera-verified under it. Onyx's stock system stays untouched and is one reboot away.

**Scope.** In:
- Install and boot GSIs through Android's Dynamic System Updates (DSU).
- Observe the display, adb and root.
- Rerun `booxctl epd probe` under the GSI.
- Return to stock.

Out:
- Writing `super` permanently (a later plan, only after a GSI passes here).
- The e-ink service and Settings entries (phase 4).

**Verification:**
- `.venv/bin/python scripts/check_context_budget.py && .venv/bin/python -m pytest -q tools` exits 0.
- Under the GSI:
  - `adb shell getprop ro.build.version.release` prints `16` or higher.
  - `booxctl shot` produces a camera frame that matches the screencap: the launcher is visible on the panel.
  - `booxctl epd probe` prints `full_refresh: VISIBLE` and `mode_switch: VISIBLE`. If mode_switch fails, the plan records why and what phase 4 needs instead.
- After `adb reboot`, `getprop ro.build.fingerprint` is the Onyx fingerprint again.
- **Prerequisites:**
  - DSU flag `persist.sys.fflag.override.settings_dynamic_system=true`. Set on 2026-11-09.
  - `com.android.dynsystem` present.
  - At least 15 GB free on `/data` (40 GB measured).
  - Camera corners in `~/boox-backups/camera-corners.json`.

**Architecture:** `booxctl dsu` wraps the DSU activity intent and `gsi_tool`. The GSI comes from Google's official GMS GSI zip. A non-sparse raw `system.img` is gzipped and pushed to `/sdcard/Download`. DSU installs it into `/data` and boots it from there.

**Spec:** [2026-11-08-eink-aosp-design.md](2026-11-08-eink-aosp-design.md). Facts: `docs/runbooks/device-facts.md`, `docs/runbooks/eink-interface.md`.

## Global Constraints

- Serial `$BOOX_SERIAL`, `ADB_LIBUSB=1` (see the `boox-device` skill).
- No writes to `super`, `boot_*` or `vbmeta*` in this plan. DSU writes only to `/data`.
- GSI candidates, in order:
  1. Google GMS GSI Android 16 QPR3 `CP11.251209.009.A1` (2026-02-10).
  2. Google GMS GSI Android 17 QPR3 beta `DP11.261016.003`.
  3. LineageOS 23.2 GSI with GApps (MisterZtr).
  4. TrebleDroid AOSP 16.
- Move to the next candidate only when the current one fails to boot or to draw.
- Precedent: the Hisense A9 (SDM662, Android 11 vendor) runs LineageOS GSIs with a working e-ink panel.

## Review Focus

1. **The GSI boots but the panel never updates.** adb and screencap still work. Expected: the plan detects this from the camera, not from screencap, and records it.
2. **The GSI bootloops.** Expected: DSU falls back to stock on the next boot, and the plan records the failure from stock's `logcat -b all` or from `/metadata/gsi`.
3. **The DSU install silently stops at partial progress.** Expected: `dsu status` reports the state, and the plan fails instead of rebooting into a half-installed image.

---

### Task 1: `booxctl dsu` — install, status, boot, discard

**Files:** Create `tools/booxctl/dsu.py`, `tools/tests/test_dsu.py`. Modify `__main__.py` and the `boox-device` skill.

**Interfaces:** Produces:
- `prepare(zip_path) -> (gz_path, raw_size)`: unzip `system.img`; if sparse (magic `0xED26FF3A`), convert to raw; then gzip.
- `install(dev, gz_remote, raw_size, userdata_bytes=8 GiB)`.
- `status(dev) -> str`: `gsi_tool status` as root.
- `boot(dev)`: `gsi_tool enable` without `-s`, so the GSI boots once, then reboot.
- `discard(dev)`: `gsi_tool wipe`.

- [x] Write the failing tests:
  - `test_install_intent_has_sizes`: the argv contains `--el KEY_SYSTEM_SIZE <n>` and `KEY_USERDATA_SIZE`.
  - `test_sparse_image_converted_to_raw`: a synthetic sparse image with one raw and one fill chunk gives the expected bytes.
- [x] Implement. Then run the tests and confirm they pass.
- [x] Commit.

### Task 2: install and boot the GSI

- [x] Run `dsu prepare` on candidate 1, then push the result.
- [x] Run `dsu install`, and poll `dsu status` until it reports installed. Record the time taken.
- [x] Run `dsu boot`. Wait for adb. Record `getprop ro.build.version.release`, `ro.build.fingerprint` and `ro.vndk.version`, then run `booxctl shot`.
- [x] Evidence for the panel: the camera frame matches the screencap layout. Run `booxctl calibrate` first if corner detection is needed.
- [x] If the GSI does not boot or does not draw, record the cause from logcat or the camera, run `adb reboot` to return to stock, and try the next candidate.

### Task 3: e-ink control under the GSI

- [x] Check root under the GSI. The DSU image boots the Magisk-patched `boot_b`, so `su` may work. If it doesn't, record that and use `adb root` if the GSI is userdebug.
- [x] Push `ebcctl`. Run `booxctl epd probe`. Expected: `full_refresh: VISIBLE` and `mode_switch: VISIBLE`, because no Onyx SurfaceFlinger overrides the waveform here.
- [x] Record the results in `docs/runbooks/eink-interface.md`, including whether the vendor composer applies a default waveform for plain DRM commits.

### Task 4: back to stock, and the decision for the permanent install

- [x] Run `adb reboot` and confirm the Onyx fingerprint. Then `dsu discard`, or keep the image for further tests.
- [x] Write the go/no-go for flashing the passing GSI into `super` permanently: repacked `super` via EDL, plus a `vbmeta` with verification disabled. Put it on the questions artifact. That flash replaces Onyx's system, so it needs the owner's OK.

---

## Outcome (closed 2026-11-14)

The Goal is met by a different route than this plan's DSU mechanism. Rulings:

- **Ruling: DSU replaced by a permanent `super` rebuild.** DSU cannot boot GSIs on this device: in DSU mode, first-stage AVB cannot find `vbmeta_b`/`boot_b` (RAM-dump evidence, `docs/runbooks/gsi-install.md`). With the owner's OK, `super` was rebuilt with our own liblp writer and written over EDL. Cost if wrong: none left, because the system runs.
- **Ruling: candidate 3 (LineageOS 23.2 GAPPS GSI) instead of candidates 1–2.** The Google GSIs abort in `system_server` (ClatCoordinator: the 4.19 kernel lacks eBPF features).
- **Ruling: "back to stock" (Task 4) is replaced by the EDL restore path.** The verified backup (`~/boox-backups/2026-11-08/edl/rl`) and `device/recover-edl.sh stock` are the way back. The Onyx system is no longer one reboot away.
- **Ruling: `epd probe` (Task 3) is replaced by the shim pipeline.** On the GSI the panel draws only through the composer's own EPDC path, driven by `device/epdcshim`. Waveforms were compared with the camera meter (`booxctl flicker`). Details: `docs/runbooks/eink-interface.md`.

Evidence (2026-11-14):

```
$ adb shell getprop ro.build.version.release        -> 16
$ adb shell getprop ro.lineage.version              -> 23.2-20260524-GAPPS-EXT4-GSI
$ python3 scripts/check_context_budget.py           -> OK: 5438 <= 6000
$ python -m pytest -q tools                         -> 62 passed
camera: the panel shows the LineageOS UI matching the screencap (setup wizard, Settings, Chrome on HN/Omni)
```
