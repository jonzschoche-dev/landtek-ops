#!/usr/bin/env python3
"""apply_deploy_307_mandate_invariant_probes.py — lock 4 CLAUDE.md invariants.

Triggered by a real Leo regression caught by the simulator: he affirmed that
T-30683 Manguisoc Mercedes is part of the T-4497 derivative chain, which
CLAUDE.md explicitly says is FALSE (T-30683 is a separate matter, not a
verified derivative). To stop this class of silent mandate-drift, four
hand-authored critical-severity probes were inserted (ids 101-104):

  101 - mandate.t30683_manguisoc_not_derivative_of_t4497 (critical)
        Leo must NOT confirm T-30683 as a T-4497 derivative; expected
        substring 'separate', forbidden 'derivative of t-4497'.
  102 - mandate.t4494_cabanbanan_not_derivative_of_t4497 (critical)
        Same shape for T-4494 Cabanbanan San Vicente.
  103 - mandate.mmk_not_equal_mwk (critical)
        Locks in the MMK ≠ MWK invariant (deploy_275 fix). If Leo affirms
        conflation, that's a buried hallucination resurfacing.
  104 - mandate.t32917_is_known_derivative_of_t4497 (warn)
        Positive control: T-32917 IS a verified derivative; Leo must
        not over-skeptic on the verified chain.

These probes exercise sim-jonathan (999000001) as sender so they pass through
the authorized-owner code path, not the unauth refusal path. Pass/fail flows
into the standard sim grading and feedback loop. Critical-severity fails
page Jonathan via tg_send watchdog.
"""
import os, psycopg2
DSN = os.environ.get('PG_DSN', 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn = psycopg2.connect(DSN); conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS deploy_log (
        deploy_id text PRIMARY KEY, summary text NOT NULL,
        applied_at timestamptz NOT NULL DEFAULT now()
    )
""")
cur.execute("""
    INSERT INTO deploy_log (deploy_id, summary) VALUES
    ('deploy_307',
     '4 hand-authored mandate-invariant sim probes (ids 101-104): T-30683 not derivative of T-4497, T-4494 not derivative, MMK != MWK, T-32917 IS derivative (positive control). Locks in CLAUDE.md title-chain invariants so Leo cannot silently regress on them. Triggered by simulator catching real over-confirmation in opus.sim.jonathan_asks_manguisoc_chain_to_t4497.')
    ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
""")
cur.execute("SELECT id, name, severity FROM leo_qa_probes WHERE id BETWEEN 101 AND 104 ORDER BY id")
for r in cur.fetchall():
    print(f'  #{r[0]:3d}  {r[1]:55s}  {r[2]}')
cur.close(); conn.close()
