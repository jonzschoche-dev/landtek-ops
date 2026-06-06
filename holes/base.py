"""holes/base.py — base `Routine` class.

Every gap-finding routine subclasses `Routine`, sets class attributes
(name, version, hole_type, cadence, severity_default), and implements
`find_holes(cur)`. Inside that method, call `self.emit(...)` for each
hole discovered.

The base class handles:
- Postgres connection / cursor
- Findings persistence with idempotency (finding_id_hash partial unique index)
- Run logging (holes_runs)
- Optional auto-remediation if `fix_sql` or `fix_command` is set on a finding
- Heartbeat emission to system_heartbeat

Pattern:
    class A2_SelfResearch(Routine):
        name = "A2_self_research"
        version = "v1"
        hole_type = "truth_gap"
        cadence = "every_6h"
        severity_default = "P2"

        def find_holes(self, cur):
            cur.execute("SELECT ...")
            for row in cur.fetchall():
                self.emit(
                    severity="P2",
                    description=f"Leo answered '{row['claim']}' as unsourced...",
                    case_file=row["case_file"],
                    metadata={"original_negotiation_id": row["id"]},
                )

CLI: every routine module gets a `if __name__ == '__main__': run_cli(MyRoutine)`.
"""
import abc
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
LANDTEK_ROOT = "/root/landtek"

VALID_SEVERITIES = ("P0", "P1", "P2", "P3", "info")
VALID_HOLE_TYPES = (
    "truth_gap", "evidence_gap", "coverage_gap", "discipline_drift",
    "schema_drift", "capacity_gap", "coordination_gap", "memory_drift",
)
VALID_CADENCES = ("every_4h", "every_6h", "daily", "weekly", "session_boundary", "on_demand")
# kind: "python" routines run inline in the dispatcher; "cc_session" routines are
# orchestrated by their own systemd timer that runs `claude -p < holes/prompts/<name>.md`.
# The dispatcher SKIPS cc_session routines but lists them so we have a unified registry view.
VALID_KINDS = ("python", "cc_session")


def load_env(path: str = f"{LANDTEK_ROOT}/.env") -> dict:
    """Load .env into os.environ AND return as dict. Idempotent."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip("'").strip('"')
            out[k] = v
            if k not in os.environ:
                os.environ[k] = v
    return out


class Routine(abc.ABC):
    """Subclass me. Set class attributes. Implement `find_holes(cur)`. Call `self.emit(...)`."""

    name: str = None                 # required: 'A2_self_research'
    version: str = "v1"
    hole_type: str = None            # required: one of VALID_HOLE_TYPES
    cadence: str = "on_demand"       # one of VALID_CADENCES
    kind: str = "python"             # "python" or "cc_session"; cc_session routines are skipped by dispatcher
    cc_prompt_path: str = None       # for kind='cc_session': path under holes/prompts/
    severity_default: str = "P2"
    description: str = ""            # human-readable purpose (for digest header)

    def __init__(self, dsn: str = DSN):
        if not self.name:
            raise ValueError(f"{type(self).__name__}: must set class attribute `name`")
        if self.hole_type not in VALID_HOLE_TYPES:
            raise ValueError(f"{self.name}: hole_type must be one of {VALID_HOLE_TYPES}")
        if self.cadence not in VALID_CADENCES:
            raise ValueError(f"{self.name}: cadence must be one of {VALID_CADENCES}")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"{self.name}: kind must be one of {VALID_KINDS}")
        self.dsn = dsn
        self._findings: list[dict] = []

    # ─────────────────────────── findings API ────────────────────────────

    def finding_hash(self, **parts) -> str:
        """Stable hash for idempotency. Pass the fields that DEFINE this hole."""
        parts["_routine"] = self.name
        s = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

    def emit(
        self,
        severity: Optional[str] = None,
        description: str = "",
        case_file: Optional[str] = None,
        matter_code: Optional[str] = None,
        doc_id: Optional[int] = None,
        suggested_fix: Optional[str] = None,
        fix_sql: Optional[str] = None,
        fix_command: Optional[str] = None,
        auto_remediable: bool = False,
        metadata: Optional[dict] = None,
        hash_parts: Optional[dict] = None,
    ):
        """Queue a finding. Persisted at end of run()."""
        sev = severity or self.severity_default
        if sev not in VALID_SEVERITIES:
            raise ValueError(f"severity {sev!r} not in {VALID_SEVERITIES}")
        if hash_parts is None:
            hash_parts = {
                "description": description,
                "case_file": case_file,
                "matter_code": matter_code,
                "doc_id": doc_id,
            }
        fh = self.finding_hash(**hash_parts)
        self._findings.append({
            "finding_id_hash": fh,
            "severity": sev,
            "description": description,
            "case_file": case_file,
            "matter_code": matter_code,
            "doc_id": doc_id,
            "suggested_fix": suggested_fix,
            "fix_sql": fix_sql,
            "fix_command": fix_command,
            "auto_remediable": bool(auto_remediable),
            "metadata": metadata or {},
        })

    # ─────────────────────────── lifecycle ────────────────────────────

    @abc.abstractmethod
    def find_holes(self, cur):
        """Subclasses implement. Call self.emit(...) for each hole."""

    def run(self, auto_remediate: bool = False, dry_run: bool = False) -> dict:
        load_env()
        t0 = time.time()
        conn = psycopg2.connect(self.dsn); conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        run_status = "ok"
        error_message = None
        try:
            self.find_holes(cur)
        except Exception as e:
            run_status = "failed"
            error_message = f"{type(e).__name__}: {e}"[:500]

        persisted = 0
        p0 = 0
        remediated = 0
        if not dry_run:
            for f in self._findings:
                # Skip if an open finding with this hash already exists (idempotent).
                cur.execute(
                    "SELECT id FROM holes_findings WHERE finding_id_hash=%s AND status='open' LIMIT 1",
                    (f["finding_id_hash"],),
                )
                if cur.fetchone():
                    continue
                cur.execute("""
                    INSERT INTO holes_findings (
                        routine_name, routine_version, finding_id_hash,
                        severity, hole_type, case_file, matter_code, doc_id,
                        description, suggested_fix, fix_sql, fix_command,
                        auto_remediable, metadata
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s::jsonb
                    )
                """, (
                    self.name, self.version, f["finding_id_hash"],
                    f["severity"], self.hole_type, f["case_file"], f["matter_code"], f["doc_id"],
                    f["description"], f["suggested_fix"], f["fix_sql"], f["fix_command"],
                    f["auto_remediable"], json.dumps(f["metadata"]),
                ))
                persisted += 1
                if f["severity"] == "P0":
                    p0 += 1

                # Auto-remediate if asked and the finding declares it
                if auto_remediate and f["auto_remediable"] and (f["fix_sql"] or f["fix_command"]):
                    if self._try_remediate(cur, f):
                        remediated += 1

        duration_ms = int((time.time() - t0) * 1000)

        if not dry_run:
            cur.execute("""
                INSERT INTO holes_runs (
                    routine_name, routine_version, status, duration_ms,
                    findings_count, p0_count, metadata, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """, (
                self.name, self.version, run_status, duration_ms,
                persisted, p0,
                json.dumps({"auto_remediate": auto_remediate, "remediated": remediated,
                            "emitted_total": len(self._findings)}),
                error_message,
            ))
            # Also write to system_heartbeat so the existing meta-agent sees us
            try:
                cur.execute("""
                    INSERT INTO system_heartbeat (source, status, duration_ms, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                """, (
                    f"holes:{self.name}",
                    run_status,
                    duration_ms,
                    json.dumps({"findings": persisted, "p0": p0, "remediated": remediated}),
                ))
            except Exception:
                pass  # system_heartbeat is optional; don't fail the run

        cur.close(); conn.close()
        return {
            "routine": self.name,
            "status": run_status,
            "findings_persisted": persisted,
            "findings_emitted_total": len(self._findings),
            "p0_count": p0,
            "remediated": remediated,
            "duration_ms": duration_ms,
            "error": error_message,
            "dry_run": dry_run,
        }

    def _try_remediate(self, cur, finding: dict) -> bool:
        try:
            if finding.get("fix_sql"):
                cur.execute(finding["fix_sql"])
            elif finding.get("fix_command"):
                import subprocess
                r = subprocess.run(finding["fix_command"], shell=True, capture_output=True,
                                   text=True, timeout=120)
                if r.returncode != 0:
                    return False
            cur.execute("""
                UPDATE holes_findings
                   SET status='remediated', remediated_at=now(),
                       remediated_via='auto', remediated_by=%s
                 WHERE finding_id_hash=%s AND status='open'
            """, (self.name, finding["finding_id_hash"]))
            return True
        except Exception:
            return False


def run_cli(routine_cls):
    """Standard CLI entry point. Every routine module ends with `if __name__: run_cli(MyRoutine)`."""
    ap = argparse.ArgumentParser(description=routine_cls.description or routine_cls.name)
    ap.add_argument("--auto", action="store_true", help="auto-remediate where finding declares fix_sql/fix_command")
    ap.add_argument("--dry-run", action="store_true", help="run logic but don't persist findings or runs")
    ap.add_argument("--json", action="store_true", help="output result as JSON")
    args = ap.parse_args()
    r = routine_cls()
    result = r.run(auto_remediate=args.auto, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        ok = "✓" if result["status"] == "ok" else "✗"
        print(f"  {ok} {routine_cls.name}: "
              f"{result['findings_persisted']} new findings "
              f"({result['p0_count']} P0), "
              f"{result['duration_ms']}ms"
              + (f" [error: {result['error']}]" if result.get("error") else ""))
    sys.exit(0 if result["status"] == "ok" else 1)
