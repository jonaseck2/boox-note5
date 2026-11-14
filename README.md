# Boox Note5 on current Android

This project moves an Onyx Boox Note5 e-ink tablet (Qualcomm SDM662 "bengal", Android 11 stock, end of
support) to current Android with Google apps, tuned for its greyscale e-ink panel. A Mac drives the
whole loop over adb and Qualcomm EDL. A camera facing the panel scores what a person actually sees.

## Status (2026-11-14)

- LineageOS 23.2 (Android 16, Google apps) runs as the permanent system on a rebuilt `super`. Root is
  through Magisk, and adb is forced on by the boot image.
- The e-ink panel is driven by `device/epdcshim`: an `LD_PRELOAD` shim in Onyx's vendor composer.
  - It calls the composer's own EPDC update path.
  - Only changed regions are updated. The default is waveform 4 (camera-measured least flash), with
    an idle clean after 30 updates.
  - A content-adaptive tone curve applies a strong curve to text and UI and a gentle one to photos.
  - Two guards prevent kernel panics: commits must carry one full-size framebuffer, and the composer
    is limited to one blend stage.
  - A boot guard restores the previous shim after 3 unhealthy boots.
- Settings → Display → **E-ink** (`device/einksettings`) sets contrast, waveform and the ghosting
  clean, and triggers a full refresh.
- The brightness slider drives the front light.
- Updates: `booxctl update glue --tag glue-v<version>` installs a verified glue release from this repo's
  GitHub Releases, then reboots and runs a post-check. System updates go over USB/EDL
  ([design](docs/plans/2026-11-14-ota-design.md)).

Details: [`docs/runbooks/eink-interface.md`](docs/runbooks/eink-interface.md),
[`docs/runbooks/gsi-install.md`](docs/runbooks/gsi-install.md). Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md).

⚠️ This modifies partitions over Qualcomm EDL. Take the full EDL backup first (`booxctl backup`), and read
the recovery rules in `.claude/skills/boox-device/SKILL.md` before writing anything.

## Setup

Your tablet's adb serial (from `adb devices`) goes in `~/.config/boox/serial` or `$BOOX_SERIAL`. Every
command pins it, because other adb devices may be connected.

```bash
mkdir -p ~/.config/boox && echo <your-serial> > ~/.config/boox/serial
python3 -m venv .venv && .venv/bin/pip install -r tools/requirements-dev.txt
.venv/bin/python scripts/check_context_budget.py && .venv/bin/python -m pytest -q tools
```

## Layout

| Path | Content |
|---|---|
| `tools/booxctl/` | Python CLI: device control, camera, backup, e-ink control, flicker meter, tap by text (`python3 -m booxctl --help` from `tools/`) |
| `device/epdcshim/` | Composer shim (C), its build and install scripts, and the Magisk module scripts |
| `device/einksettings/` | The E-ink entry in Android Settings (Java, no Gradle) |
| `device/eink-settings.sh` | Android settings for e-ink (theme, animations, bold text, wallpaper) |
| `device/ebcctl/` | 277-byte AArch64 tool that sets the e-ink refresh mode (`/dev/ebc` ioctl `0x700b`) |
| `device/boox-adb.rc.template` | Boot-image init script: forces adb and starts the shimmed composer |
| `docs/runbooks/` | Device facts, the e-ink interface map, the GSI install |

Backups and Onyx's proprietary files stay outside the repository, in `~/boox-backups`. The repository
redistributes no Onyx or Google files.

The workflow (brainstorm → plan → close-out) comes from the Claude Code project template. See `CLAUDE.md`.

## License and notice

Apache License 2.0, see [`LICENSE`](LICENSE). Not affiliated with or endorsed by Onyx International.
"Boox" is Onyx's trademark. The runbooks document interfaces of Onyx's software, found through
reverse engineering for interoperability.
