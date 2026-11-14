# CI-built glue releases — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A glue release (display shim, module scripts, settings app) is built and published by GitHub Actions on the public repo from one "Run workflow" click with a version number. It needs no Mac and no proprietary file. The tablet installs that release like any other.

**Scope.** In:
- Stub link libraries generated from a checked-in symbol list (names and versions only, no Onyx code), so the shim builds without the device's libraries.
- Portable `device/epdcshim/build.sh` (`CLANG`, `LLD`, `SYSROOT` overrides; stubs when `sysroot/` is absent) and `device/einksettings/build.sh` (Linux build-tools, `EINK_KSPASS` from the environment).
- `.github/workflows/release.yml`: `workflow_dispatch` with input `version`. It decodes `EINK_KEYSTORE_B64`, builds both artifacts, runs `booxctl release glue --version V --publish`.

Out:
- Changing the signing key or password (same key, so updates keep working).
- System (class B) releases.

**Verification:**
- Locally: the stub-linked `libbooxepdc.so` has the same imported symbols (with versions) and the same `NEEDED` entries as the build against the real device libraries (`llvm-nm -D --undefined-only` + `llvm-readelf -d` diff empty).
- The CI gate stays green: `python3 scripts/check_context_budget.py && pytest -q tools`.
- On GitHub: the workflow run for `2026.11.14.7` succeeds and the release has the zip, the sidecar, and a manifest listing `EinkSettings.apk`.
- On the device: `booxctl update glue --tag glue-v2026.11.14.7` prints `post-check OK`. The CI-built APK installs as an update, which proves the signature matches.
- **Prerequisites:** secret `EINK_KEYSTORE_B64` set on `jonaseck2/boox-note5` (done 2026-11-14). The keystore is backed up in the owner's Drive (`My Drive/boox/`).

## Global Constraints

- Never commit device libraries, the keystore, the serial or personal paths (public repo).
- Stubs must not change the ABI the composer sees. The diff check above is the gate.

## Review Focus

1. **A new import in `epdcshim.c` without a stub entry.** Expected: the stub build fails at link time and names the missing symbol, rather than producing a `.so` that fails on the device.
2. **Versioned vs unversioned symbols.** Expected: `@LIBC` / `@LIBLOG` versions survive, because the bionic linker resolves them.

---

### Task 1: stub sysroot + portable shim build

- [ ] `device/epdcshim/stubs/symbols.txt` (lib, symbol, version) and `stubs/mkstubs.sh` → `build/stubs/*.so`.
- [ ] `build.sh`: compiler and linker overrides, `SYSROOT` defaulting to `sysroot/`, else the stubs.
- [ ] Diff check against the real-sysroot build, output pasted.
- [ ] Commit.

### Task 2: portable APK build + release workflow

- [ ] `einksettings/build.sh`: Linux build-tools zip (SHA-1 from `repository2-3.xml`), `EINK_KSPASS`.
- [ ] `.github/workflows/release.yml`.
- [ ] Commit, run the workflow for `2026.11.14.7`, check the release assets.

### Task 3: install the CI release on the tablet

- [ ] `booxctl update glue --tag glue-v2026.11.14.7` → post-check OK. Then close out.
