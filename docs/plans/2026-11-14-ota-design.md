# Updates from GitHub Releases (USB and on-device) — design

Date: 2026-11-14. Parent design: [e-ink AOSP](2026-11-08-eink-aosp-design.md) (phase 6, "GitHub-release
updates"). Device facts: [device-facts.md](../runbooks/device-facts.md), [gsi-install.md](../runbooks/gsi-install.md),
[eink-interface.md](../runbooks/eink-interface.md), skill `boox-device`.

## Goal

The Note5 keeps receiving new versions of the e-ink glue and new LineageOS GSI builds after 2026-11-14.
Each version is published as a GitHub Release of the private repository `github.com/jonaseck2/boox`.
The owner installs a version from the Mac over USB with one command. Glue versions can also install on
the tablet itself, without the Mac, if the owner accepts one of the access options in § Decisions.

## Scope

In:

- Release artifact layout, versioning and integrity for two update classes:
  - **Class A (glue):** `libbooxepdc.so`, the `boox_epdc` Magisk module scripts, `eink-settings.sh`.
    Root and adb only. A failure costs at most one reboot cycle, after the boot guard below exists.
  - **Class B (system):** a new GSI in `system_b` inside `super`, and possibly a new `boot_b`.
    A failure can remove adb and leave EDL as the only way back.
- `booxctl update` design for the USB path from the Mac.
- The on-device path for class A.
- A feasibility verdict for an on-device class B update, with numbers.
- First runnable piece: `tools/booxctl/release.py` (`build_glue_bundle`) and `tools/tests/test_release.py`.

Out:

- Creating releases on GitHub, CI release workflows, and the `booxctl update` subcommand. Each is a
  later plan.
- Any device write. This spec changes nothing on the tablet.
- Bootloader-chain partitions (`xbl*`, `abl*`, `tz*` and the others in the skill). No update writes them.

## Verification

- Now: `.venv/bin/python -m pytest -q tools` passes. That is the
  same command as the CI gate's test step in `.github/workflows/gate.yml`. `test_release.py` covers the
  bundle's file list, manifest hashes, the `.sha256` sidecar, byte-reproducibility, script modes, version
  validation and a build from the real repo.
- Each later plan built on this spec drives the real artifact: `booxctl update glue` against the tablet,
  then checks the post-update state (§ USB path, step 6). Unit tests alone do not close those plans.

## Facts this design rests on

Measured for this spec on 2026-11-14 from local backups. No device was touched.

| Fact | Value | Source |
|---|---|---|
| `super` size | 4096 MiB | `lp.super_sectors` on `~/boox-backups/2026-11-08/edl/rl/lun0/super.bin` |
| `vendor_b` size | 493 MiB | `lp.extents_of(meta, "vendor_b")`, metadata slot 1 |
| LineageOS 23.2 GSI system image | 3,446,353,920 B (3287 MiB) | `~/boox-backups/gsi/lineage-23.2-20260524/` |
| Free space in `super` after the current GSI layout | about 315 MiB | 4096 − 493 − 3287, less metadata |
| `/data` encryption under the GSI (vendor fstab) | `fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized+wrappedkey_v0,metadata_encryption=aes-256-xts:wrappedkey_v0,keydirectory=/metadata/vold/metadata_encryption` | `vendor_b` in the super backup |
| Stock `recovery_b` | 96 MiB, `ro.build.type=user`, `ro.debuggable=0`, `ro.adb.secure=1`. Contains `adbd`, `minadbd`, `update_engine_sideload`, `toybox`. No keymaster, keystore or vold. | `recovery_b.bin` ramdisk, unpacked with `booxctl.bootimg` |
| GitHub release asset limit | 2 GiB per file | GitHub documentation |
| Magisk `updateJson` contract | `module.prop` line `updateJson=<url>`. The URL returns `{"version": str, "versionCode": int, "zipUrl": url, "changelog": url}`. The docs say nothing about authentication. | `topjohnwu/Magisk` `docs/guides.md` |

Facts from the runbooks that drive the risk model:

- Both slots are `slot-successful:yes`, and slot `a` has no logical partitions. A broken `system_b` never
  falls back to another slot.
- `adbd` comes from the system image, but `boot_b`'s overlay.d rc forces it on at `post-fs-data`, before
  `system_server`. A system that crashes in `system_server` still offers adb and `adb reboot edl`.
  A system that fails before second-stage init offers nothing, and recovery then needs the EDL cable.
- The composer loads the shim through `LD_PRELOAD`. The EPDC panics the kernel on some inputs (narrow
  planes, `waveform_mode=2`). A faulty shim can therefore crash every boot.

## Release artifact layout

Two tag families in `jonaseck2/boox`, so a glue release never implies a system change:

| Tag | Assets | Notes |
|---|---|---|
| `glue-v<version>` | `boox-glue-<version>.zip` and `.zip.sha256` (built by `release.build_glue_bundle`). Later: `boox_epdc-<version>.zip`, a Magisk-installable module, and `update.json`. | Small, about 10 KB today |
| `system-<gsi-build>-r<n>`, for example `system-los23.2-20260524-r1` | `system-manifest.json`, `boot_b.img` (Magisk + adb rc + `boox_composer`, 41.5 MB) and `.sha256` files | The GSI image itself is **not** re-hosted. 3.29 GiB exceeds the 2 GiB asset limit, and the upstream archive is already public. |

**Glue bundle** (implemented). Zip root:

```
eink-settings.sh            0755
libbooxepdc.so              0644
module/post-fs-data.sh      0755
module/service.sh           0755   (module/* is globbed, so new scripts ship without a code change)
manifest.json               0644
```

`manifest.json`, format 1:

```json
{"format": 1, "kind": "glue", "version": "2026.11.14.1",
 "files": {"libbooxepdc.so": {"sha256": "8689fb73…", "size": 16296}, "…": {}}}
```

The zip is byte-reproducible: entries in sorted order, timestamp 1980-01-01, fixed modes. The same tree
gives the same release hash on any machine, so a published asset can be checked against a local rebuild.

**System manifest** (designed, not built). It holds:

- `upstream_url`, plus the SHA-256 of the archive and of the extracted raw image.
- The SHA-256 of `boot_b.img` and of the expected `vbmeta_b`.
- `min_glue_version`.
- `data_compatible_with`: the GSI builds whose `/data` survives this update without a wipe. An Android
  major version change means a wipe.

**Versioning.**

- Glue `version` is `YYYY.MM.DD.N`.
- Magisk needs an integer `versionCode`. Use `YYYYMMDD × 100 + N`, for example `2026111401`. This stays
  below the int32 limit 2,147,483,647, with N ≤ 99 per day.
- `release.py` rejects any version outside `[0-9A-Za-z][0-9A-Za-z._-]{0,63}`, because the string becomes
  a filename and a `module.prop` value.

**Integrity.**

- The trust root is TLS plus the owner's GitHub account. Whoever controls that account can already
  change the code, so a signature adds no protection against the main threat.
- The SHA-256 values in the manifest and the sidecar detect corrupt or truncated downloads, and a staged
  file changed in shell-writable `/data/local/tmp`. `install.sh` already checks the latter.
- Signing is deferred. If a public mirror (Decision 1, option M) is ever writable by anything other than
  the owner, sign `manifest.json` with `ssh-keygen -Y sign` and verify it on the Mac before install.

## USB path: `booxctl update` (Mac)

Mac-side download uses `gh release download <tag> -R jonaseck2/boox`. `gh` is already authenticated with
the owner's token (permission ledger, 2026-11-09), so the private repository needs no new credentials.

### `booxctl update glue [--tag T | --bundle PATH]`

1. **Fetch and verify.** Download the bundle. Check the sidecar, then every manifest hash after extraction.
   Refuse on any mismatch.
2. **Precheck.** The way back must work in the post-write state:
   - adb answers, and `/debug_ramdisk/su -c id` returns uid 0.
   - `getprop init.svc.boox_composer` is `running`. That shows the boot image carries the service the
     module needs.
   - The boot guard (below) is installed. Refuse an unattended update without it.
3. **Keep the previous version.** Copy `/data/adb/modules/boox_epdc` to `/data/adb/boox_epdc.prev`.
4. **Install.** Stage the bundle files and run the existing `install.sh` logic. It verifies hashes, writes
   `.new` and then runs `mv` (never `cp` over the mapped `.so`), and sets the SELinux context.
   `module.prop` gets `version`/`versionCode` from the manifest instead of the hard-coded `v2`.
   Then run `eink-settings.sh`.
5. **Reboot.** The composer maps the `.so`, so a new shim takes effect only after a reboot.
6. **Post-check.** Within 3 minutes, check all of these:
   - adb is back and `sys.boot_completed=1`.
   - `boox_composer` is running and `module.prop` shows the new version.
   - `/sys/fs/pstore/dmesg-ramoops-*` shows no new panic.
   - `booxctl shot` shows the panel updating.

   On failure: restore `.prev`, then reboot.

**Boot guard (prerequisite, part of the first `update` plan).**

- `post-fs-data.sh` increments `/data/adb/boox_epdc.attempts`. `service.sh` clears the counter at
  `sys.boot_completed=1`.
- At the 3rd attempt, `post-fs-data.sh` restores `boox_epdc.prev`, or touches `disable` if no `.prev`
  exists.
- This works because Magisk runs `post-fs-data` scripts blocking, at `post-fs-data`. `class hal`, which
  starts `boox_composer`, starts later, at `on boot`.
- This guard replaces Magisk's own safe mode, which needs a volume key, and the Note5 has none.
- Open: whether the composer still starts when `LD_PRELOAD` names a missing file (a disabled module).
  Bionic usually warns and continues. Verify it on the device before relying on `disable` as the
  fallback. Until then, restoring `.prev` is the fallback.

**Way back for class A:**

- The guard restores the previous version on the next boot. `adb` itself does not depend on the module.
  It comes from `boot_b`'s rc.
- Worst case: a shim that panics the kernel within seconds of composer start, on every boot. The guard
  fires on attempt 3. If the guard itself is broken, the way back is `adb reboot edl` in the short window
  before composer start, or the EDL cable followed by `recover-edl.sh adb`.

### `booxctl update system --tag T`

This is the proven EDL route from `gsi-install.md`, wrapped. It is brick-risk class, so every run is a
Tier 3 step: the owner confirms and is available for the cable.

1. Download `system-manifest.json` and `boot_b.img` from the release, and the GSI from `upstream_url`.
   Verify all three hashes.
2. Build `super` with `lp.build_super(<EDL backup super.bin>, <system.img>, out)`. `vendor_b` stays
   byte-identical, and metadata slot 1 is rewritten. Keep the image of the currently running super in
   `~/boox-backups/gsi/<build>/` as the rollback image.
3. **Precheck** (recovery rule):
   - The current boot forces adb (two-boot test already passed for `boot_b.magisk.epdc.img`).
   - `booxctl backup verify` passes.
   - The rollback super image exists and its hash is recorded.
   - The owner has the EDL cable in reach, and macOS accessories are set to "Always".
4. `adb reboot edl`, then EDL `w super`. Add `w boot_b` only if the manifest's boot hash differs from the
   installed one. Add `e metadata` and `e userdata` only if the running build is not in
   `data_compatible_with`. Read back and hash, then `reset`.
5. Post-check as in the glue path. The `boox_epdc` module and settings live on `/data`, so they survive
   a no-wipe update. After a wipe, run `update glue`.

**Way back for class B:** EDL write of the rollback super image.

- Reachable by `adb reboot edl` if the new system brings up adbd, which is true for every failure seen
  so far after `system_server` started.
- Otherwise reachable only with the EDL cable and the owner.

## On-device path, class A

Mechanism: ship the glue as a Magisk-installable module and point `module.prop`'s `updateJson` at a
release asset:

- Zip layout: `module.prop`, `post-fs-data.sh`, `service.sh` and `system/vendor/lib64/libbooxepdc.so`.
  `META-INF/com/google/android/update-binary` is Magisk's `module_installer.sh`, and `updater-script`
  contains `#MAGISK`.
- `customize.sh` sets the `vendor_file` SELinux context and seeds `persist.boox.epdc.*`, which is
  `install.sh`'s job today.
- The device-side half of `eink-settings.sh` moves into `service.sh` at `boot_completed`. It is
  idempotent. The Mac script stays for USB use.
- `update.json` lives at a stable URL. `https://github.com/<repo>/releases/latest/download/update.json`
  always resolves to the newest release.

Two installers can consume it:

1. **Magisk app** (`com.topjohnwu.magisk`). The app shows "Update" when `versionCode` is higher and
   installs `zipUrl`. It sends a plain GET with no credentials. Whether its HTTP client follows GitHub's
   redirect to `objects.githubusercontent.com` is not stated in the Magisk docs. Verify it once on the
   device. The app may not be installed after the factory reset. Root works without it, through
   `/debug_ramdisk/su`.
2. **Own updater loop in `service.sh`.** It checks once a day on Wi-Fi: fetch `update.json`, download,
   verify the manifest hashes, then `magisk --install-module <zip>` (headless Magisk CLI), and post a
   notification "glue <v> installed, reboot to apply". It uses Magisk's busybox `wget`.
   Open: whether that busybox build supports HTTPS. Check `/data/adb/magisk/busybox wget --help` and one
   real fetch before building on it. This installer can send an `Authorization` header, which is what
   Decision 1, option T needs.

The boot guard applies unchanged, and it is required before any unattended on-device install.

**Private-repository blocker.** A release asset of a private repository returns 404 without a token.
The Magisk app cannot send one. See Decision 1.

## On-device path, class B: verdict

**Not feasible on this device with the current facts.** It remains USB-driven (EDL today). Three
independent blockers, each with its number:

1. **No room for a second system.** Real A/B (write the inactive `system_a`, switch slots, and let the
   bootloader fall back on failure) needs two system partitions plus `vendor` in `super`:
   2 × 3287 + 493 = 7067 MiB, and `super` is 4096 MiB. Sharing one `vendor` extent between `vendor_a`
   and `vendor_b` saves 493 MiB and still does not fit. Two systems fit only below about 1800 MiB each,
   and the current GSI is 3287 MiB.
2. **No staging place outside the running Android.** An update environment that writes `system_b` while
   it is unmounted (recovery, or a custom ramdisk in `boot_a`) must read the new image from somewhere:
   - `/data` uses metadata encryption with hardware-wrapped keys (`wrappedkey_v0`). Stock recovery has
     no keymaster or vold, so it reads ciphertext.
   - An uncrypt-style block map fails for the same reason.
   - Free space in `super` is about 315 MiB, and `recovery_a` is 96 MiB.
3. **Live overwrite is unsafe.** Writing `system_b` from root while it is mounted replaces the pages that
   `init` (second stage, `/system/bin/init`) and every running process fault back in. A crash part-way
   leaves a half-written system, with no adbd (it lives in the system image) and no slot fallback.
   The only way back is then the EDL cable.

What would change the verdict:

- **Virtual A/B through `update_engine`.** COW snapshots on `/data`, merged after a successful boot,
  with rollback if boot fails. Stock used it (`system_b-cow` existed), so the 4.19 kernel has
  dm-snapshot. DSU's first-stage log reached `DSU slot: dsu`, weak evidence that first-stage init maps
  images on encrypted `/data`. This route needs all of the following:
  - a payload generated with AOSP host tools (`delta_generator`, Linux only)
  - a payload key that the GSI's `update_engine` accepts
  - `boot_a`, `vbmeta_a` and super metadata slot 0 prepared for slot `a`
  - a deliberate test showing that ABL falls back to `b` after slot `a` fails to boot. That test needs
    the EDL cable at hand.

  It is a research project of several sessions, not a design step. Listed under Later.
- **An EROFS GSI below about 1800 MiB.** This depends on EROFS support in the Onyx 4.19 kernel. Mainline
  EROFS left staging only in 5.4, so the support is unverified.

## Optional class B improvement: rooted `recovery_b` as the USB update environment

This option replaces EDL for routine system updates. It still needs the Mac.

- Build: edit the stock `recovery_b` ramdisk with `booxctl.bootimg`. In `prop.default`, set
  `ro.debuggable=1`, `ro.adb.secure=0` and `persist.sys.usb.config=adb`. Add `/adb_keys` with the Mac's
  key. `recovery_b` is never used in a normal boot, and its stock image is in the EDL backup.
- Update: `adb reboot recovery`, then stream the rebuilt super from the Mac (`adb shell dd of=… bs=4M`
  through stdin, never staged), then read back the hash and `reboot`. `system_b` is not mounted in
  recovery, so blocker 3 does not apply.
- Interrupted writes: write `boot-recovery` into the `misc` BCB before writing `super`, and clear it after
  the hash check. A power loss part-way re-enters recovery instead of the half-written system.
- Way back: recovery does not depend on `super`, so an interrupted or wrong write can be redone over adb.
  A complete write of a system that fails before adbd starts still needs EDL, the same as today.
- Prechecks the plan must prove first:
  - Recovery's `adbd` gives a root shell with the edited props.
  - A 15 s power hold from a hung recovery returns to normal boot (Qualcomm reboot reason, not BCB).
    Test it with the stock recovery before writing a modified one.
- Gain over the current route: no community firehose loader, and no EDL accessory mode. Interrupted
  writes become retryable. Cost: one more boot image to maintain. EDL via `adb reboot edl` already avoids
  the cable, so this is optional.

## Rejected options

| Option | Rationale for rejection | What would reverse it |
|---|---|---|
| Re-host the GSI image as a release asset | 3.29 GiB > 2 GiB per-asset limit. The upstream archive is public and pinned by hash. | Upstream link rot. Then split the image, or host the 1.17 GB `.7z`. |
| Make `jonaseck2/boox` public | The owner chose a private repository (ledger, 2026-11-09). The repo also references Onyx firmware analysis. | Owner decision |
| Unguessable URL (secret gist, random path) for `update.json` | Gives the same exposure as public once the URL leaks, without saying so | — |
| Live `dd` of `system_b` from root | Blocker 3 above. A crash part-way removes adb and leaves only the EDL cable. | — |
| A/B in `super` with a shared `vendor` extent | Blocker 1: 2 × 3287 + 493 > 4096 MiB, and 2 × 3287 > 4096 MiB even without `vendor` | A system image ≤ ~1800 MiB |
| Recovery reads a staged image from `/data` | Blocker 2: `wrappedkey_v0` metadata encryption, and no keymaster in recovery | A recovery with a working keymaster HAL (none exists for the Note5) |
| DSU as an update channel | First-stage init panics on the missing `vbmeta_b`/`boot_b` links in DSU mode (gsi-install.md) | — |
| fastboot / fastbootd flashing | `flash`, `boot` and `erase` are removed in both (device-facts.md) | — |
| Signing release manifests in v1 | The account that signs is the account that hosts. A signature adds a key to manage and no protection. | A second writer, or a mirror not controlled by the owner |
| Magisk app as the only on-device installer | It cannot authenticate, may not be installed, and has no hash check beyond the download | Decision 1 = M, with the app present |

## Decisions for the owner

1. **On-device access to glue releases (private repository).** Pick one:
   - **M — public mirror repository**, for example `jonaseck2/boox-glue`, holding only the glue release
     assets: the shim binary, module scripts and `update.json`. No Onyx files, no keys, no boot images.
     The Magisk app and the own updater both work with no token on the device.
     **Agent's recommendation.** The glue contains no secret, and the main repository stays private.
     A release step copies the assets.
   - **T — read-only token on the device.** A fine-grained PAT, `contents:read` on `jonaseck2/boox`
     only, stored root-only in `/data/adb/`. Only the own updater can use it, through the GitHub API
     asset URL with `Accept: application/octet-stream`. The PAT expires after at most 1 year. A
     factory reset deletes it. A stolen tablet exposes read access to the private repository.
   - **U — USB only.** No on-device updates. Zero new exposure, and the owner needs the Mac for every
     update.
2. **System updates over EDL only, or also build the rooted `recovery_b`?** The agent's call is EDL only
   for now, and the recovery work only if system updates become frequent.
3. **Accept that a system update on the device itself is not offered**, or fund the Virtual A/B research
   (Later). The agent recommends accepting.
4. **Version scheme** `YYYY.MM.DD.N` with `versionCode = YYYYMMDD × 100 + N`. Override if you prefer
   semantic versions.

### Owner answers (2026-11-14, decision page)

1. **M: public mirror.** The owner asked whether "fully public" means excluding Google files. Yes: the glue release holds only our own shim, scripts and settings app. It redistributes no Google or Onyx files. At runtime the shim calls Onyx's composer on the device, so the composer itself is not ours to publish.
2. **EDL over USB only.** No recovery work.
3. **No on-device system updates.** The owner asked what the Virtual A/B research would cost (see the estimate below).
4. **Version scheme agreed:** `YYYY.MM.DD.N`.
5. Related: the whole repo goes open source as a fresh public repo under Apache-2.0, with personal data scrubbed. The mirror can therefore be that public repo's releases.

Estimate for on-device system updates (Virtual A/B), for the owner's question: `super` has about 315 MiB free and the system needs 3287 MiB. A second copy needs snapshot/COW space on `/data` (Virtual A/B compression) plus an `update_engine` and snapuserd that work with this vendor (Android 11) and a 4.19 kernel. Expect several multi-day sessions of reverse engineering and test flashing, each write with EDL cable recovery on standby. The probability of success is uncertain, because GSIs rarely support Virtual A/B on old vendors.

## Build order (later plans)

1. `update glue` over USB, plus the boot guard and `module.prop` versioning in `install.sh`.
   First real release `glue-v<date>.1` (Tier 3: publishing).
2. Magisk-installable module zip and `update.json` in the release. On-device updater per Decision 1.
3. `update system` wrapping the EDL route, with `system-manifest.json`.
4. Optional: rooted `recovery_b` (Decision 2).
