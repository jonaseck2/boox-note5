# Shipped

Log of completed plans, archived in this folder by the `close-out` skill. Kept as decision
records — what shipped, and the verification evidence that it worked. Newest first.

<!-- close-out appends: - YYYY-MM-DD [<feature>](<file>.md) — one-line outcome -->

- 2026-11-14 [`booxctl update glue` + first glue release](2026-11-14-booxctl-update-glue.md) — one-command verified glue updates from GitHub Releases (tamper-proofed, precheck, post-check). Releases 2026.11.14.1 and .2 published, the tablet runs .2
- 2026-11-14 [Phase 2: generic Android on the Note5](2026-11-09-phase2-gsi-via-dsu.md) — LineageOS 23.2 (Android 16, GApps) permanent via a rebuilt `super` (DSU impossible on this device). Panel driven by the composer EPDC shim: region updates, wf4, adaptive tone curve, panic guards, boot guard

- 2026-11-09 [Phase 0–1: backup and e-ink interface map](2026-11-08-phase0-1-backup-and-eink-interface.md) — full EDL backup (82 partitions, verified), Magisk root, full refresh via `panel_clean`, refresh modes via `/dev/ebc` ioctl; mode-switch camera proof deferred to phase 2
