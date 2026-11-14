# `booxctl update glue` and the first glue release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** The owner updates the tablet's e-ink glue (display shim, Magisk module scripts, e-ink settings) from a GitHub Release of the public repo with one command on the Mac. A failed update returns to the previous version without the EDL cable. Release `2026.11.14.1` is published.

**Scope.** In:
- `booxctl release glue --version V [--publish]`: build the bundle (`release.build_glue_bundle`). `--publish` creates the GitHub Release `glue-vV` on `jonaseck2/boox-note5` with the zip and its `.sha256`.
- `booxctl update glue (--tag T | --bundle PATH)`: fetch, verify the sidecar and every manifest hash, precheck, install through `device/epdcshim/install.sh` with the bundle as source, run `eink-settings.sh`, reboot, post-check.
- `install.sh` takes `SRC` (source dir) and `VERSION` (written to `module.prop` with `versionCode = YYYYMMDD×100+N`).

Out:
- The on-device updater and Magisk `updateJson` (a later plan).
- System (class B) updates.
- Signing (deferred by the design).

**Verification:**
- `.venv/bin/python scripts/check_context_budget.py && .venv/bin/python -m pytest -q tools` exits 0 (the CI gate).
- On the device: `booxctl update glue --tag glue-v2026.11.14.1` prints `post-check OK`. Then `module.prop` shows `version=2026.11.14.1` and `versionCode=2026111401`, `boox_composer` is running, the composer maps `libbooxepdc.so`, and the camera shot shows the panel drawing.
- Tamper test: a bundle with one changed byte is refused before anything is written to the device.
- **Prerequisites:** the boot guard is installed (done 2026-11-14, `docs/runbooks/eink-interface.md`). `gh` is authenticated as `jonaseck2` with permission to create releases on `jonaseck2/boox-note5`. The tablet serial is in `~/.config/boox/serial`.

**Spec:** [2026-11-14-ota-design.md](2026-11-14-ota-design.md).

## Global Constraints

- Version strings: `YYYY.MM.DD.N`, `versionCode = YYYYMMDD×100 + N` (owner decision, 2026-11-14).
- Never `cp` over the live `.so` (the composer maps it): `install.sh`'s rename path only.
- Ruling: the boot guard restores `libbooxepdc.so.prev` (as built), not a `boox_epdc.prev` module copy (as designed). It covers the shim, the only part that can panic the kernel.

## Review Focus

1. **Tampered or truncated bundle.** Expected: refused before any device write. The error names the file.
2. **The tablet is missing the boot guard or the `boox_composer` service.** Expected: precheck refuses and names the missing piece.
3. **The post-check fails (no adb within 3 min, composer down, new pstore panic).** Expected: the command reports failure and the way back (the guard restores `.prev` within 3 boots; EDL as the last resort). It does not claim success.

---

### Task 1: version code, bundle verification, release command

**Files:** `tools/booxctl/release.py`, `tools/tests/test_release.py`, `tools/booxctl/__main__.py`.

**Interfaces:** Produces:
- `version_code(version: str) -> int`
- `verify_bundle(zip_path: Path, out_dir: Path) -> dict`: returns the manifest, raises `ValueError` naming the bad file.
- CLI `release glue --version V [--publish]`.

- [x] Failing tests: `test_version_code` (`2026.11.14.1` → `2026111401`, invalid → `ValueError`), `test_verify_bundle_ok`, `test_verify_bundle_rejects_tampered_file`, `test_verify_bundle_rejects_bad_sidecar`.
- [x] Implement. Run the full suite.
- [x] Commit.

### Task 2: `update glue` with precheck, install, post-check

**Files:** `tools/booxctl/update.py`, `tools/tests/test_update.py`, `device/epdcshim/install.sh`, `tools/booxctl/__main__.py`.

**Interfaces:** Consumes `verify_bundle`, `version_code`. Produces `precheck(dev) -> list[str]` (empty = OK, else the problems) and `update_glue(dev, bundle, repo_root) -> bool`.

- [x] Failing tests: `test_precheck_reports_missing_guard`, `test_precheck_reports_composer_not_running`, `test_precheck_ok`.
- [x] Implement. `install.sh`: `SRC`, `VERSION`. Run the full suite.
- [x] Commit.

### Task 3: publish 2026.11.14.1 and update the tablet from it

- [x] `booxctl release glue --version 2026.11.14.1 --publish`. Confirm the release assets.
- [x] Tamper test against the downloaded bundle.
- [x] `booxctl update glue --tag glue-v2026.11.14.1`. Paste the post-check and camera evidence.
- [x] Close out.

---

## Outcome (closed 2026-11-14)

Rulings:
- `install.sh` saves `.prev` only when the shim differs. An update to the same shim keeps the older `.prev` as the fallback.
- The first update run's post-check flagged a false panic (console/pmsg ramoops rotate on every boot). The fix counts only new `dmesg-ramoops-*` records (`test_normal_reboot_is_not_a_panic`, `test_new_dmesg_record_is_a_panic`, both seen RED).
- That run exposed a shim bug (stale mapping after re-presented buffers). It was fixed and shipped as release 2026.11.14.2 through this tool.

Evidence:

```
$ python3 scripts/check_context_budget.py        -> OK: 5438 <= 6000
$ pytest -q tools                                -> 75 passed (CI: green on jonaseck2/boox-note5)
releases: github.com/jonaseck2/boox-note5/releases/tag/glue-v2026.11.14.1 and glue-v2026.11.14.2
tamper test (service.sh changed, matching sidecar) -> "ValueError: hash mismatch: module/service.sh", device md5 unchanged
$ booxctl update glue --tag glue-v2026.11.14.2
bundle boox-glue-2026.11.14.2.zip: version 2026.11.14.2, 4 files verified
precheck OK
installed; rebooting
post-check OK: glue 2026.11.14.2 running
module.prop: version=2026.11.14.2 versionCode=2026111402; lib64: libbooxepdc.so + libbooxepdc.so.prev
camera: Settings drawn correctly after the update boot
```
