# E-ink interface — Boox Note5 (stock firmware 4.0.2)

Mapped 2026-11-09 on the rooted stock system. Sources:

- Kernel config (`/proc/config.gz`) and `dmesg`.
- `ls -lZR /dev` and `/sys/class/sepdc`.
- `strings` over binaries pulled to `~/boox-backups/2026-11-08/analysis/fs`.
- Camera-verified experiments.

Device facts: [device-facts.md](device-facts.md).

## Kernel driver (stays under any system image)

- Driver: Onyx "software EPDC" built into the 4.19.157 kernel. Config: `CONFIG_FB_ONYX_SOFTWARE_EPDC=y`, `CONFIG_ONYX_EPDC_USE_MIPI_SDM662=y`, `CONFIG_ONYX_EPDC_TCON_TYPE_LCDIF=y`, `CONFIG_ONYX_EPDC_SEGMENT=y`, `CONFIG_ONYX_EPDC_DISPLAY_BUF_PIXEL_FORMAT_RGBA=y`.
- The panel is fed through the SDM662 MIPI-DSI display pipeline. The timing controller is a Lattice FPGA, with firmware compiled into the kernel (`lfe5u/*`, `lfcpnx/*_tcon_fw_*.bin`).
- Waveforms: `waveform/eink_waveform.wbf` compiled into the kernel, plus vendor waveforms from the `onyxconfig` partition (`CONFIG_ONYX_EPDC_WAVEFORM_VENDOR_DIR="onyxconfig"`). `/sys/devices/platform/onyx_epdc_fb.0/waveform_version` reads `onyx waveform sg`.
- Kernel threads: `mdss_fb_epdc`, `commit_epdc`, `EPDC Submit`, `epdc_refresh_wa`, `epdc_thread`, `epdc_msg_thread`.
- Platform device: `onyx_epdc_fb.0`. No `/dev/fb*` or `/dev/graphics/*` node exists. Userspace display goes through `/dev/dri/card0` (226,0, mode 0666).
- Kernel log line seen during normal UI use: `epdc_ioctl(): set force_waveform = 16777220` (`0x01000004`). There is an ioctl path that forces a waveform. Its node and number are not traced yet (see Open items).

### Debug sysfs: `/sys/class/sepdc/debug/` (root, SELinux type `sysfs`)

| Node | Mode | Effect (verified) |
|---|---|---|
| `panel_clean` | r | **Reading it triggers a full-panel clean refresh.** Camera mean grey over the panel: ~150 → 77 → 183 → settles at ~158 within ~1 s. Same curve in 2 of 2 runs (2026-11-09). `dmesg`: `show_panel_clean(): enter!` |
| `status` | r | EPDC state: `epdctask_status`, `wf_status`, `epdc_active_luts`, `frame[a:b:c]` |
| `update_disable` | rw | `0` by default. Presumably stops panel updates. Not tested. |
| `panel_init`, `panel_last`, `dump_list`, `update_err` | r | Not tested. |
| `submit_upd_work`, `update_snapshot`, `reset_test` | w | Not tested. `submit_upd_work` may submit an update. |
| `cut_frame_num`, `debug_level`, `time_test_level` | rw | Tuning and debug. Not tested. |

Shell command for a full refresh: `adb shell su -c 'cat /sys/class/sepdc/debug/panel_clean'`. Writing to `panel_clean` fails, because the file is read-only.

## How stock Android drives it (system side, lost under a GSI)

Onyx extended the AOSP graphics stack with an "EPDC list": per-update refresh rectangles with a waveform mode.

| Layer | Binary | Evidence (strings) |
|---|---|---|
| App surface | `system/lib64/libgui.so` | `Surface::transferEpdc`, `EpdcWrapper::addEpdc(int,int,int,int,int)`, `/dev/onyx/epdc-listener` |
| Compositor | `system/lib64/libsurfaceflinger.so` | `EpdcManager`, `HWEpdcManager`, `SWEpdcManager`, `### sf epdc region received: %d %d %d %d mode: %d`, `/dev/ebc` |
| HAL types | `graphics.common@1.0` (custom) | `conversion::flatten(...V1_0::EpdcWrapper...)`: Onyx added a type to the composer HIDL interface |
| Vendor composer | `vendor/bin/hw/vendor.qti.hardware.display.composer-service` | `onyx_epdc_update_to_display`, `waveform_mode = %d, update_mode = %d, Rect[...]`, `CommitEpdc`, `/dev/graphics/fb0` |
| Framework | `system_server` | holds `/dev/onyx/listener` (FIFO) and `/onyxconfig/mmkv/onyx_config` |
| JNI | `libonyx_epd_listener.so` | `android.onyx.optimization.EpdEventListener`, `android.onyx.hardware.DeviceController` |

**Consequence for the generic image (design phase 2/4):** the vendor composer and the kernel stay. The EPDC-list plumbing in libgui, SurfaceFlinger and the HAL types disappears. Phase 2 has to show what the vendor composer does with plain commits that carry no EPDC list. It probably falls back to a default waveform. Per-region waveform control then needs one of these:

- the kernel ioctl directly (`force_waveform`), from a small privileged service;
- a modified SurfaceFlinger in a self-built system image.

Full refreshes are already available through `panel_clean`.

## Refresh-mode control: `/dev/ebc` ioctl `0x700b` (verified 2026-11-09)

- Node: `/dev/ebc`, char 10,53, `crw------- root root`, SELinux type `ebc_device`. SurfaceFlinger keeps it open as fd 23.
- Call: `ioctl(fd, 0x700b, &int32)`. The kernel logs `epdc_ioctl(): set force_waveform = <v>!`. Traced with ftrace `raw_syscalls` (fd printed in hex: `0x17` = 23). Each Onyx quick-panel mode tap produced exactly one SurfaceFlinger ioctl, 4–11 µs before the kernel log line.
- Values (from Onyx's quick panel → kernel log):

| Onyx mode | value |
|---|---|
| Normal | `-1` (no forced waveform) |
| Speed | `2305` (`0x901`) |
| A2 | `2308` (`0x904`) |
| X | `16777220` (`0x1000004`) |

- Shell tool: `device/ebcctl/ebcctl <value>` (277-byte static AArch64 ELF, syscall-only; source `ebcctl.S`, built with `clang -target aarch64-linux-gnu -c` plus `mkelf.py`). Run as root from `/data/local/tmp/ebcctl`. Setting all four values returned rc 0, and the kernel logged each one.
- `booxctl epd mode <normal|speed|a2|x>` and `booxctl epd clean` wrap both controls.
- **Not yet proven on camera:** a visible difference between modes. A static image redrawn under every mode measured the same (16-step ramp: 139–142 grey-level range in each mode). The scroll comparison between camera and screencap is too noisy (21–99 regardless of mode). Next design: record video of a scroll and measure transition frame count and partial-render greys per mode.
- The other Onyx quick-panel controls also need tracing: "Dark Color Enhancement" (default 30), "Light Color Filter" (0), "High Contrast". They are candidates for the contrast work in design phase 5.

## Rejected candidates

- `/dev/graphics/fb0`: the composer contains the string, but the node does not exist on this device.

## Open items

- Camera proof that refresh modes change the panel output (see above).
- The vendor composer commits through plain DRM atomic ioctls (`0xc03864bc` on `/dev/dri/card0`). Find out what it does without Onyx's EPDC list under a GSI (phase 2).

## How a frame reaches the panel (reverse-engineered 2026-11-15)

Sources: the vendor composer and display libraries pulled as root from the running LineageOS (`~/boox-backups/2026-11-14/composer-re`). All are stripped. The code references below were found with a capstone `adrp`+`add` scan.

- The kernel EPDC refreshes the panel only from an **atomic commit whose DRM plane carries Onyx's custom properties `EPDC_UPDATE_CNT` and `EPDC_UPDATE_PARMS_ADDR`**. The setters are `sde_drm::DRMPlane::SetEpdcUpdCnt(drmModeAtomicReq*, uint32)` and `SetEpdcUpdParmsAddr(drmModeAtomicReq*, uint64)` in `libsdedrm.so`.
- They are filled by `sdm::DisplayBase::CommitUpd(onyxfb_update_data*, int)` → `HWDeviceDRM::CommitUpd` in `libsdmcore.so`. The composer's own code: `CommitEpdc` (xref `0x40288`), `update_to_display[...] waveform_mode, update_mode, Rect, flags` (`0x40db4`), and `Epdc list not matched, use item count` (`0x36968`).
- The update list comes from Onyx's modified SurfaceFlinger / libgui (`EpdcWrapper`). A GSI's SurfaceFlinger never sends it, so every commit has CNT=0. The kernel counts frames, but it never draws the composed image. That is why the panel stays white under LineageOS while stock recovery (minui, which drives the EPDC path the kernel's own way) draws.
- **Way forward:** feed `onyxfb_update_data` ourselves. Options, in order of preference:
  1. Find how the update list reaches the composer (a vendor.qti composer extension call, or a field in the HIDL command stream), and send it from a small privileged daemon on every SurfaceFlinger frame or on a timer.
  2. Hook the composer process (Magisk module / LD_PRELOAD) so that `CommitUpd` always gets a full-screen update when the list is empty.
  3. Drive the EPDC from our own DRM client. Not preferred, because the composer holds DRM master.

### The update-list command (reverse-engineered 2026-11-15)

- Onyx's SurfaceFlinger puts the EPDC update list in the **standard HIDL composer command buffer** as a vendor extension command. The composer's dispatcher (around `0x317e4`–`0x318b4`) compares the opcode against `0x08000000`, `0x08010000` and **`0x08020000`**. `0x08020000` jumps to the handler at `0x36120`, which calls the reader at `0x3690c`.
- Layout: command word `0x0802LLLL`, with the length `LLLL` in 32-bit words. Payload: `n`, then `n` entries of 5 words. The reader copies them as `{w0,w1,w2,w3,w4}`, most likely `left, top, right, bottom, mode`. The handler computes `n = (LLLL - 1) / 5` and logs `Epdc list not matched, use item count` when it differs from the stated `n`.
- `0x08010000` → handler `0x36098` (Onyx, purpose unknown). `0x08000000` → the Qualcomm extension path (`0x43ad8`).
- Only one HIDL composer client exists (SurfaceFlinger), so the command has to come from inside that stream or from the composer side. Candidates:
  1. LD_PRELOAD shim in the vendor composer that synthesises a full-screen update when the frame carries no list. Needs the `onyxfb_update_data` layout, which the kernel reads through `EPDC_UPDATE_PARMS_ADDR`.
  2. A binary patch of the composer's empty-list path.
  3. A hook in SurfaceFlinger that appends `0x08020000` to each frame's command batch.

### Shim experiment (2026-11-15): `device/epdcshim`

- `libbooxepdc.so` (LD_PRELOAD into the vendor composer; wraps libdrm's `drmModeAtomicCommit`, which `libsdedrm.so` calls through PLT) adds `EPDC_UPDATE_CNT=1` + `EPDC_UPDATE_PARMS_ADDR` to every commit. The EPDC plane is id 69 (`plane-1`), with props 68/67. Settings come from `persist.boox.epdc.{w,h,wf,mode,flags,enable}`.
- Build: Homebrew `llvm` clang + `lld`, `--target=aarch64-linux-android30 -nostdlib -shared`, linked against the device's libdrm, liblog, libdl and libc (pulled to `device/epdcshim/sysroot`, gitignored).
- Loading: vendor processes may only load from `/odm:/vendor:/system/vendor`. A Magisk module (`/data/adb/modules/boox_epdc/system/vendor/lib64/`) overlays it as `/vendor/lib64/libbooxepdc.so`. That needed `/data/adb/magisk` repopulated with Magisk's binaries, because the data wipe had emptied it. Manual start: stop the init service, start the composer with `LD_PRELOAD`, restart surfaceflinger.
- **The framebuffer is landscape 1872×1404.** A portrait rect gives `ERROR … upd_rect [w=1404,h=1872]`. With 1872×1404 the kernel accepts and queues updates (`_o_e_b_p_q … upd_rect [0 0 1872 1404] waveform_mode[N]`), but **the panel stays white** with waveform 257, 2305 and 16777220.
- **DANGER: `waveform_mode=2` panics the kernel** (dump mode `900E`, needs a power hold). Only send waveform values seen in Onyx's own pipeline.
- Hypothesis: Onyx's composer path (`CommitEpdc` → `DisplayBase::CommitUpd`) also configures something the raw-commit shim skips. The kernel strings mention writeback (`_epdc_update_wb_direct`, `wb_4bit`, `onyx_epdc_update_wb_sg`), so it is probably the writeback block that makes the greyscale source frame. **Better hook point:** get the composer itself to run its EPDC path, by injecting composer command `0x08020000` into its command reader (or binary-patching its empty-list branch), rather than adding DRM props after the fact.
- Kernel debug: `echo 255 > /sys/class/sepdc/debug/debug_level` turns on the EPDC traces in dmesg.

### Shim v1 (2026-11-14): the composer runs its own EPDC path — panel works

- `epdcshim.c` v1 calls the composer's internal `setEpdcList` (vaddr `0x40248` in `vendor.qti.hardware.display.composer-service`, args `(ignored, display<0x16, std::vector<item{a,b,c,d,mode}>*)`) from a thread after each frame. The constructor checks the prologue bytes at `0x40248` before using it. Item values come from `persist.boox.epdc.{a,b,c,d,list_mode,disp,period_us,enable,always}`. The v0 raw-prop path sits behind `persist.boox.epdc.raw=0`.
- Mode word → effect: `0x901`–`0x904` = waveform 1–4 partial. `0x1000004` = waveform 4, flags 0x8000. `0x10/0x20/0x40/0x80` = waveform 2 **full update that flashes on every frame** (unusable as a default). Default `list_mode=2307` (`0x903`).
- Result: after a plain reboot, dmesg shows `update_to_display … waveform_mode = 3, update_mode = 0, Rect[0 0 1872 1404]` and the camera shows the LineageOS setup wizard matching the screencap.
- **Install (reproducible):** `device/epdcshim/build.sh` then `device/epdcshim/install.sh`. The boot image must carry the `boox_composer` service from `device/boox-adb.rc.template` (it replaces the stock composer service with one that sets `LD_PRELOAD`).
- **Why LD_PRELOAD was ignored at first — two AT_SECURE causes:**
  1. `capabilities` in the service definition raises caps at exec → AT_SECURE. The template omits it.
  2. The init → `hal_graphics_composer_default` SELinux transition sets AT_SECURE unless policy grants `noatsecure`. The module's `post-fs-data.sh` adds `allow init hal_graphics_composer_default process noatsecure` with `/data/adb/magisk/magiskpolicy --live`.
- Open: per-region rects instead of full screen, a periodic full refresh against ghosting, and mode selection per content.

### Overlay planes never reach the panel (2026-11-14)

- Symptom: Android drew the Wi-Fi password dialog and keyboard (screencap shows them), but the panel kept the list underneath. The kernel kept queuing full-screen `waveform_mode[3]` updates every 0.5 s.
- Cause: the EPDC conversion reads only the primary DRM plane. HWC put the dialog, the dim layer and the IME on overlay planes.
- Fix: `service call SurfaceFlinger 1008 i32 1` (Disable HW overlays → GPU composition into one plane). Camera-verified: the dialog and keyboard appear. It does not survive a reboot, so the module's `service.sh` runs it at boot_completed (see `device/epdcshim/install.sh`).
- Animations off (`window/transition/animator` scales 0): animation frames under partial waveform 3 left smeared traces (owner photo).
- Light theme (`cmd uimode night no`) + `high_text_contrast_enabled=1`. Text is still pale grey on the camera (98th-percentile brightness 213 vs text 160). Waveform 4 and a full refresh did not change that, so contrast work belongs in the colour pipeline.
- **Never overwrite the live `libbooxepdc.so` in place.** The composer maps it, and `cp` onto the same inode crashed it twice (`SIGSEGV pc 0x4fe0` from `epdc_thread`, 2026-11-14). The composer restart restarted SurfaceFlinger, which reset the SF 1008 overlay setting, and the panel lost dialogs again. `install.sh` now writes `.new` and runs `mv` (new inode, takes effect at the next boot). `service.sh` re-applies 1008 whenever the SurfaceFlinger PID changes.

### Shim v2 (2026-11-14): changed-region updates

- The item is `{left, top, right, bottom, mode}`. Evidence: sending `240,176,456,1228` made the kernel log `upd_rect [l=240, t=176, w=216, h=1052]`.
- The composer's framebuffers are 1920 px wide (virtual, `fb_width_virt[1920]`). The panel is 1872, so clamp rects to 1872x1404.
- v2 hooks libdrm's exported `drmIoctl` (`libdrmutils`/`libsdedrm` import it). On `ADDFB2` (`0xC06864B8`) it records fb_id → handle/pitch and exports a dmabuf right away (`drmPrimeHandleToFD`). `RMFB` (`0xC00464AF`) unmaps and closes it. The commit hook takes the largest framebuffer in the atomic request (FB_ID prop) as the frame.
- The thread diffs that frame against its own copy (`DMA_BUF_IOCTL_SYNC` around the read). It sends the changed bounding box (8-px aligned, `persist.boox.epdc.pad` default 8) or nothing when the frame is unchanged. `persist.boox.epdc.diff=0` falls back to full-screen updates. Example: one tap → `rect 808,624 256x184`.
- Build with `-mno-outline-atomics`: otherwise clang emits calls to `__aarch64_swp4_acq`, which the device does not export, and the composer cannot load the shim.

### Kernel panic from narrow planes (2026-11-14) — guard in the shim

- Symptom: crash-dump mode (`05c6:900E`) while the owner typed the boot PIN. pstore (`/sys/fs/pstore/dmesg-ramoops-1`) showed `Unable to handle kernel paging request` in `__onyx_epdc_buf_put_queue` ← `onyx_epdc_pd_image` ← `drm_atomic_helper_commit_planes_epdc`. The preceding lines created framebuffers 704x1404 and 1216x1404.
- Cause: at boot, before overlays were disabled, HWC put the keyguard on narrow planes. The EPDC read a full-width region from a narrow plane and ran off its end.
- Guard: the shim sends an update only when the commit carries exactly one framebuffer of at least 1872x1404 (`g_safe`). Otherwise it logs `skip update`.
- `service.sh` re-applies SF 1008 every 10 s. A one-shot call at boot_completed did not stick: SF reported `h/w composer enabled` again after boot.
- The PIN was removed (owner's decision), so reboots do not wait for an unlock. With a PIN, `sys.user.0.ce_available` stays empty and `/sdcard` (screencap) fails until the owner unlocks.

### Front light (2026-11-14)

- `/sys/class/backlight/onyx_bl_br` = front-light brightness (0–28, world-writable). `onyx_bl_ct` = colour temperature (0–24). `panel0/1-backlight` (what the lights HAL drives) do nothing on this panel.
- Camera evidence: panel mean 160 → 195 → 165 for `onyx_bl_br` 0 → 28 → 0.
- `device/epdcshim/module/service.sh` maps `settings system screen_brightness` (1–255) to `onyx_bl_br` once per second. The lowest slider position turns the light off. Measured: 255→28, 128→14, 1→0, 100→10.
- Open: map Night Light to `onyx_bl_ct`.
- The module scripts are now real files (`device/epdcshim/module/`), which `install.sh` pushes. Before this, generated `printf` strings caused escaping bugs. To restart `service.sh` without a reboot, run `pkill -f boox_ep[d]c/service.sh`. The bracket keeps pkill from matching its own su shell.

### Waveform choice, camera-measured (2026-11-14, `booxctl flicker`)

- Metric: `flash_area` = fraction of the panel that leaves the range of its values 0.7 s before and after (flash, ghost blink). Popups that stay longer than 0.7 s do not count. Scenario: Home → Settings, 30 fps.

  | Mode | Changed area | Flash area | Notes |
  |---|---|---|---|
  | `0x901` (wf1) | 73% | 58% | |
  | `0x903` (wf3) | 74% | 96% | Whitest whites, p98 206 |
  | `0x904` (wf4) | 73% | 55% | p98 198. **New default** |
  | `0x1000004` | 0.3% | 0 | Panel did not update |

- Full-screen vs changed-rect updates: same flash area (page change 96–98%, volume popup about 2.6%). `update_mode 0` is partial, so the EPDC drives only changed pixels in either case. The rect mainly reduces EPDC work and overlapping updates.
- Partial modes cannot clean ghosting, because they skip unchanged pixels. Idle clean: after `clean_after` (default 30) fast updates and `clean_idle_ms` (1500) idle, the shim sends one `clean_mode` (default `0x10`, full update) over the union of those rects. This is a deliberate flash. It is set by props, and the Settings entry is open.
- The display can go to `Dozing` (screen off) despite `stay_on_while_plugged_in=7`. The panel then keeps its last image and receives no frames. `input keyevent WAKEUP` before measurements.

### Panics, part 2, and the tone curve (2026-11-14, shim v3)

- Two more panics (`rgb32_to_4bit_32` ← `__onyx_epdc_buf_put_queue`), both right after 704x1404 framebuffers. The EPDC converts on ANY commit. A guard that only skips the shim's own updates cannot help.
- Hole found: `FB_ID` and `IN_FENCE_FD` have a **different prop id per plane**. The shim had probed plane 0 (obj 69) only, so multi-plane commits read as `nfb=0` and the guard never saw them. It now probes all planes.
- Guard v2: the commit hook returns `-EINVAL` for every commit, TEST_ONLY validations included, that is not exactly one fb of at least `persist.boox.epdc.minw` (1872) x 1404. SDM then falls back to GPU composition. Detector proof: with `minw=1921`, 5 rejects were logged and the composer survived. With `minw=1872` the guard does not fire in normal use.
- Plus `vendor.display.primary_mixer_stages=1`, set by `magisk resetprop` in `post-fs-data.sh` (before the composer starts), and SF 1008 re-applied every 10 s. With overlays re-enabled by hand, all layers stayed CLIENT and nothing panicked.
- **Colour transforms never reach the panel.** The SF 1015 matrix and accessibility inversion do not show: the QTI composer applies them in DSPP, after the plane the EPDC reads.
- The tone curve therefore runs in the shim's commit hook. It waits for the plane's `IN_FENCE_FD`, then maps every pixel with alpha 0xFF: luma → LUT (`persist.boox.lut.black` 40, `white` 235), written back as grey with alpha 0xFE. The 0xFE marker makes the pass idempotent when SF re-presents a cached buffer. The diff runs in the same pass, and the thread only sends the pending rect. The dmabuf is exported `O_RDWR` and mapped `PROT_WRITE`. `persist.boox.lut.enable=0` turns the pass off live. Proof that the curve reaches the panel: `black=128 white=129` turned the card backgrounds pure white.
- Cost: 48–72 ms per frame in the commit path. The buffers are uncached for CPU reads (about 10 MB per frame). Open: reduce this.
- Settings: `high_text_contrast_enabled=0`, because the white text halos showed as grey patches (owner noticed). `font_weight_adjustment=300` (Bold text) made thin Material text legible on camera.
- **"Crash" that was sleep:** the display went `Dozing` with `mLastSleepReason=application` (SystemUI uid 10142). Two slow taps on the status bar had triggered LineageOS's double-tap-to-sleep (`content://lineagesettings/system` `double_tap_sleep_gesture`). It is now 0. `device/eink-settings.sh` applies all e-ink Android settings idempotently.
- White wallpaper (owner request: the grey default was hard to read and ghosted): Night mode: no
done
- White wallpaper (owner request: the grey default was hard to read and ghosted): `WALLPAPER=1 device/eink-settings.sh` writes the image files as root and removes `wallpaper_info.xml`, so the colour hints are recomputed on the next boot. Otherwise status-bar icons stay white on white.
- Tone-pass speed-up: the per-pixel loop on the uncached dmabuf took 53–63 ms. The cache-sync ioctls took only 2–8 ms. Fix: `memcpy` each row into a cached buffer (bulk reads), skip rows equal to the previous mapped frame (re-presented buffer), reuse the previous mapping for rows whose raw content did not change, and compute only changed rows. Loop now 14–20 ms, whole pass about 25 ms.

### E-ink entry in Settings (2026-11-14) — `device/einksettings`

- A Java app without Gradle (`build.sh`, SDK in `~/boox-backups/tools/android-sdk`). It adds an activity tile to Settings > Display (`com.android.settings.action.IA_SETTINGS`, category `com.android.settings.category.ia.display`).
- **Settings shows injected tiles only for system apps** (`TileUtils.loadActivityTiles` drops entries where `ResolveInfo.system` is false). The APK therefore lives in its own Magisk module, `boox_einksettings`, at `/system/app/EinkSettings/`.
- `persist.boox.*` is `default_prop` (`getprop -Z`), which apps cannot set. The app writes through Magisk su, granted via `install.sh grant` (policies row uid 10190, policy 2).
- Verified on the device: the tile appears, the screen shows "Root access: Granted", and "Refresh screen now" set `sys.boox.epdc.force` to 1794674615.
- `persist.boox.epdc.clean_after=0` now means off. The shim had treated 0 as "clean every idle tick", possibly with an empty rect.

### Content-adaptive tone curve (2026-11-14)

- Bands of 32 rows / tiles of 32 px. A changed band is classified per tile from its raw pixels (every 2nd px and row). More than `persist.boox.lut.photo_pct` (35) % mid-grey (luma 48–208) = photo, which gets the curve `pblack/pwhite` (16/245). Other tiles = text/UI, curve `black/white` (40/235). `persist.boox.lut.adaptive=0` uses the global curve.
- Row states: 0 = equal to the previous mapped frame (skip), 1 = raw unchanged (rewrite the previous mapping), 2 = new raw (map), 3 = an already-mapped buffer (alpha 0xFE) with different content (diff only). State 3 exists because SF alternates buffers.
- Cost: 36 ms per frame when every row is new (scrolling), less for local changes.
- Camera A/B on omni.se (Laplacian detail, same crop): hair 2.44 adaptive vs 1.86 global, face 2.91 vs 3.24, text 13.04 vs 13.11. Text is unaffected and photos keep more highlight detail by eye. The metric is limited by camera blur.

### Boot guard (2026-11-14)

- `install.sh` keeps the replaced shim as `libbooxepdc.so.prev` (only when the new file differs). `post-fs-data.sh` increments `/data/adb/boox_boot_count`, and `service.sh` resets it 60 s after boot_completed. At count 3, `post-fs-data` restores `.prev`, keeps the failed file as `.bad` and logs to `/data/adb/boox_guard.log`. This runs before Magisk mounts the module, so the composer never loads the bad shim.
- Verified: with `.prev` staged and the counter at 2, the next boot logged "boot guard: 3 unhealthy boots, restored previous shim", left `.bad` and loaded the shim (maps 4). A normal boot: counter 1 at boot_completed, 0 after 60 s.
- Limit: a panic later than 60 s after boot does not count.
- **Bug fixed (2026-11-14): stale panel after boot.** A state-3 row (SF re-presenting an older mapped buffer) set the previous-mapped copy without touching the previous-raw copy. The next fresh frame then matched the raw copy and got the older buffer's mapping written back, so the panel kept the boot overlay. Fix: state 3 invalidates the raw row, and any change to the curve or adaptive settings invalidates all raw rows.
- **Night Light → warm front light.** `onyx_bl_ct` 0 = cold, 24 = warm (camera R/B 1.037 → 1.174). `service.sh` maps Night Light's temperature (2596–4082 K, lower = warmer) linearly onto 24…0 every 2 s. Night Light off = 0. Verified: on at 2850 K → ct 19, off → 0. Android's Night Light schedule therefore warms the front light automatically.
- Chrome scrolling (HN, camera at 30 fps): flash area 0.5–0.9% per scroll, so no Chrome flag change is needed. The flicker meter at 468x351 with blur under-counts changes in thin text (3.5% changed for a full-page scroll). Use a larger warp size before judging text content.

### On-device glue updates (2026-11-14)

- Settings > Display > E-ink > **Check for updates** (`Updater.java`) reads the public releases API (`jonaseck2/boox-note5`, no token) and takes the newest `glue-v*` release. It checks the zip against its sidecar and the three files against the manifest, requires the boot guard in the new module, stages the files in the app's cache, and installs through su like `install.sh` (`.prev`, `.new` file, rename). It then offers a restart.
- Verified: release 2026.11.14.3 was installed from the tablet, Restart was tapped, and the post-check passed (`update.postcheck`: composer, version, maps, no new panic record).
- **System APK fact:** PackageManager rescans `/system` APKs only when the build fingerprint changes. A replaced APK in the Magisk module keeps its old package record (version 1.0, no INTERNET permission) until then. Fix: `adb install -r` of the same, identically signed APK. That makes it an updated system app (flags `SYSTEM … UPDATED_SYSTEM_APP`), and the Settings tile stays. `device/einksettings/install.sh` now does this automatically.
- **Emboldening (2026-11-14).** Chrome ignores Android's Bold text for web content (screencap dark-pixel fraction 3.15% at weight 0 vs 3.11% at 300). In text/UI tiles the shim takes the darker of each pixel and its left neighbour (`persist.boox.lut.bold`, default 1), so strokes grow by 1 px. Photo tiles are untouched. Camera A/B on HN: dark-text fraction 1.66% → 4.63%, darkest text 134 → 122.
- **The settings app ships in glue releases** (`EinkSettings.apk` when built). `booxctl update` installs it with `adb install -r`. On the tablet, "Check for updates" verifies it and installs it from a detached root shell on Restart (`pm install -r`, then reboot), because installing its own package kills the app. Bootstrap: an app older than 1.3 ignores the APK, so install 1.3+ once over USB. Verified: release 2026.11.14.6 updated from the tablet. The app went 1.3 → 1.4 and the module to .6, the composer maps the shim, and no new panic record appeared.

### Building the shim without device libraries (2026-11-14)

- `device/epdcshim/stubs/symbols.txt` lists the shim's imports (library, name, version). `stubs/mkstubs.sh` generates stub `libc/libdl/liblog/libdrm.so` from it (names and versions only). `build.sh` uses `sysroot/` when present, else the stubs.
- Verified: the stub-linked `libbooxepdc.so` is **byte-identical** to the build against the real device libraries (`cmp`). `-Wl,--no-undefined` makes a missing stub entry a link error (mutation: removing `memset` → `ld.lld: error: undefined symbol: memset`). A new import therefore needs a line in `symbols.txt`.

### Home screen for e-ink (2026-11-14)

- The owner found the Home screen bleak. Its DeskClock "Digital clock" widget draws the time in the theme's light accent tone, which the tone curve (white point 235) maps to white. The search bar's light fill becomes white too.
- Changes: monochrome theme (`theme_style MONOCHROMATIC`, preset grey), `contrast_level 1.0` (Color contrast: High), themed icons on (Wallpaper & style → Icons; UI only, no setting key found). Both settings are in `device/eink-settings.sh`.
- Layout via Launcher3's database `/data/data/com.android.launcher3/databases/launcher_6_by_5.db` (table `favorites`): stop the launcher, replace the file (owner `u0_a140`, mode 660, `restorecon`), press HOME. The layout now: search bar, a row with Calendar/Contacts/Gallery/Camera/Music/Files (`cellY` 2), and a dock (`container` -101) with Chrome, Play Books, Storytel, Keep, Play Store, Settings. The clock widget was removed (time and date are in the status bar). Original backed up as `~/boox-backups/launcher_6_by_5.orig.db`.
- Launcher "Double tap to sleep" (Home settings) is off. Like the status-bar gesture, slow e-ink taps would trigger it.
- **Default wallpaper: The Great Wave (Hokusai, public domain) as a light print** (owner, 2026-11-14). `booxctl wallpaper [wave|white]` downloads the Wikimedia original (sha256 pinned), cover-crops it to 1872x1404 and keeps 45% of the ink, then installs it as root and reboots. The full-contrast version made Android choose **white** launcher labels and status-bar icons, which were unreadable on the panel. The light print gets dark ones (camera-verified).
- **Dark mode was not suitable** (superseded by the dark profile below) (camera, 2026-11-14): the previous screen ghosts clearly behind dark Settings and quick-settings backgrounds, because wf4 partial updates don't fully drive large dark areas. Chrome's dark UI comes out mid-grey. Light mode stays the default (`eink-settings.sh`: `cmd uimode night no`).

### Dark theme: the shim's dark profile (2026-11-15)

- Cause of the poor dark theme, measured with `booxctl audit` on 24 screens (77 of 595 elements flagged, light mode 32 of 579):
  1. Material dark surfaces sit at luma 30–70. The light curve (black point 40) maps them all to black, so cards, tiles and icon discs merge.
  2. The photo test (luma 48–208 over 35 % of a 32 px tile) classifies those surfaces as photo tiles. The two curves then split one surface into visible 32 px blocks.
  3. The bold pass keeps the darker neighbour, so it thins light text on dark surfaces. A 1 px light stroke disappears entirely (test `test_auto_dark_off_keeps_light_curve`).
  4. The idle clean `0x10` (waveform 2, full) leaves a dark page **white** on this panel: camera mean 133 → flash 224 → 176 (white), 3 of 5 runs.
- Fix in `device/epdcshim`: per frame, the shim measures the share of luma < 64 on a 4 px grid. Above `persist.boox.lut.dark_frac` (60 %) it switches to the dark profile and back below 50 %. It logs `profile dark|light`. The dark profile has its own curve, `lut.dark_black` 20 / `lut.dark_white` 180, and photo threshold `lut.dark_photo_lo` 72. Its bold pass keeps the lighter neighbour. It cleans after `epdc.dark_clean_after` (10) updates with `epdc.dark_clean_mode` `0x13`, and once after every profile change. `lut.auto_dark 0` turns the profile off. `audit.simulate` mirrors all of it (`audit.dark_frame`).
- Clean modes on a dark page (camera, 30 fps, 2026-11-15): `0x10`, `0x20`, `0x40` end white. `0x11` shows no flash and leaves the previous screen's icons. `0x13` flashes once and ends on the image (3 of 3 runs, panel mean 117–134). `0x14` does not clean (the full wallpaper stays as a ghost).
- Result: dark mode 77 → 42 flagged of 595 (most of the rest are scoring artifacts: back-arrow discs, Chrome's disabled back/forward). Light mode unchanged (33 of 571). Light screens never trip the detector at 60 %.
- Curve choice from the offline sweep on the dark captures (flagged of 595, with the per-tile polarity bold): 40/235 → 74, 16/235 → 75, 16/200 → 46, 10/190 → 45, **20/180 → 44**, 0/170 → 47.
- `device/eink-settings.sh` keeps a dark theme the owner chose (`ui_night_mode` 2). Otherwise it sets light.
- Still open: the dark theme still ghosts more than the light theme between cleans, because wf4 partial updates do not fully drive large dark areas. Dimmed QS tiles (Wallet, Device controls, Battery Saver: 148 on 35) and the notification expand chevrons stay low contrast.

### Visual-style audit (2026-11-14, `booxctl audit <dir>`)

- Method: `audit.simulate` replicates the shim's tone pass in NumPy (luma, 32 px photo/text tiles, both curves, 1 px bold), so it predicts the panel image without camera noise. `audit.score` gives each uiautomator text or icon node a contrast: paper = the box's dominant grey, ink = 10th percentile of the pixels that differ from paper by more than 12. Verdicts: `vanishes` (< 40), `low` (< 100, or both tones on the same side of mid-grey), `ok`. Covers 24 screens (system UI, Settings, Chrome, Books, Keep, Store, Calendar, Files, Contacts, keyboard, Storytel).
- Result: 587 elements, **39 flagged (6.6%)**. Groups:
  1. Translucent backgrounds: app drawer and notification shade/QS sit on a mid-grey layer (about 200) over the wallpaper. Labels and inactive tiles end up grey on grey (e.g. QS tiles 140 on 212).
  2. Material's light greys on white: expand chevrons (223/255), "Clear all" (158), inactive-tile icons.
  3. Deliberately faint states: disabled Chrome back/forward, Calendar weekend letters, Settings footnotes.
  4. App content: a Play Books banner (57 on 87).
- **Rejected, with reasons:**
  - **Local contrast amplification** (paper − k·(paper − v) per text tile): flags 39 → 23 at k = 3, but blocky tile seams appear around rounded QS tiles and icons (each tile picks its own paper). It games the metric and looks worse.
  - **Stronger global curve** (black 100 / white 240): flags 39 → 31, but icon seams appear where photo and text curves diverge more, and the text gain is small. The curve stays at 40/235.
- Conclusion: the remaining issues have to be fixed where Android draws them (opaque drawer and shade backgrounds through resource overlays), not in the tone curve.
- Scoring caveat found while building the tool: a 5th-percentile ink misses short text in full-width label boxes (2% coverage). Hence the foreground-pixel method (`test_short_text_in_wide_box_is_found`).
- **Overlays (`device/overlays`, Magisk module `boox_overlays`, static RROs in `/system/product/overlay`):** SystemUI `notification_scrim_base`, `notification_scrim_fallback`, `shade_panel_fallback` and framework `shade_panel_scrim_color` plus `surface_effect_0..3_color` → white. The launcher's `materialColorSurfaceDim` → white. Device-resource names come from the device's own `framework-res.apk`: the SDK `android.jar` IDs differ for private resources. Check with `cmd overlay lookup <pkg> <res>`. Result: the shade background went 218 → 255, and the audit went from 39 to 32 flags (shade 8 → 4). Camera: QS and notifications on clean white. Delivery: glue releases carry `overlays/BooxEink-*.apk` (CI signs them with the app key). `booxctl update glue` runs `device/overlays/install.sh` with `SRC`, and the app's updater (v1.5+) copies them into the module with rename. The module's `version=` follows the glue version.
- **Home screen and widget sweep (2026-11-15).** Before: the Google search bar was a white pill with grey glyphs on the busy wallpaper, and the themed icons were light-grey discs. After: home audit 1 → 0 flags, camera-confirmed.
  - Themed icons: the launcher overlay sets `themed_icon_background_color` and `themed_icon_adaptive_background_color` to black and `themed_icon_color` to white.
  - Google search widget: the Google app's own setting, not an overlay. Path: Google app → account avatar → Settings → Customize Search widget → Custom, Saturation slider fully left, Transparency 0. The result is a black bar with white glyphs. "Dark" gives a #3C4043 bar with coloured glyphs that land mid-grey (audit "low"). "Device" and "Light" give a pale bar that the LUT clips to white. The setting lives in the Google app's data, so a data wipe resets it.
  - Etar calendar widget: its texts are white on a transparent body, written for a dark wallpaper. `device/overlays/etar` sets `appwidget_no_events` and `appwidget_date` to black.
  - Checked and left as they are: At a Glance "Solid" (black text on a white pill), Clock "Backed" (dark digits on a light pill), Keep note collection (white card, black text), Play Books "Your books" (covers). The audit flags only a dark book cover.
  - Rejected: a lighter wallpaper print (ink 0.30 and 0.22, simulated). The photo/text tile switch turns the faint art into speckle, and the black UI elements already dominate at 0.45.
  - Widget automation: in the launcher picker, a tap on a preview shows `Add <name> widget`. To remove a widget, long-press it, wiggle, then drag to the **Remove** target at x 636–859, y 42–150 (not the screen centre).
- **Open: the tablet app-drawer panel stays `#C6C6C6`.** It isn't reachable by resource overlay. Eight launcher surface tokens, `shade_panel_scrim_color` and `surface_effect_*` all resolve to white (`cmd overlay lookup`) without changing it, so it's probably blended in code. Next idea: a launcher with an opaque drawer, or a code patch. `disable_window_blurs=1` did not change it either.
