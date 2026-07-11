# WORKORDER — Shared-Drive migration (owner-quota → org-pooled quota)

> **Law (read first — these govern; this order is execution):**
> `memory/feedback-drive-canonical-storage.md` (the SA-has-no-quota finding + the owner-quota fix,
> deploy_815) and `case_work/MWK-ARTA-1212/DRIVE_LOCATION.md`. The corpus PDFs are Drive-canonical;
> the DB holds the text. **Do not delete any local PDF in this work order** — locals stay until a
> separate, human-approved decision. This order only re-homes the *Drive* copies.
>
> **Why now (binding):** the corpus lives in `jonzschoche@gmail.com`'s **personal** Drive (folder
> `1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP`), now **94% full (0.88 GiB free)**. The next ingested PDFs will
> `403 storageQuotaExceeded` again. A Workspace **Shared Drive** (org-pooled quota, and service accounts
> CAN write to it — Google's recommended pattern) is the durable home and reclaims the personal quota.
>
> **Stop and surface if any pre-flight fails. Fail-closed. Report; the desk edits ONTOLOGY.md.**

## Facts (grounded 2026-07-11)
- Files to migrate: **1,497** docs with `drive_file_id` (814 also still local — locals untouched here).
- Current parent (personal): folder `1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP`, owner `jonzschoche@gmail.com`.
- Mover credential: `DRIVE_REFRESH_TOKEN` (`jonzschoche@gmail.com`) — the file **owner**; only the owner
  can move its files into a Shared Drive. OAuth client in `gmail_oauth_client.json`.
- Service accounts: writes fall back to `287898704764-compute@developer.gserviceaccount.com`
  (`landtek-compute-sa.json`); reads use `leolandtek-docai@landtek.iam.gserviceaccount.com`
  (`google-creds.json`). **Both must be members of the new Shared Drive.**
- **No code currently sets `supportsAllDrives`** — Shared-Drive API calls will fail without it.

## The load-bearing assumption (verify on a canary before bulk)
**Moving a file into a Shared Drive preserves its file ID.** If true, every stored `drive_file_id`
stays valid → **no DB re-point needed**, and `/files/c/<id>` keeps serving. T1 proves this on ONE file
before touching the other 1,496. If a move ever changes an ID, STOP — the plan changes to re-point.

---

## PRE-FLIGHT (human/admin-gated — the SA cannot do this)
A Shared Drive can only be created by a Workspace user in `hayuma.org`. **Jonathan (or an OAuth token
for `jonathan@hayuma.org`) must:**
1. Create a Shared Drive (e.g. **"LANDTEK Corpus"**) in the `hayuma.org` Workspace.
2. Add as members: `287898704764-compute@developer.gserviceaccount.com` (**Content Manager**),
   `leolandtek-docai@landtek.iam.gserviceaccount.com` (**Content Manager** — it serves + reads),
   and `jonzschoche@gmail.com` (**Content Manager** — it must move its files in).
3. Create a `corpus/` folder inside it; record its folder id as `SHARED_DRIVE_FOLDER_ID` and the drive
   id as `SHARED_DRIVE_ID` in `.env`.

**Pre-flight gate:** the executor confirms all three members can be resolved and the folder id reads
back via API before any move. If not → surface and hold.

---

## T1 — CANARY move + ID-preservation proof
- Using the owner OAuth (`DRIVE_REFRESH_TOKEN`), move ONE low-stakes doc:
  `files.update(fileId, addParents=SHARED_DRIVE_FOLDER_ID, removeParents=1BMnZL…, supportsAllDrives=True)`.
- **Assert:** the file id is unchanged; `files.get(id, supportsAllDrives=True)` shows `driveId` set +
  size byte-identical to before; `/files/c/<id>` still serves that doc.
- **Assert:** `jonzschoche` quota `usage` dropped by ~that file's size (ownership moved to the org).
- If any assertion fails → STOP, surface, do not proceed to bulk.

## T2 — BULK move (1,496 remaining) — resumable, verified
- Iterate every `documents.drive_file_id` still parented under `1BMnZL…`; move each into
  `SHARED_DRIVE_FOLDER_ID` (owner OAuth, `supportsAllDrives=True`). **Idempotent:** skip any file whose
  parent is already the Shared Drive (so a re-run resumes — mirror `drive_offload.py`'s resumability).
- Per file: verify id-unchanged + `driveId` set. Log failures; never abort the batch on one failure.
- **Do NOT modify `documents.drive_file_id`** (ids are preserved). If T1 proved ids DO change, this task
  instead records the new id per doc — but only then.

## T3 — repoint the code to the Shared Drive (+ truth-floor)
- `leo_tools/server.py`:
  - `upload_to_drive`: default `folder_id` → `SHARED_DRIVE_FOLDER_ID`; add `supportsAllDrives=True` to
    `files.create`. Now the **SA path works** (SA is a Content Manager on the Shared Drive) — you MAY
    swap `_drive_service()` default back to the SA (reclaims autonomy + stops consuming personal quota
    for new uploads), keeping OAuth as fallback. Keep the loud-log discipline.
  - the serve path (`/files/c`) + any `files.get`/download: add `supportsAllDrives=True`.
- the reader (`google-creds.json` SA): any `files.list` gains `supportsAllDrives=True,
  includeItemsFromAllDrives=True` (and `corpora='drive', driveId=…` where it enumerates the corpus).
- **Truth-floor** — `truth_tests/test_shared_drive_migration.py` (deploy-gate + nightly), negative-tested:
  (a) grep-floor: no code path still hardcodes the personal folder `1BMnZL…`; (b) a fresh
  `upload_to_drive` lands a probe file **in the Shared Drive** (`driveId` set) then deletes it;
  (c) report-only: count of `documents` still parented in the personal folder — **the shrinking count is
  the graduation tracker** (0 = migration complete).

## T4 — supervision + reclaim close-out
- Run each of T1/T2/T3 as an **A59 `work_order`** reaching a terminal state (`supervisor.py`); a stalled
  task surfaces via `supervisor_sentinel.py`.
- Dated close-out block appended here per task. Final graduation line back to the desk: **reclaim proven**
  — `jonzschoche` quota `usage` dropped by ~the corpus size; free space restored; new uploads land in the
  Shared Drive under org quota.

---

## Guardrails (encode everything learned)
- **No local deletions.** This order never runs `drive_offload.py --go` (delete-local). Locals are the
  belt to the Drive suspenders until a separate human decision.
- **Canary before bulk.** The ID-preservation assumption is proven on one file before 1,496 are touched.
- **Byte-identity check** post-move (size match), like the geometry/consensus discipline.
- **Idempotent + resumable** — re-runs skip already-moved files (parent-is-Shared-Drive check).
- **Fail-closed** — any failed assertion halts + surfaces; the batch logs per-file failures without
  aborting siblings.
- **No phantom enforcement** — the executor reports counts; the ontology desk edits `ONTOLOGY.md`.
- **A62 gate-note discipline** — note the cost/credit posture; the migration itself is $0 (Drive API).
- **VPS staged-dup pull recipe** — if the session-start pull is blocked by a dirty VPS tree, use the
  lossless `reset --mixed origin/main` + gitignore-the-regenerable recipe from
  `memory/vps-stash-accumulation-and-drift.md`; never `--hard`.
- **Rollback** — every move is reversible: move a file back (`addParents=1BMnZL…,
  removeParents=SHARED_DRIVE_FOLDER_ID`). Ids preserved both ways, so the DB never diverges.
