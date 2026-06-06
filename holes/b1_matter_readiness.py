"""holes.b1_matter_readiness — per-matter readiness scorecard.

Daily 06:00 PHT. For each active matter, computes:
  - classification_pct      : docs in case_file with classification IS NOT NULL
  - stage_known             : matters.current_stage IS NOT NULL
  - deadline_known          : matters.next_deadline IS NOT NULL AND >= today
  - last_activity_days      : days since most recent document OR gmail in case_file
  - evidence_gap_pct        : NULL if not applicable, else from transfer_completeness

Emits one finding per matter whose composite readiness score is below threshold.
Severity scales with how far below.

This is the COMPASS — a single daily view of where Leo is blind across all 17 matters.
"""
from datetime import date

from holes.base import Routine, run_cli

# Thresholds — below these → emit finding
CLASSIFICATION_FLOOR = 0.85   # 85% of docs must be classified
STALE_DAYS = 21               # >21 days no activity = stale matter
# Composite score weights
W_CLASSIFICATION = 0.30
W_STAGE = 0.20
W_DEADLINE = 0.20
W_ACTIVITY = 0.15
W_EVIDENCE = 0.15


class B1_MatterReadiness(Routine):
    name = "B1_matter_readiness"
    version = "v1"
    hole_type = "coverage_gap"
    cadence = "daily"
    severity_default = "P2"
    description = "Per-matter readiness scorecard. Daily compass on where Leo is blind across all active matters."

    def find_holes(self, cur):
        cur.execute("""
            SELECT matter_code, case_file, title, status, docket_number,
                   current_stage, next_event, next_deadline, next_event_owner,
                   stage_updated_at
              FROM matters
             WHERE status='active'
             ORDER BY matter_code
        """)
        matters = cur.fetchall()
        if not matters:
            return

        today = date.today()

        for m in matters:
            mc = m["matter_code"]
            cf = m["case_file"]

            # 1. Classification coverage
            cls_pct = None
            if cf:
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE classification IS NOT NULL AND classification <> '')::float
                           / NULLIF(COUNT(*), 0) AS pct,
                           COUNT(*) AS total
                      FROM documents WHERE case_file = %s
                """, (cf,))
                r = cur.fetchone()
                cls_pct = float(r["pct"]) if r and r["pct"] is not None else None
                docs_total = r["total"] if r else 0
            else:
                docs_total = 0

            # 2. Stage known
            stage_known = bool(m.get("current_stage"))

            # 3. Deadline known + in the future
            deadline_known = (
                m.get("next_deadline") is not None
                and m["next_deadline"] >= today
            )

            # 4. Last activity
            last_doc_days = None
            last_gmail_days = None
            if cf:
                cur.execute("""
                    SELECT EXTRACT(EPOCH FROM (now() - MAX(GREATEST(doc_date_norm::timestamptz, ingested_at)))) / 86400 AS days
                      FROM documents WHERE case_file = %s
                """, (cf,))
                r = cur.fetchone()
                last_doc_days = float(r["days"]) if r and r["days"] is not None else None
                try:
                    cur.execute("""
                        SELECT EXTRACT(EPOCH FROM (now() - MAX(received_at))) / 86400 AS days
                          FROM gmail_messages WHERE case_file = %s
                    """, (cf,))
                    r = cur.fetchone()
                    last_gmail_days = float(r["days"]) if r and r["days"] is not None else None
                except Exception:
                    last_gmail_days = None
            activity_days = min(
                [d for d in (last_doc_days, last_gmail_days) if d is not None],
                default=None,
            )

            # 5. Evidence gap (only meaningful for matters with a transfer-based theory)
            evidence_gap_pct = None
            try:
                cur.execute("""
                    SELECT AVG(100 - completeness_pct) AS gap
                      FROM transfer_completeness
                """)
                r = cur.fetchone()
                if r and r["gap"] is not None and mc.startswith("MWK"):
                    evidence_gap_pct = float(r["gap"])
            except Exception:
                pass

            # Composite score (0-1)
            s_cls = cls_pct if cls_pct is not None else 0.0
            s_stage = 1.0 if stage_known else 0.0
            s_deadline = 1.0 if deadline_known else 0.0
            s_activity = 0.0
            if activity_days is None:
                s_activity = 0.0
            elif activity_days <= 7:
                s_activity = 1.0
            elif activity_days <= STALE_DAYS:
                s_activity = 1.0 - (activity_days - 7) / (STALE_DAYS - 7)
            else:
                s_activity = 0.0
            s_evidence = 1.0
            if evidence_gap_pct is not None:
                s_evidence = max(0.0, 1.0 - (evidence_gap_pct / 100.0))

            score = (
                W_CLASSIFICATION * s_cls
                + W_STAGE * s_stage
                + W_DEADLINE * s_deadline
                + W_ACTIVITY * s_activity
                + W_EVIDENCE * s_evidence
            )

            # Severity scaling
            if score < 0.40:
                severity = "P1"
            elif score < 0.65:
                severity = "P2"
            elif score < 0.85:
                severity = "P3"
            else:
                # Healthy enough — don't emit
                continue

            # Build a focused description + suggested fix
            issues = []
            fixes = []
            if cls_pct is not None and cls_pct < CLASSIFICATION_FLOOR:
                issues.append(f"classification {int(cls_pct*100)}% (target ≥{int(CLASSIFICATION_FLOOR*100)}%)")
                fixes.append(f"Run classify pass on case_file={cf}: docs missing classification.")
            if not stage_known:
                issues.append("current_stage NULL")
                fixes.append("Run classify_case_stage.py for this matter.")
            if not deadline_known:
                if m.get("next_deadline") and m["next_deadline"] < today:
                    issues.append(f"next_deadline PAST DUE ({m['next_deadline']})")
                    fixes.append("Update next_deadline + next_event; investigate why post-deadline filings exist.")
                else:
                    issues.append("next_deadline NULL")
                    fixes.append("Set next_deadline from current procedural stage.")
            if activity_days is None:
                issues.append("no documents or emails ever in this matter")
            elif activity_days > STALE_DAYS:
                issues.append(f"no activity in {int(activity_days)} days")
                fixes.append("Send chase email to counsel or schedule follow-up.")
            if evidence_gap_pct is not None and evidence_gap_pct > 50:
                issues.append(f"evidence gap ≈{int(evidence_gap_pct)}% (avg across transfers)")
                fixes.append("Review transfer_completeness; close primary-instrument gaps.")

            desc = (
                f"Matter {mc} ({m.get('title') or '?'}) readiness score "
                f"{int(score*100)}/100 — " + "; ".join(issues)
            )
            self.emit(
                severity=severity,
                description=desc,
                case_file=cf,
                matter_code=mc,
                suggested_fix=" / ".join(fixes) if fixes else None,
                metadata={
                    "score": round(score, 3),
                    "classification_pct": cls_pct,
                    "stage_known": stage_known,
                    "deadline_known": deadline_known,
                    "last_activity_days": activity_days,
                    "evidence_gap_pct": evidence_gap_pct,
                    "docs_total": docs_total,
                    "current_stage": m.get("current_stage"),
                    "next_deadline": str(m["next_deadline"]) if m.get("next_deadline") else None,
                },
                hash_parts={"matter_code": mc},  # one open finding per matter
            )


if __name__ == "__main__":
    run_cli(B1_MatterReadiness)
