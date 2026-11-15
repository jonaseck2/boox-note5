---
name: boox-device
description: Use when touching the Boox Note5 over adb/fastboot, capturing its screen or camera, flashing, backing up, rooting, or working on e-ink refresh.
---

# Boox Note5 device

Facts: [`docs/runbooks/device-facts.md`](../../../docs/runbooks/device-facts.md). E-ink kernel interface: [`docs/runbooks/eink-interface.md`](../../../docs/runbooks/eink-interface.md) (written in phase 1). Owner mandate and availability: design § Owner mandate in `docs/plans/` (or `docs/plans/archive/`).

## Rules

- **Recovery precheck (hard rule):** before ANY device write, name the exact way back and prove it still works in the post-write state: adb forced on, EDL reachable, slot fallback real (check `slot-successful` flags). If the step can remove the only way back, don't run it.
- **Before asking the owner for physical effort** (power cycles, buttons, cables), verify the mechanism against recorded facts (`getvar.txt`, runbooks) and a quick search. Both slots are `slot-successful:yes`, so power cycles never force a fallback here.

- Serial: `$BOOX_SERIAL`, or `~/.config/boox/serial` (holds this tablet's serial). Always pass `-s`. Another adb device (a TV) is on the network.
- Start the adb server with `ADB_LIBUSB=1`, or the Mac does not list the device.
- Never write the active slot or slot-independent partitions without a verified backup (`python3 -m booxctl backup verify`).
- Never write `xbl*`, `abl*`, `tz*`, `hyp*`, `rpm*`, `devcfg*`, `keymaster*`, and never enter EDL, without asking the owner first.
- Backups and proprietary Onyx files live in `$BOOX_BACKUP_DIR` (default `~/boox-backups`), never in the repo.
- Batch steps that need the owner (buttons, sign-in) for a morning or evening window.

- **Before the first boot of any new system image, flash a `boot_b` that forces adb** (see `docs/runbooks/gsi-install.md`). A fresh userdata has adb off, USB disappears, and this device has no volume keys for EDL.
- DSU cannot boot GSIs on this device (first-stage AVB path). Use the permanent `super` rebuild instead.
- Treat a boot as hung after 3 minutes of no USB and no panel change.

## E-ink pipeline (facts, details in docs/runbooks/eink-interface.md)

- The kernel redraws the panel only for DRM commits that carry plane props `EPDC_UPDATE_CNT` + `EPDC_UPDATE_PARMS_ADDR`. The address points to an array of 40-byte `mxcfb_update_data` entries (`top,left,width,height,waveform_mode,update_mode,marker,temp,flags`) in the committing process.
- Onyx's SurfaceFlinger sends the list as composer extension command `0x08020000` (`n` + `n`×5 words). GSIs don't send it, so the panel stays white. The fix is `device/epdcshim` (LD_PRELOAD into the composer; calls its `setEpdcList`). Install: `build.sh` + `install.sh` there, plus the `boox_composer` service in the boot rc. Mode `0x10`–`0x80` flashes every frame. Default `0x904` (wf4, camera-measured least flash) plus an idle full clean (`0x10`) after 30 updates. EPDC reads only the primary plane: HW overlays must stay disabled (SF 1008, module `service.sh`), else dialogs/keyboard never show. **The EPDC panics the kernel if it updates while a narrow plane (<1872 wide) is on screen.** The shim rejects every commit that isn't one full-size fb, and `post-fs-data` sets `vendor.display.primary_mixer_stages=1`. Never remove either. `FB_ID` prop ids differ per plane. Android colour transforms never reach the panel, so tone mapping lives in the shim (`persist.boox.lut.*`). Mostly dark frames get the shim's dark profile (own curve, light-widening bold, clean `0x13`: `0x10` leaves dark pages white), see the runbook's dark-theme entry. Crash log: `/sys/fs/pstore/dmesg-ramoops-1`. Never `cp` over the live `.so`: use `install.sh`. Boot guard: 3 boots without 60 s of health restore `libbooxepdc.so.prev` (log `/data/adb/boox_guard.log`).
- **Never send EPDC `waveform_mode=2`: it panics the kernel.** Framebuffer is landscape 1872x1404. Kernel EPDC traces: `echo 255 > /sys/class/sepdc/debug/debug_level`.
- Settings > Display > E-ink = `device/einksettings` (system app via its own Magisk module, writes props through su). Injected Settings tiles must come from system apps. A replaced system APK needs `adb install -r` (no rescan without a fingerprint change).
- Front light: `/sys/class/backlight/onyx_bl_br` (0–28), colour temp `onyx_bl_ct` (0–24). Android's slider and Night Light are bridged by the module's `service.sh`.
- Full refresh: read `/sys/class/sepdc/debug/panel_clean`, which works as shell. Forced waveform: `/dev/ebc` ioctl `0x700b` (`device/ebcctl`).
- Current system: LineageOS 23.2 GSI with glue releases (`module.prop` version). Root via `/debug_ramdisk/su`. Boot image `~/boox-backups/gsi/boot_b.magisk.epdc.img` (adb key + adbd restart + `boox_composer`). Fallback `boot_b.magisk.adbkey.img`. The panel shows Android after a plain reboot (2026-11-14).

## Tool

`cd tools && python3 -m booxctl <cmd>`. All device calls go through `booxctl.device.Device`.

- `shot <dir>` — writes `screen.png` (screencap, pulled from `/sdcard`, because stock `screencap` prints junk to stdout) and `camera.jpg` (Mac FaceTime camera, which faces the panel).
- `calibrate` — store camera panel corners (run after the stand moves).
- `backup dump|verify|import-edl|restore-script` — `verify ~/boox-backups/2026-11-08/edl/rl` checks the EDL backup. Restores go over EDL.
- `epd clean` (full refresh via `panel_clean`) · `epd mode normal|speed|a2|x` (`/dev/ebc` ioctl) · `epd probe`.
- Root: `adb shell su -c ...`. EDL: start `edl` before `adb reboot edl`, outside the sandbox. Procedure: `docs/runbooks/device-facts.md`.
- `flicker <dir> --action '<adb shell cmd>'` — camera flicker meter (30 fps, `flash_area`). `tap "<text>"` — tap an element by text or content-desc.
- Preferred release path: GitHub Actions `release` workflow (`gh workflow run release.yml -R jonaseck2/boox-note5 -f version=…`). It needs no device libraries (stubs) and signs with the secret `EINK_KEYSTORE_B64`. The keystore is backed up in the owner's Drive at `My Drive/boox/`.
- `release glue --version YYYY.MM.DD.N [--publish]` · `update glue --tag glue-v… | --bundle zip` — glue releases on `jonaseck2/boox-note5` (verify, precheck, install, reboot, post-check). On the tablet: Settings > Display > E-ink > Check for updates.
- `booxctl.lp` (liblp super metadata rebuild) · `booxctl.bootimg` (add ramdisk files to boot v2) · `booxctl dsu …` (DSU; unusable here, kept for reference).
