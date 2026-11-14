# Device facts — Boox Note5 

Read over adb on 2026-11-08. Re-read with `adb -s $BOOX_SERIAL shell getprop <prop>` before relying on a value after a flash.

## Access

- adb over USB works. USB debugging is enabled in Boox's menus at **Apps → ☰ (menu) → App Management → USB debug mode**. The Build-number tap in Boox's own Settings does nothing.
- On this Mac, `adb devices` did not list the device until the adb server ran with `ADB_LIBUSB=1` (`ADB_LIBUSB=1 adb kill-server; ADB_LIBUSB=1 adb start-server`). USB ID: `18d1:4ee2`.
- The network can have a second adb device (a TV). Always pass `-s $BOOX_SERIAL`.
- **Root (since 2026-11-09):** Magisk v31.1. Active `boot_b` is a Magisk-patched copy of stock (SHA-256 `5729a569…`), written via EDL. The stock `boot_b` is in the EDL backup (`c6929595…`). `adb shell su -c <cmd>` works because module `device/magisk-shellroot` grants uid 2000 and sets `root_access=3`. Magisk's own UI hides the ADB root option on this build.
- **Onyx App Freeze** (Apps → ☰ → App Management → App Freeze) disabled Magisk right after install. Without the app, the Magisk daemon rejects every `su` request with no prompt (`su: request rejected (2000)`). Fix: switch off "Automatically enable freezing after installing an app" and untick Magisk (a ticked box means frozen).
- **DocumentsUI file picker ignores `input tap`.** Navigate with `input keyevent 20` (DPAD_DOWN), then `66` (ENTER).
- **Slot `a` cannot boot:** `super` only holds `_b` logical partitions. Every boot-image change goes to `boot_b`, after a verified backup.
- **Stay awake:** `settings put global stay_on_while_plugged_in 7`, `screen_off_timeout 2147483647`, `dumpsys deviceidle disable`.
- `adb exec-out screencap -p` is corrupt on stock firmware: Onyx's `screencap` prints `capture from screenshot!` to stdout before the PNG. Use `screencap -p /sdcard/s.png` and `adb pull`.
- The device clock reads `2025-06-20` (checked 2026-11-08). It is wrong by 17 months.

## Fastboot and flashing paths (tested 2026-11-08)

- **macOS accessory prompt.** Each new USB mode of the tablet (bootloader `18d1:d00d`, fastbootd `18d1:4ee0`, EDL `05c6:9008`) triggers a macOS "Allow accessory to connect?" prompt on this Mac. Until someone clicks Allow, IORegistry shows the device as `!registered, !matched` and no tool sees it. Notify the owner before switching modes.
- **Bootloader fastboot** (`adb reboot bootloader`): `getvar` works. Results: `unlocked:yes`, `secure:no`, `product:bengal`, `current-slot:b`, both slots `successful:yes`, `max-download-size:804268032`. Saved: `~/boox-backups/2026-11-08/getvar.txt`. `boot`, `flash`, `erase`, `fetch` and `oem` all return `unknown command`, so Onyx removed them.
- **fastbootd** (`adb reboot fastboot`): `is-userspace:yes`, `version-vndk:30`, `super` is `0x100000000` (4 GiB). Logical partitions exist only for slot `b` (`system_b`, `system_ext_b`, `product_b`, `vendor_b`, `system_b-cow`). `flash` and `boot` return `Unrecognized command`, and `fetch` is unsupported. Saved: `getvar-fastbootd.txt`.
- **Consequence:** the only write path is Qualcomm EDL with a firehose loader. Community loader for HWID `0014d0e1` (SM_KAMORTA_H = SM6115): `poke6.bin` from temblast.com, SHA-256 `e5eb01597752a59cb74cc4fb5b2137eea3fe361be94226f3613b979abe194eb6`, stored in `~/boox-backups/tools/loaders/`. **Confirmed on the Note5 (2026-11-08 22:30):** Sahara reports HWID `0x0014d0e100000000` (MSM_ID `0x0014d0e1`, SDM662), PK_HASH `0xd40eee56f3194665574109a39267724ae7944134cd53cb767e293d3c40497955bc8a4519ff992b031fadc6355015ac87`, serial `0xb59197fc`. `poke6.bin` loads (build date 2022-12-18) and offers `program, read, erase, patch, getsha256digest, fixgpt, setbootablestoragedrive`. Storage: UFS `KM5H7001DM-B424`, 6 LUNs, block size 4096. Full GPT: `~/boox-backups/2026-11-08/edl/gpt.log`.
- **EDL procedure that works:**
  1. Start `edl` **before** `adb reboot edl`, outside the Claude Code sandbox, because the sandbox hides USB devices from libusb.
  2. Run it from a directory where a `logs/` subdirectory can be created.
  3. If an `edl` run is killed after the Sahara hello, the chip ignores new connections until the owner holds power for about 15 s.
  4. The EDL USB device (`05c6:9008`, `QUSB_BULK_CID:041C`) needs the macOS accessory approval once.
- **Physical layout:**
  - LUN 0: `super` (4 GiB), `userdata`, `metadata`, `onyxconfig`, `recovery_a/b`, `vbmeta_system_a/b`, `persist`, `frp`, `misc`, `keystore`.
  - LUN 1/2: `xbl_a` / `xbl_b`.
  - LUN 4: the A/B firmware and `boot_a/b` (96 MiB each), `dtbo_a/b`, `vbmeta_a/b`, `abl_a/b`, and others.
  - LUN 5: modem storage.
- **Owner approval** (2026-11-08 21:45): EDL may be used. Read-only backup first, then a Magisk-patched boot image to slot `a`. Never write the bootloader-chain partitions.

## Firmware packages

- Onyx update API: `http://data.onyx-international.cn/api/firmware/update?where=<json>`. The JSON takes `buildNumber`, `buildType`, `deviceMAC`, `lang` (`en_US`; `zh_CN` returns 204), `model` (`Note5`), `submodel` and `fingerprint` (`Onyx/Note5/Note5:11/<build>/<incremental>:user/release-keys`). The full package it returns is v4.0 `2025-04-01_22-12_v4.0-rel_6d15a71551` (build 49342), 1851160970 bytes, md5 `a4a99d1cdaba2d29af5214e3f81c178d`, at `http://firmware-us.boox.com/a4a99d1cdaba2d29af5214e3f81c178d/update.upx`.
- Decryption: `Hagb/decryptBooxUpdateUpx`, which has a `Note5` key in `BooxKeys.csv`.

## Camera (feedback loop)

- The Mac's `FaceTime HD Camera` (ffmpeg avfoundation device `0`) faces the propped-up tablet. The tablet is in landscape. Capture command: `ffmpeg -f avfoundation -framerate 30 -video_size 1920x1080 -i "0:none" -ss 2 -frames:v 1 cam.jpg`. The 2-second skip lets exposure settle.
- Fixed position since 2026-11-08 16:54 (device clock): the panel spans about x 15–1850 and y 115–1050 of the 1920x1080 frame. All four corners are inside the frame. That is about 1 camera pixel per panel pixel, enough to read body text.
- The camera looks down at the panel, so the image has perspective skew. Correct it in software with a 4-corner warp. Tilting the tablet back increases glare, so the skew stays.
- Lamp glare fades the left edge, the sidebar labels at x < 300. Mask it in scoring.
- Ask the owner before moving the setup. Scores are only comparable within one position.
- **The owner moved the stand on 2026-11-09.** The new corners from `booxctl calibrate` are `[[78,60],[1665,63],[1477,969],[309,963]]`, stored in `~/boox-backups/camera-corners.json`. Re-run `python3 -m booxctl calibrate` after any move. Auto-detection of the panel fails when the screen shows dark content, so always use the stored corners.
- The warm frontlight is on. It tints camera frames orange, so compare grey levels within one session only.

## Hardware

| Property | Value |
|---|---|
| SoC | Qualcomm `bengal` (SM6115 family / Snapdragon 662) |
| RAM | 3.7 GB |
| Panel | 1404x1872, 240 dpi |
| `/data` | 51 GB, 8.8 GB used |

## Software

| Property | Value |
|---|---|
| Boox firmware | `2025-06-20_22-08_4.0.2-rel_0617_d4b9d37036` |
| Android | 11 (SDK 30), security patch 2024-02-01 |
| Fingerprint | `ONYX/BOOX/BOOX:11/RKQ1.210614.002/200:userdebug/release-keys` |
| Google apps | GMS and Play Store (`com.android.vending`) installed |
| Stock Settings | `com.android.settings` present, opens with `am start -a android.settings.SETTINGS` |

## Bootloader and partitions

| Property | Value | Meaning |
|---|---|---|
| `ro.boot.vbmeta.device_state` | `unlocked` | Bootloader is already unlocked |
| `ro.boot.verifiedbootstate` | `orange` | Boots unverified images |
| `ro.boot.flash.locked` | `0` | Flashing allowed |
| `ro.treble.enabled` | `true` | Generic system images (GSI) can boot in principle |
| `ro.build.ab_update` | `true`, active slot `_b` | A/B slots give a fallback slot |
| `ro.boot.dynamic_partitions` | `true` | `system` is flashed from fastbootd, not the bootloader |
| `ro.vndk.version` | `30` | Vendor interface is Android 11 |

## E-ink stack

E-ink refresh control is in Onyx's framework on the **system** partition, not the vendor partition:

- Binder services `onyx_device_service` (`android.onyx.services.IOnyxDeviceService`) and `oec_service` (`android.onyx.optimization.IOECService`).
- Native libraries include `libonyx_epd_listener.so`, `libonyx_neo_dither.so` and `libonyx_pen_touch_reader.so`.

Consequence: replacing `system` with a GSI removes refresh-mode control, dithering and the low-latency pen path, unless they are rebuilt.

## Storage and update facts (2026-11-14, from the OTA design `docs/plans/2026-11-14-ota-design.md`)

- `super` is 4096 MiB. LineageOS system 3287 MiB + vendor 493 MiB leaves about 315 MiB free. There is no room for a second system copy, so no A/B system updates inside `super`.
- `/data` uses `metadata_encryption=aes-256-xts:wrappedkey_v0` (`vendor_b` fstab). Stock `recovery_b` (user build) has adbd but no keymaster or vold, so it cannot read images staged on `/data`.
- GitHub release assets are limited to 2 GiB each, so a GSI system image cannot be a single release asset.
- Verdict: system updates go over USB/EDL. Glue updates (shim, module, settings) can run on the device.
