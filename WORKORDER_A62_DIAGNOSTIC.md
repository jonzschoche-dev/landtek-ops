# Diagnostic — where do LandTek's bytes actually live, and what's in B2?

**For:** executor agent (VPS Claude) or operator, on the VPS. Read-only diagnostic — change nothing.
**Why:** A62 (record survives the machine) depends on BOTH the database AND the client file
binaries being off-box. The B2 cap (account fc40d7f66583, rclone 403 storage_cap_exceeded)
is the known red. But before raising it, confirm what B2 actually holds and whether the
ingested binaries are off-box at all. This is ground truth, not inference.

## T1 — Where do ingested documents physically live?
```sql
-- the storage roots documents point at (file_path prefix tells us local vs Drive vs B2)
SELECT split_part(file_path,'/',1) AS root, count(*) AS n
FROM documents GROUP BY 1 ORDER BY n DESC;
-- sample a few real paths
SELECT id, ingest_source, file_path FROM documents
WHERE ingest_source LIKE 'comms_%' ORDER BY id DESC LIMIT 5;
```
Report: are comms_/client binaries on LOCAL VPS disk (`/root/...`, `/var/...`), Google Drive
(`driveId`/shared-drive paths), or B2? This determines whether a VPS death loses the bytes.

## T2 — What does the backup pipeline actually dump?
```bash
grep -rnE "pg_dump|rclone|RESTORE_DRILL|--b2|--remote|DUMP_DIR" \
  scripts/ migrations/ infra/ 2>/dev/null | grep -iE "dump|rclone|b2|backup" | head -20
cat /root/backups/RESTORE_DRILL.log 2>/dev/null | tail -15
```
Report: does the backup dump Postgres only, or does it also copy the binary store (file_path dir)?
If binaries are local and NOT in the dump → B2 holds only the DB, not the client files.

## T3 — What's in the B2 bucket right now?
```bash
# the rclone remote name (from the backup script / .env)
grep -iE "B2|rclone|remote" /root/landtek/.env 2>/dev/null | sed 's/=.*/=<redacted>/'
# list bucket contents + size (needs B2 creds present)
rclone lsd <remote>: 2>&1 | head
rclone size <remote>: 2>&1 | tail -5
```
Report: bucket name, total stored GB, top-level layout (is it just `landtek_dump.sql` + dated
dumps, or does it also hold a `documents/` tree?). This shows what's filling the cap.

## T4 — Is the DB dump itself off-box AND current?
```bash
# last successful rclone push vs last local dump
ls -la /root/backups/*.sql 2>/dev/null | tail -3
rclone lsl <remote>: 2>&1 | tail -5
```
Report: does a current dump exist in B2, or has the 403 been blocking pushes (so B2 is stale)?

## T5 — Honest A62 verdict
Synthesize:
- DB off-box? (B2 green-or-red)
- Binaries off-box? (Drive yes / local no / B2 no)
- Does "record survives the machine" ACTUALLY hold today, or only after (a) cap raised AND
  (b) binaries confirmed off-box?
State the remaining hole plainly. If binaries are local-only, name the fix: route file_path to
the Shared Drive (deploy_846 migration) so bytes are off-box, OR add binaries to the B2 dump.

## Guardrails
Read-only (SELECTs + rclone ls/size, no copy/delete). Redact credentials in any output.
Report facts, not reassurance — A62 is the one standing red; this diagnostic exists to show
whether raising the cap actually closes it or only half-closes it.

## Invocation
> Run the A62 storage diagnostic (T1–T5). Where do documents physically live (local vs Drive vs
> B2)? What does the backup dump (DB only or bytes too)? What's in the B2 bucket and is it current?
> Give the honest A62 verdict: does raising the cap on fc40d7f66583 actually make the record
> survive the machine, or are the client binaries still local-only? Redact creds.
