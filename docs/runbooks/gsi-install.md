# Installing a GSI on the Note5 (learned 2026-11-09)

## DSU does not work here (root cause, verified)

DSU installs fine (`com.android.dynsystem` → "Dynamic system is ready"). Booting the image panics in first-stage init. RAM dump (`edl memorydump --pid=0x900e` in crash-dump mode), kernel log:

```
init: DSU slot: dsu
init: [libfs_avb]Device path not found: /dev/block/by-name/vbmeta_b
init: [libfs_avb]Device path not found: /dev/block/by-name/boot_b
init: Failed to mount /system
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00007f00
```

Seen with Google GSI 15 (AP4A.241205.013) and 16 (CP11.251209.009.A1). It is not a version or kernel problem: in DSU mode, first-stage init never creates the `vbmeta_b`/`boot_b` device links that AVB needs. Other notes:

- A plain reboot discards an uncommitted DSU install. Commit with `am startservice -n com.android.dynsystem/.DynamicSystemInstallationService -a com.android.dynsystem.ACTION_REBOOT_TO_DYN_SYSTEM`.
- `gsi_tool install` from a root shell fails with `read gsi chunk: Bad file descriptor`.

## Permanent install (the route that writes the device)

1. `booxctl.lp.build_super(<backup super.bin>, <raw system.img>, out)` keeps `vendor_b` byte-identical. It drops `system_ext_b`, `product_b` and `system_b-cow`, gives `system_b` the free sectors, and rewrites metadata slot 1 (primary and backup). Slots 0 and 2 are left alone (slot `a` cannot boot anyway). Maximum system image is about 3.75 GB.
2. `vbmeta_b` copy with flags=3 at offset 120 (hashtree and verification disabled). This is needed because stock fstab mounts `system` with `avb=vbmeta_system` and `avb_keys` q/r/s-gsi.
3. EDL: `w super`, `w vbmeta_b`, `e metadata`, `e userdata` (both are `formattable`), then `reset`. Read back `vbmeta_b` and the first 8 MB of `super` and compare hashes.

## LESSON: build adb into boot before the first boot of any new system

A fresh userdata starts with adb off and USB in "charging only". The Mac sees **no USB device at all**, and the Note5 has no volume keys for EDL. On 2026-11-09 the Android 15 GMS GSI hung before drawing anything (panel frozen white, no USB), and the only way back was exhausting the A/B retry counter with repeated power cycles.

Before flashing any new system, flash a `boot_b` with a Magisk `overlay.d` rc that forces adb:

- `booxctl.bootimg.add_ramdisk_file(boot_b.magisk.img, out, "overlay.d/boox-adb.rc", rc)` (header v2, gzip ramdisk).
- The rc runs `${MAGISKTMP}/magisk resetprop -n ro.adb.secure 0` at post-fs-data and sets `persist.sys.usb.config` / `sys.usb.config` to `mtp,adb`.
- Built: `~/boox-backups/gsi/boot_b.magisk.adb.img` (SHA-256 `138c012c…`).

Also: give up on a silent boot after **3 minutes**, not 16.

## LESSON: power cycles cannot force a slot fallback here

Stock marked both slots `slot-successful:yes`, and EDL writes do not reset that flag (fastboot or update_engine normally would). ABL only counts retries for slots that are *not* marked successful, so it boots `b` indefinitely, whether or not the system on it works. More than 8 early-interrupted boots changed nothing (2026-11-09).

**Recovery without adb therefore needs an EDL cable** (USB 2.0 D+ shorted to GND while plugging in; a MobileRead user reports it works on newer Onyx devices) or the internal test points. After EDL: `device/recover-edl.sh adb|stock`.

## Session lessons (2026-11-08/09), beyond the above

- **macOS USB prompt:** each new USB mode (bootloader, fastbootd, EDL, crash-dump) is a new accessory. Set System Settings → Privacy & Security → "Allow accessories to connect" to **Always** for unattended recovery.
- **Sandbox:** the Claude Code sandbox hides USB from libusb. Run `edl` outside it, and start it **before** `adb reboot edl`. A killed `edl` after the Sahara hello needs a power hold before the chip answers again.
- **Onyx stock overrides:** Onyx resets `force_waveform` to -1 on every app launch, and its SurfaceFlinger attaches per-update waveforms. Mode effects can only be measured where Onyx's framework is absent.
- **Camera measurement:** ffmpeg's avfoundation start latency varies. Detect events by signal shape (dip then overshoot), not by a fixed frame index. Always run a negative control.
- **Display under the GSI (open question):** the vendor composer imports no EPDC symbols. Only Onyx's system-side `android.hardware.graphics.common@1.0.so` defines `EpdcWrapper` parcel functions, so the vendor composer by itself is not linked to Onyx's changes. Why Android 15 drew nothing is unknown until adb works.
- **Testing:** after a mutation run, clear `__pycache__`. A stale `.pyc` once made restored code look broken.

## Google GSIs cannot run on the Onyx kernel (verified 2026-11-14)

Google GMS GSI 15 (AP4A.241205.013) in `system_b` boots far enough for adb (with `boot_b.magisk.adb.img`), composer, SurfaceFlinger and the boot animation. Then `system_server` aborts in a loop:

```
#01 /apex/com.android.tethering/lib64/libservice-connectivity.so (register_com_android_server_connectivity_ClatCoordinator+712)
#08 com.android.server.NetworkStatsServiceInitializer.<init>
BpfLoader: BPF_PROG_LOAD ... returned fd: -1 (Invalid argument) / Failed to load object ... Operation not permitted
```

Cause: the Onyx kernel `4.19.157-perf` lacks the eBPF features that the networking mainline module needs. The panel stays on the boot animation's first frame, because boot never completes. It is not a display problem.

Next candidates are TrebleDroid-based community GSIs (LineageOS, crDroid), which carry old-kernel workarounds. Precedent: Hisense A9 (SDM662, 4.19) runs LineageOS 20/21 GSIs.

**Recovery is now in place:** with the adb boot image, adbd starts before `system_server`, so `adb reboot edl` works even in a crash loop. EDL cable fallback: hold the cable button, force-restart with a 15 s power hold, and keep the button held about 5 s more. Release the button before flashing, or USB returns pipe errors.

## LineageOS 23.2 boots; the panel stays blank (2026-11-14)

- `LineageOS-23.2-20260524-GAPPS-EXT4-GSI` (MisterZtr, Android 16 QPR2, "added support for Android 11 vendors") in `system_b` gets to `sys.boot_completed=1` and the setup wizard (screencap OK). It has no system_server crash, so its patches handle the old kernel.
- **The panel never updates.** Composer and SurfaceFlinger run. Reading `panel_clean` (world-readable, works as shell) wipes the panel white, and then no frames follow. Leading hypothesis: Onyx's vendor composer only drives the EPDC when SurfaceFlinger supplies Onyx's EPDC lists. Next: with root, try `submit_upd_work`, `update_snapshot` and `/dev/ebc` ioctls, or a small service that turns plain commits into EPDC updates.

## LESSON: adb authorization must not depend on boot timing

The first adb boot image (`resetprop ro.adb.secure 0` at post-fs-data) worked on a fresh userdata. The next boot came up `unauthorized`, because the stored `persist.sys.usb.config=mtp,adb` started adbd **before** the resetprop. With an invisible panel, nobody can accept the RSA prompt, so it took the EDL cable again.

Fix (`boot_b.magisk.adbkey.img`, template `device/boox-adb.rc.template`): init writes the Mac's `~/.android/adbkey.pub` to `/data/misc/adb/adb_keys` at post-fs-data, sets `ro.adb.secure=0`, then runs `restart adbd`. It also grants uid 2000 root in Magisk's DB at boot_completed. Test any adb boot image across **two consecutive boots** before trusting it.

## State 2026-11-14 evening

- LineageOS 23.2 runs. adb and root survive reboots (`boot_b.magisk.adbkey.img`, two-boot test passed, read-back verified). Root: `/debug_ramdisk/su` (`booxctl` falls back to it).
- The panel stays white. The EPDC driver initialises and processes frames (counter 87 → 117 after `submit_upd_work` / `update_snapshot`), but the content is white while the UI is dark. The composer logs no EPDC activity. **Stock recovery draws fine** (minui, plain DRM), so the panel can show non-Onyx frames.
- Onyx recovery accepts **touch** (owner used it for Factory data reset). A factory reset clears the stored `persist.sys.usb.config` that broke the first adb image.
- Next: reverse-engineer what makes the vendor composer call `onyx_epdc_update_to_display` / `CommitEpdc` (likely a vendor.qti composer extension or DRM property fed by Onyx's SurfaceFlinger), and drive it from our own service.
