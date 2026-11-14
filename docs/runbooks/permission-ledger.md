# Permission ledger — granted, never re-ask

| Date | Item | Granted by | Notes |
|---|---|---|---|
| 2026-11-08 | Change the tablet in any way needed; ask only before a step that risks a brick with no recovery path | owner | design § Owner mandate |
| 2026-11-08 | Qualcomm EDL with community loader `poke6.bin`: read-only backup, then patched boot write | owner | runbook device-facts |
| 2026-11-08 | Write Magisk-patched boot to active `boot_b` | owner | slot `a` cannot boot |
| 2026-11-08 | macOS USB accessory approval for bootloader, fastbootd, EDL `9008` and crash-dump `900E` modes | owner (clicked Allow) | each new mode may prompt again; notify first |
| 2026-11-09 | Releases: private repository on owner's personal GitHub | owner | questions artifact |
| 2026-11-09 | Push `main` to `github.com/jonaseck2/boox` (private) | owner | push with `git -c credential.helper='!gh auth git-credential' push`; the gh token has `workflow` scope |
| 2026-11-09 | Test GSIs through DSU (no write to `super`) | agent's call, recorded on the artifact | stock stays one reboot away |
| 2026-11-08 | Claude Code allow rules for `~/boox-backups/tools/edlvenv` (install and run edl) | owner | `.claude/settings.local.json` |
