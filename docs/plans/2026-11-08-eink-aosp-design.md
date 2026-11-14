# Boox Note5 on current AOSP, tuned for e-ink — design

Date: 2026-11-08. Device facts: [docs/runbooks/device-facts.md](../runbooks/device-facts.md).

## Intent

The owner wants the Boox Note5 to behave like a standard Google Android device, as close to a Pixel
as the hardware allows, on the newest Android that runs. The display is a greyscale e-ink panel, so
the system must be tuned for it: contrast, colour-to-grey mapping and refresh behaviour.

Two reasons drive the change:

- Onyx's firmware is heavily customised. The owner cannot find standard Android settings in it.
- Onyx has ended support for this device (last firmware `4.0.2`, 2025-06-20, Android 11, security
  patch 2024-02-01). Onyx's device-specific libraries will not follow newer Android versions.

The agent runs the whole loop: flash, boot, observe, measure, tune. The owner is not in the loop.
The owner's only planned role is physical recovery, which the design works to avoid.

## Owner mandate (2026-11-08, owner's words condensed)

- The agent may change the tablet in any way needed, including wiping `/data`, replacing any
  partition, and changing vendor sepolicy.
- One limit: no step that risks a brick with no recovery path. Such a step is not forbidden. The
  agent **asks before** taking it.
- Objective: make the tablet as useful as possible on the newest possible Android, with a continued
  lifecycle (updates over USB, or OTA from GitHub releases).
- E-ink rendering adapts all visible content automatically (images, web, UI): contrast, hue and
  tone mapping, so content is both legible and pleasant to look at.
- The agent adds subagents and skills as needed.
- The agent asks the owner for help with human-side steps, and when progress stops.
- **Owner availability for physical steps** (button combinations, sign-in, 2FA): mornings and
  evenings, sometimes Fridays (working from home). A step that needs the owner waits for one of
  those windows. Batch such steps.

## Usage this optimises for (owner's statements)

- Chrome is the most used and the hardest app. The pages that matter most are
  `https://www.omni.se` and `https://news.ycombinator.com` (front page and comment threads).
- Google Play Books and Keep Notes are used and are easier.
- The stylus is **not used**. Pen latency and handwriting are out of scope.
- Priority now: **standard navigation working** — launcher, back/home/recents, notification shade,
  Settings, Play Store, Chrome.

## Goals

1. A current AOSP-based system image with Google apps (Play Store, Chrome, Play Books, Keep) boots
   and is usable on the Note5.
2. The e-ink panel updates correctly under that image: screen content appears, ghosting can be
   cleared, scrolling is usable.
3. E-ink settings (refresh mode, contrast/colour remap, per-app profiles) are entries in the
   standard Android Settings app.
4. A camera-based measurement loop scores readability per app and page. Tuning is accepted only
   when it improves the score.
5. Content-adaptive rendering: images, web content and UI are remapped for a greyscale panel. The
   remap considers contrast, hue separation (colours that differ in hue but share a luminance must
   stay distinguishable) and tone, so photos look pleasant and text stays legible. The camera loop
   scores both legibility and image quality. Image quality is scored as tonal range and detail
   preserved in photos.
6. A continued lifecycle: versioned builds published as GitHub releases. The device installs
   them over USB (a script on the Mac) or over the air (an updater that reads GitHub releases).
   An update keeps the e-ink component working and keeps user data.

## Non-goals

- Stylus, handwriting, low-latency pen drawing.
- Onyx apps (Library, Notes, NeoBrowser, BOOXDrop, AI Assistant, Onyx store and account).
- Pixel-exclusive software (Pixel Launcher, Pixel-only features). "Pixel-like" means stock AOSP
  look and behaviour plus Google Mobile Services.
- Front light or warm-light control, unless the device turns out to have it and it costs little.

## Anti-goals (a failure even if it technically works)

- E-ink controls shipped as a separate launcher app with its own icon.
- A process that needs the owner to press buttons, read the screen or approve steps.
- Porting Onyx's Android 11 framework code forward version by version. It ties the system to an
  abandoned codebase.
- An unrecoverable device: any write to the **active** slot, or to slot-independent partitions,
  done without a verified full backup. A write to the inactive slot is allowed before the backup
  exists, because the active slot still boots stock (agent's call).

## Constraints and known facts

From [device-facts.md](../runbooks/device-facts.md):

- Qualcomm `bengal` (SM6115 / Snapdragon 662), 3.7 GB RAM, 1404x1872 panel at 240 dpi, greyscale.
- Bootloader **already unlocked** (`vbmeta.device_state=unlocked`, `verifiedbootstate=orange`).
- Treble enabled, A/B slots (active `_b`), dynamic partitions (`system` is flashed from
  fastbootd), VNDK 30 (Android 11 vendor).
- No root on stock. `ro.debuggable=0`.
- E-ink control on stock lives in Onyx framework code on the **system** partition
  (`onyx_device_service`, `oec_service`, `libonyx_epd_listener.so`, `libonyx_neo_dither.so`). The
  kernel driver and vendor partition stay when `system` is replaced.
- Control channel: adb and fastboot over USB from the owner's Mac. adb needs `ADB_LIBUSB=1` on this
  Mac.
- Camera: the Mac's built-in `FaceTime HD Camera` faces the propped tablet (landscape), at about
  1 camera pixel per panel pixel. There is perspective skew and lamp glare on the left edge.

## Approach (decided with the owner)

**Option A: a generic system image, with e-ink support rebuilt against the kernel interface.** The
owner rejected Option B (keep Onyx's system, debloat it), because Onyx's libraries will not be
compatible with newer Android.

**Reverse-engineer the interface, not the libraries.** The object of reverse engineering is the
boundary between Onyx's system code and the vendor/kernel side. That boundary is device files,
ioctls, sysfs nodes or a vendor HAL. A small new service calls that boundary directly. Onyx's
libraries are read (jadx for Java, Ghidra for native) only to learn the boundary.

### Phases

| # | Phase | Exit check |
|---|---|---|
| 0 | **Backup and recovery.** Get temporary root without flashing (`fastboot boot` a Magisk-patched copy of the stock `boot` image). Dump every partition to the Mac with checksums. Pull Onyx framework jars, APKs and libraries for analysis. Write and dry-run a restore script. Find out whether an EDL (Qualcomm emergency download) loader exists for this device. | The partition dumps and their checksums exist on the Mac. The restore script lists every partition. EDL availability is recorded in the runbook. |
| 1 | **Map the e-ink interface** on stock: trace `onyx_device_service` (strace and open file descriptors), list the kernel display/EPD device nodes and sysfs, decompile the Onyx framework classes that call them. | A shell command, run as root on stock, triggers a full refresh and switches between at least two refresh modes, as confirmed by the camera. |
| 2 | **Generic system image (GSI) bring-up.** Pick the newest AOSP-based GSI with Google apps that supports an Android 11 (VNDK 30) vendor. Flash it from fastbootd. Prefer keeping stock bootable on the other slot if the `super` partition has room. Otherwise rely on the phase 0 backup. | The device boots. adb works. Screencap shows the launcher. The camera shows the panel updating, by itself or through the phase 1 commands. |
| 3 | **Standard navigation.** Launcher, back/home/recents, notification shade, Settings, Play Store sign-in, Chrome. Basic e-ink usability: a refresh after each screen change, so ghosting does not build up. | A scripted walk-through (`adb shell input` plus uiautomator) completes: open Settings, open Chrome, load HN, go back, go home, open recents. The camera frame at each step matches the screencap above a readability threshold. |
| 4 | **E-ink service and Settings entries.** A privileged system component drives the kernel interface. It exposes refresh mode and contrast/remap settings as entries in Settings (Settings injection, no launcher icon). It applies per-app profiles on foreground app change. | The settings appear in the Settings app. Changing them changes the camera-measured result. No new launcher icon exists. |
| 5 | **Content-adaptive tuning loop.** Score the benchmark set for legibility and image quality, adjust remap parameters, keep only improvements. | The benchmark score beats the phase 3 baseline on every benchmark page. Photo pages do not lose tonal range. |
| 6 | **Lifecycle.** Build pipeline producing versioned releases on GitHub. USB install script. OTA updater on the device that reads GitHub releases and installs to the inactive slot. | A release published on GitHub installs over OTA to the inactive slot, boots, passes the phase 3 walk-through, and the e-ink component still works. A failed boot falls back to the previous slot. |

The owner's priority is phases 0–3. Phases 4–6 follow.

**Sign-in (owner's choice):** the owner signs in to Google once on the device, in one of the
availability windows, when the agent asks. Until then, phase 3 checks run without the Play Store
sign-in step.

**Releases (owner's choice, 2026-11-09):** a private repository on the owner's personal GitHub. The OTA updater on the device needs a read-only token for it.

**Phase 2 route (agent's call, 2026-11-09):** test generic images first through Android's Dynamic System Updates (DSU). DSU boots a GSI from `/data` without touching `super`, and a reboot returns to stock. The tablet has `com.android.dynsystem`, `ro.virtual_ab.enabled=true` and 40 GB free. A permanent flash into `super` (via EDL, since fastboot flashing is removed) comes only after a GSI passes on DSU. The camera proof for refresh modes also moved to phase 2: on stock, Onyx's SurfaceFlinger overrides `force_waveform` per update (see `docs/runbooks/eink-interface.md`).

**User data:** a wipe is allowed. As cheap insurance, phase 0 copies the user-visible storage
(`/sdcard`) to the Mac before any wipe (agent's call).

### Measurement loop

Each run:

1. Show full-white and full-black frames and capture both with the camera. They normalise for room
   light.
2. Find the four screen corners and warp the camera frame onto the screencap's pixel grid.
3. For each benchmark page: load it, wait for the panel to settle, capture the screencap and the
   camera frame.
4. Score three numbers:
   - **readability**: share of the screencap's OCR text that OCR also reads from the camera frame;
   - **element contrast**: grey-level separation between text or controls and their background, as
     the camera sees it;
   - **ghosting**: leftover difference after scrolling, against the same view loaded fresh.
5. Mask the glare region. Store the results per run, so runs can be compared.

**Benchmark set:** HN front page, an HN comment thread, the Omni front page, an Omni article, a Play
Books page, a Keep note, Settings home. Problems expected on HN: grey secondary text (`#828282`) and
the orange header bar. Problems expected on Omni: thin grey metadata, coloured labels, photos.

**Contrast fix locations to test:** a system-wide colour transform (SurfaceFlinger colour matrix)
with per-app profiles on top, and, for Chrome, page-level fixes (forced colours, a contrast
stylesheet). The loop keeps whichever scores higher.

## Agent's calls (made during design, owner can override)

- **Vendor-side changes are allowed.** Treble sepolicy blocks a system-side service from opening
  vendor device nodes. Onyx avoided that by building both sides. The builder may therefore change
  vendor sepolicy and init scripts, `boot`/`vendor_boot`, and `vbmeta` (verification is already off
  on the unlocked bootloader). A vendor-side shim HAL is an equal option. SELinux permissive is
  allowed during phases 1–2 experiments only. The delivered system runs enforcing. The phase 0
  backup covers every partition that may be rewritten.
- **Stock boot image source.** No root exists to dump `boot`, so the stock image comes from Onyx's
  OTA package for firmware `4.0.2` (`payload.bin`). If `fastboot boot` is refused, the patched boot
  image goes to the inactive slot `_a` (see anti-goals).
- **Play certification is not required.** The benchmark apps (Chrome, Play Books, Keep) work on an
  uncertified device after GSF-ID registration. Banking, Wallet and DRM content are out of scope.
  Widevine L3 is acceptable.
- **Updates.** The e-ink component ships as a separately flashable module, not baked into one GSI
  build. A GSI update is then a `system` reflash plus a scripted re-apply-and-verify step.

## Builder's calls

- The specific GSI build and Android version, as long as it is the newest that boots and passes
  phase 3 on this vendor.
- Tooling for reverse engineering, image processing and OCR.
- How the e-ink component is packaged: a privileged app in `system_ext`, a system service, or a
  Magisk-style overlay, provided the anti-goals hold.
- The scoring thresholds, once a baseline exists.

## Risks

- **Bricking.** Mitigation: phase 0 backup, A/B fallback, no `bootloader`/`xbl`/`abl` writes. A
  bootloader-level failure needs EDL or physical buttons. Recovering from that is the owner's one
  possible manual step.
- **The newest Android may not run on an Android 11 vendor.** Fallback: the newest version that does.
- **The panel may not update at all under a GSI** until phase 1's interface is in use. Screencap
  keeps the loop working meanwhile.
- **Kernel stays at Onyx's version.** A newer kernel is out of scope. The vendor kernel limits
  features such as some newer Android memory and security features.
