-- REVISED (Grok, 2026-10-20 PHT) from Claude's from-claude/DRAFT_drip_v2_fabric.sql — applies Grok's CHANGEs of
-- DRIP_THREAD 07:35 ANSWER on Jonathan's GO (20 Oct 2026 07:40 PHT): R1 running clock needs served_at + proof doc ·
-- R2 calm_routine register (no very_warm) · R3 lint: Ombudsman / failure to comply / complaint at routine rungs;
-- internal labels leak-linted · R4 15-working-day floor before any escalation rung · R5 CV6839 amount_role
-- (₱5,124,922.47 principal, doc 377 = at_stake; ₱48,250,900 = valuation). NO hearing rows, NO calendar W1 wiring.
-- Original header follows.
-- DRAFT (NOT APPLIED) — Drip v2 "fabric" back-end: registry hardening, strategic layer, output construction.
-- Spec: agent_specs/005_drip.md §v2 (Stages 0–8) + docs/RELATIONSHIP_EQUILIBRIUM.md §7 (S1–S5, §7.6 rope doctrine).
-- Drafted 2026-10-20 on the Mac. Gets a deploy number only on Jonathan's go and after the Claude↔Grok
-- ping-pong round. Idempotent and additive: no DROP, no data rewrite. The new CHECKs are NOT VALID, so legacy
-- rows aren't re-judged until VALIDATE is run deliberately.
--
-- Extends, does not duplicate:
--   office_obligation / escalation_rung / drip_event / drip_edition (005 v1) · work_orders (§0.4.7 ledger) ·
--   client_goals (goal links) · case_forums (per-issue forum candidates; forum_power below is the general law
--   table it can cite) · contradictions (A65 register; drip_xref rows go there) · fact_fields (E3 amount role).
--
-- Dry run:  (sed '$d' migrations/DRAFT_drip_v2_fabric.sql; echo ROLLBACK;) | docker exec -i n8n-postgres-1 psql -U n8n -d n8n -v ON_ERROR_STOP=1

BEGIN;

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 0. THE INTERNAL GOAL PER MATTER — what we are really after (INTERNAL ONLY; never rendered outward)
--    MASTER_PLAN §0.4.1: every front has objective · remedy · forum · next move · date · owner.
--    Extends matter_objectives (goal_id → client_goals) instead of a new goals table.
-- ════════════════════════════════════════════════════════════════════════════════════════════════
ALTER TABLE matter_objectives
  ADD COLUMN IF NOT EXISTS internal_goal       text,          -- the result we want from THIS matter, in our words
  ADD COLUMN IF NOT EXISTS remedy              text,          -- the remedy that delivers it
  ADD COLUMN IF NOT EXISTS forum_code          text,          -- the forum that can grant it (G1; joins forum_power)
  ADD COLUMN IF NOT EXISTS success_criteria    text,          -- how we will know it landed (observable, documentable)
  ADD COLUMN IF NOT EXISTS money_target_php    numeric(14,2), -- at-stake value if any (sourced)
  ADD COLUMN IF NOT EXISTS money_source_doc_id integer REFERENCES documents(id),
  ADD COLUMN IF NOT EXISTS next_move           text,
  ADD COLUMN IF NOT EXISTS next_move_date      date,          -- sourced from a procedural rule or set by Jonathan; never invented
  ADD COLUMN IF NOT EXISTS owner               text,
  ADD COLUMN IF NOT EXISTS walk_away           text,          -- what we will not trade / the floor (internal)
  ADD COLUMN IF NOT EXISTS goal_set_by         text,          -- 'jonathan' | 'proposed:<desk>' (proposed ≠ set)
  ADD COLUMN IF NOT EXISTS goal_set_at         timestamptz,
  ADD COLUMN IF NOT EXISTS visibility          text NOT NULL DEFAULT 'internal';

DO $$ BEGIN
  ALTER TABLE matter_objectives ADD CONSTRAINT mo_visibility_internal CHECK (visibility IN ('internal','client_ready')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- money target ranks only with a source; a set goal names who set it
DO $$ BEGIN
  ALTER TABLE matter_objectives ADD CONSTRAINT mo_money_needs_source CHECK (money_target_php IS NULL OR money_source_doc_id IS NOT NULL) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Every obligation says which internal goal it serves and how (internal-only reasoning; the office never sees it)
ALTER TABLE office_obligation
  ADD COLUMN IF NOT EXISTS serves_objective_id  integer REFERENCES matter_objectives(id),
  ADD COLUMN IF NOT EXISTS how_it_serves        text;   -- e.g. 'certified copies = Exhibit for 9 Dec formal offer'

-- The front card: one row per matter — the six things + the drip slice. Read by the pick, CoS cards, inquiry.
CREATE OR REPLACE VIEW v_matter_front_card AS
SELECT mo.matter_code,
       mo.id                                   AS objective_id,
       cg.goal_text                            AS client_goal,
       mo.internal_goal, mo.remedy, mo.forum_code, mo.success_criteria,
       mo.money_target_php, mo.next_move, mo.next_move_date, mo.owner, mo.walk_away,
       mo.goal_set_by,
       (mo.internal_goal IS NOT NULL AND mo.remedy IS NOT NULL AND mo.forum_code IS NOT NULL
        AND mo.next_move IS NOT NULL AND mo.next_move_date IS NOT NULL AND mo.owner IS NOT NULL) AS six_things_complete,
       (mo.next_move_date IS NOT NULL AND mo.next_move_date < current_date)                    AS next_move_stale,
       (SELECT count(*) FROM office_obligation o WHERE o.serves_objective_id = mo.id
          AND o.state NOT IN ('performed','withdrawn','consequence_filed'))                     AS open_obligations,
       (SELECT count(*) FROM office_obligation o WHERE o.serves_objective_id = mo.id
          AND o.state IN ('served_running','replied_not_performed','partial'))                  AS clocks_running,
       mo.visibility
  FROM matter_objectives mo
  LEFT JOIN client_goals cg ON cg.id = mo.goal_id;

COMMENT ON VIEW v_matter_front_card IS
  'INTERNAL. The six things per matter (§0.4.1) + drip slice. internal_goal/walk_away never render into outward drafts (lint internal_goal_leak).';

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 1. REGISTRY HARDENING — office_obligation (Stages 0–2, 5; §7 V1–V3; §7.6)
-- ════════════════════════════════════════════════════════════════════════════════════════════════
ALTER TABLE office_obligation
  ADD COLUMN IF NOT EXISTS approved_at            timestamptz,     -- Jonathan's go for THIS item (A39)
  ADD COLUMN IF NOT EXISTS approval_ref           text,            -- where the go is recorded (chat id / card id)
  ADD COLUMN IF NOT EXISTS proof_candidate_doc_id integer REFERENCES documents(id),  -- proposed, never starts a clock
  ADD COLUMN IF NOT EXISTS goal_id                integer REFERENCES client_goals(id),
  ADD COLUMN IF NOT EXISTS money_at_stake_php     numeric(14,2),   -- ONLY at-stake money (judgment, protested tax, paid-unrendered fee)
  ADD COLUMN IF NOT EXISTS money_source_doc_id    integer REFERENCES documents(id),
  ADD COLUMN IF NOT EXISTS pressure_type          text,            -- §7 S3
  ADD COLUMN IF NOT EXISTS rope_phase             text,            -- §7.6
  ADD COLUMN IF NOT EXISTS ripeness               jsonb NOT NULL DEFAULT '{}'::jsonb,  -- §7.6 six conditions, each {met, ref}
  ADD COLUMN IF NOT EXISTS benefit_element_ref    text,            -- RA 3019 §3(f) "for whose benefit" — doc/fact ref, else admin-only
  ADD COLUMN IF NOT EXISTS office_cluster         text,            -- stagger unit (one new rung / cluster / week)
  ADD COLUMN IF NOT EXISTS intake_source          text,            -- harvest file + run date (Stage 0)
  ADD COLUMN IF NOT EXISTS xref_status            text NOT NULL DEFAULT 'unchecked',  -- clean | blocked | flagged | unchecked
  ADD COLUMN IF NOT EXISTS xref_findings          jsonb NOT NULL DEFAULT '[]'::jsonb, -- X1–X12 results, each with recheck_condition (A74)
  ADD COLUMN IF NOT EXISTS xref_checked_at        timestamptz;

DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_state_enum CHECK (state IN (
    'draft_held','held_counsel_route','approved','served_running','replied_not_performed','partial',
    'performed','lapsed','consequence_staged','consequence_filed','withdrawn')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_pressure_enum CHECK (pressure_type IS NULL OR pressure_type IN (
    'attribution','personal_liability','removes_deflect','prices_delay','none')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_rope_enum CHECK (rope_phase IS NULL OR rope_phase IN (
    'rope1_ask','rope2_edition','rope3_supervisor','rope4_notarized','counter_punch')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- approved ⇒ the go is on record (A39); a clean xref is required to leave draft_held for approved
DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_approved_has_ref CHECK (
    state <> 'approved' OR (approved_at IS NOT NULL AND approval_ref IS NOT NULL AND xref_status = 'clean')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- R1 (Grok CHANGE §1): no receipt, no clock — a running/lapsed state requires served_at AND a proof-of-service doc.
DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_running_clock_needs_proof CHECK (
    state NOT IN ('served_running','replied_not_performed','partial','lapsed')
    OR (served_at IS NOT NULL AND service_proof_doc_id IS NOT NULL)) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE office_obligation VALIDATE CONSTRAINT drip_running_clock_needs_proof;  -- all live rows comply (none served)

-- money ranks only with a source document
DO $$ BEGIN
  ALTER TABLE office_obligation ADD CONSTRAINT drip_money_needs_source CHECK (
    money_at_stake_php IS NULL OR money_source_doc_id IS NOT NULL) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 2. STRATEGIC LAYER — docs/RELATIONSHIP_EQUILIBRIUM.md §7.4 (S1, S2, S4; S3 above; S5 view below)
-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- S1: what a forum CAN grant (G1 position fit). Unknown pair = [HUMAN VERIFY], never a pass.
CREATE TABLE IF NOT EXISTS forum_power (
    id                bigserial PRIMARY KEY,
    forum_code        text NOT NULL,           -- e.g. 'CSC-RO5', 'OMB', 'ARTA', 'OP', 'LBAA', 'RTC', 'DILG-RD'
    remedy            text NOT NULL,           -- e.g. 'admin_penalty_appointive', 'title_relief', 'refer_only'
    can_grant         boolean NOT NULL,
    basis             text NOT NULL,           -- statute/rule cited verbatim
    basis_doc_id      integer REFERENCES documents(id),
    provenance_level  text NOT NULL DEFAULT 'inferred_strong',
    notes             text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (forum_code, remedy)
);

-- S2: move prerequisites (G2) — every dependency names what clears it (A74)
CREATE TABLE IF NOT EXISTS move_dependency (
    id                 bigserial PRIMARY KEY,
    move_ref           text NOT NULL,          -- 'ob:<id>' | 'rung:<id>' | 'play:<id>' | 'matter:<code>'
    requires_ref       text NOT NULL,
    client_code        text NOT NULL,          -- A5: both ends must resolve to this client
    basis              text NOT NULL,          -- why (source-cited)
    recheck_condition  text NOT NULL,          -- what clears it
    state              text NOT NULL DEFAULT 'open' CHECK (state IN ('open','met','waived')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (move_ref, requires_ref)
);

-- S4: exposure — the strongest counter-move and our standing answer (V4)
CREATE TABLE IF NOT EXISTS move_exposure (
    id                  bigserial PRIMARY KEY,
    move_ref            text NOT NULL,
    client_code         text NOT NULL,
    counter_move        text NOT NULL,         -- their best response, in their voice
    counter_source      text,                  -- red-team annex path/line
    standing_answer     text,                  -- NULL = exposed
    answer_source       text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (move_ref, counter_move)
);

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 3. OUTPUT CONSTRUCTION — 005 v2 Stage 8 (instruments, style registers, lint, templates)
-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- Per-audience voice. Language/register/limits are data, so the lint and renderers read one source.
CREATE TABLE IF NOT EXISTS drip_style_register (
    audience                text PRIMARY KEY,   -- official | supervisor | forum | operator_tg | operator_chat | officer_task | counsel | client_allan | phone_drip
    language                text NOT NULL,      -- 'en-formal-ph' | 'en-plain' | 'taglish' | ...
    register_note           text NOT NULL,
    max_chars               integer,            -- NULL = no cap (letters are capped by the 1-page rule instead)
    markup_allowed          boolean NOT NULL DEFAULT false,
    one_point               boolean NOT NULL DEFAULT true,
    consequence_from_rung   integer,            -- earliest rung allowed to state consequence (procedure only); NULL = never
    signoff                 text,
    send_mode               text NOT NULL DEFAULT 'draft_only' CHECK (send_mode IN ('draft_only','paste_ready','internal_post')),
    warmth                  text NOT NULL DEFAULT 'warm' CHECK (warmth IN ('calm_routine','warm','neutral')),
    requires_easy_yes       boolean NOT NULL DEFAULT false,   -- every ask makes compliance effortless (we pay / bring / come)
    requires_gracious_close boolean NOT NULL DEFAULT false,
    burden_line_from_rung   integer,          -- earliest output that states the running cost (0 = demand, 1 = edition/R1); NULL = never
    updated_at              timestamptz NOT NULL DEFAULT now()
);

INSERT INTO drip_style_register (audience, language, register_note, max_chars, markup_allowed, one_point, consequence_from_rung, signoff, send_mode, warmth, requires_easy_yes, requires_gracious_close, burden_line_from_rung) VALUES
 ('official',      'en-formal-ph', 'CALM / ROUTINE (tone doctrine 20 Oct 2026): reads like ordinary administrative follow-up; courteous, plain, no effusive praise, no adjectives about conduct; one small easy ask, statute cited plainly without argument; a polite reply-by date; refer to the last letter by its date; close with a named contact; tone constant across rungs', NULL, false, true, NULL, 'Respectfully, [AIF under apostilled SPA]', 'draft_only', 'calm_routine', true, true, 1),
 ('supervisor',    'en-formal-ph', 'CALM / ROUTINE: "for your information and appropriate action"; duty-holder named + dated without blame; officer cc''d; no escalation language', NULL, false, true, 2, 'Respectfully, [AIF under apostilled SPA]', 'draft_only', 'calm_routine', true, true, 1),
 ('forum',         'en-formal-ph', 'Complaint-affidavit register, element by element; measured and courteous (the requester''s good faith is itself an element); one officer, ripest count; counsel signs where matter requires', NULL, false, false, 3, '[per forum rules]', 'draft_only', 'neutral', false, false, 0),
 ('operator_tg',   'en-plain',     'S14: plain, no markup, one point, no second message until reply; decision not status', 280, false, true, NULL, NULL, 'internal_post', 'warm', false, false, NULL),
 ('operator_chat', 'taglish',      'Confident, punchy, warm Taglish with a spark of excitement; 1–2 bite-sized asks; yes/no or one blank (INTERNAL to Jonathan only)', NULL, true, true, NULL, NULL, 'internal_post', 'warm', false, false, NULL),
 ('officer_task',  'en-plain',     'Task card: address, deadline, what to bring back (stamped copy), how to ingest; thank them', NULL, false, true, NULL, NULL, 'internal_post', 'warm', false, false, NULL),
 ('counsel',       'en-formal-ph', 'Act-fast memo: 1-sentence bottom line, ≤15 tagged facts, gaps, actions w/ owner+date, ≤3pp', NULL, true, false, NULL, NULL, 'draft_only', 'neutral', false, false, 0),
 ('client_allan',  'en-plain',     'Allan interaction-style profile; nothing until Jonathan says ready', NULL, false, true, NULL, NULL, 'draft_only', 'warm', false, false, NULL),
 ('phone_drip',    'en-plain',     'Calm, short, courteous, routine, paste-ready; one easy ask; Jonathan sends from his phone; never auto-sent', 500, false, true, NULL, NULL, 'paste_ready', 'calm_routine', true, true, NULL)
ON CONFLICT (audience) DO NOTHING;

-- Per-matter warmth: the relationship note, the warm opener, the easy-yes offers that fit each office in each
-- matter. Data (not prompt text), so every desk and both brains draft in the same voice. Client-scoped (A5).
CREATE TABLE IF NOT EXISTS drip_voice_profile (
    id                 bigserial PRIMARY KEY,
    client_code        text NOT NULL,
    matter_code        text NOT NULL,
    office_cluster     text NOT NULL,              -- e.g. 'LGU Mercedes', 'DENR R5', 'MGB-V', 'RTC Daet OCC'
    audience           text NOT NULL REFERENCES drip_style_register(audience),
    relationship_note  text NOT NULL,              -- the true, documented history to honor (e.g. prior help given)
    warm_openers       text[] NOT NULL DEFAULT '{}',   -- genuine, specific, source-backed (never flattery, never false)
    easy_yes_offers    text[] NOT NULL DEFAULT '{}',   -- what we'll do to make the yes effortless
    gracious_closes    text[] NOT NULL DEFAULT '{}',
    avoid              text[] NOT NULL DEFAULT '{}',   -- sore points for this office (e.g. don't relitigate the CART)
    source_refs        text[] NOT NULL DEFAULT '{}',   -- docs backing any courtesy that recites a fact
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (matter_code, office_cluster, audience)
);

-- Fixed skeletons per output kind (the letter formula; R1/R2/R3; edition; partial reply; ask; task card)
CREATE TABLE IF NOT EXISTS drip_template (
    id             bigserial PRIMARY KEY,
    kind           text NOT NULL,              -- demand | edition | reiteration_r1 | escalation_r2_notarized | consequence_r3 | partial_reply | operator_ask | task_card | phone_drip
    audience       text NOT NULL REFERENCES drip_style_register(audience),
    version        integer NOT NULL DEFAULT 1,
    skeleton_path  text NOT NULL,              -- repo path of the skeleton (single source; review pack reads the same file)
    annex_scheme   jsonb NOT NULL DEFAULT '["A schedule/counters","B served instruments","C proofs of receipt","D law page","E comparator/reply"]'::jsonb,
    active         boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, audience, version)
);

-- Lint rules — the drafting gate (instigation / threats / characterization / untraceable facts)
CREATE TABLE IF NOT EXISTS drip_lint_rule (
    id           bigserial PRIMARY KEY,
    rule_class   text NOT NULL CHECK (rule_class IN ('instigation','threat_early','characterization','untagged_inference','untraceable_fact','multi_duty','multi_officer','markup','length','missing_easy_yes','missing_gracious_close','cold_tone','internal_goal_leak','unpleadable_amount')),
    pattern      text,                         -- regex (case-insensitive); NULL for structural rules checked in code
    audiences    text[] NOT NULL DEFAULT '{official,supervisor,forum}',
    max_rung     integer,                      -- applies at rungs ≤ this (e.g. threats refused at edition/R1)
    action       text NOT NULL DEFAULT 'refuse' CHECK (action IN ('refuse','flag')),
    rationale    text NOT NULL,
    UNIQUE (rule_class, pattern)
);

INSERT INTO drip_lint_rule (rule_class, pattern, audiences, max_rung, action, rationale) VALUES
 ('instigation', '\m(facilitat\w*|grease|token of (appreciation|gratitude)|consideration for (your|the) (help|assistance)|off[- ]record|for your trouble)\M', '{official,supervisor,forum,phone_drip}', NULL, 'refuse', '§7.6: instigation is a complete defense; never offer or invite an unlawful act'),
 ('threat_early', '\m(we will (file|sue|charge)|you will be (charged|sued|held liable)|criminal(ly)? liab\w*)\M', '{official,supervisor}', 1, 'refuse', 'Editions and R1 measure, they never threaten; consequence wording only from R2, and only as procedure'),
 ('characterization', '\m(corrupt\w*|bad faith|malicious\w*|conspir\w*|criminal\w*|fraudster|crook)\M', '{official,supervisor,phone_drip,operator_tg}', NULL, 'refuse', 'Those are a forum''s findings, not our words; name the duty and the date'),
 ('untagged_inference', NULL, '{official,supervisor,forum,counsel}', NULL, 'refuse', 'Every inferred element carries [?]/[HUMAN VERIFY] (MASTER_PLAN §4B); checked in code'),
 ('untraceable_fact', NULL, '{official,supervisor,forum,counsel}', NULL, 'refuse', 'Every date/amount/reference number/day-count must map to a cited doc or SoR row; checked in code'),
 ('multi_duty', NULL, '{official,supervisor}', NULL, 'refuse', 'Splitting rule: one duty + one clock + one consequence forum per letter'),
 ('multi_officer', NULL, '{official,supervisor,forum}', NULL, 'refuse', 'One officer per letter; each receipt = that officer''s clock'),
 ('markup', '[<*_`#]', '{operator_tg,phone_drip}', NULL, 'refuse', 'S14: plain text only'),
 ('length', NULL, '{operator_tg,phone_drip}', NULL, 'refuse', 'max_chars from drip_style_register'),
 ('missing_easy_yes', NULL, '{official,supervisor,phone_drip}', NULL, 'refuse', 'Warmth with substance: every ask offers the effortless yes (requires_easy_yes); checked in code'),
 ('missing_gracious_close', NULL, '{official,supervisor,phone_drip}', NULL, 'flag', 'Close with gratitude and a named contact'),
 ('unpleadable_amount', NULL, '{official,supervisor,forum,phone_drip}', NULL, 'refuse', 'Every peso figure in an outward draft must equal a pleadable loss_line amount as of the stated date (v_dereliction_meter); estimates never go out'),
 ('internal_goal_leak', NULL, '{official,supervisor,forum,phone_drip,client_allan}', NULL, 'refuse', 'Internal goal, walk-away and how_it_serves are ours alone; checked in code by n-gram overlap against matter_objectives/office_obligation'),
 ('cold_tone', '\m(failed to|neglected|refused|demand (that|you)|you are (hereby )?(directed|required)|final (notice|demand)|non-?compliance)\M', '{official,supervisor,phone_drip}', 1, 'flag', 'Same substance, calmer words at editions/R1: "the request of [date] remains open" not "you failed to"'),
 ('threat_early', '\m(ombudsman|failure to comply|failure to act|complaint|complaints)\M', '{official,supervisor,phone_drip}', 1, 'refuse', 'R3 tone doctrine 20 Oct 2026: routine drips (editions/R1) never mention the Ombudsman, "failure to comply", or a complaint; escalation language only at the complaint rung after Jonathan''s go'),
 ('internal_goal_leak', '\m(rope[- ]?a[- ]?dope|counter[- ]?punch\w*|rope[1-4]?_?(ask|edition|supervisor|notarized|phase)|rope doctrine|patient record|go to sleep|lull\w*|walk[- ]away)\M', '{official,supervisor,forum,phone_drip,client_allan,counsel}', NULL, 'refuse', 'R3: internal strategy labels (rope-a-dope, counter-punch, rope phases, patient record) never appear in any outward draft or phone drip')
ON CONFLICT (rule_class, pattern) DO NOTHING;

-- Every drafted output — the traceable artifact between Claude/Grok drafting and service (D5 Ping Pong rows)
CREATE TABLE IF NOT EXISTS drip_instrument (
    id                 bigserial PRIMARY KEY,
    obligation_id      bigint REFERENCES office_obligation(id),
    rung_id            bigint REFERENCES escalation_rung(id),
    edition_id         bigint REFERENCES drip_edition(id),
    kind               text NOT NULL,
    audience           text NOT NULL REFERENCES drip_style_register(audience),
    template_id        bigint REFERENCES drip_template(id),
    client_code        text NOT NULL,                     -- A5
    drafted_by         text NOT NULL,                     -- 'claude' | 'grok:drip' | 'engine' | 'jonathan'
    pingpong_dir       text CHECK (pingpong_dir IN ('to_claude','from_claude')),
    file_path          text,                              -- Drive/repo path of the rendered file
    sha256             text,
    annex_manifest     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{annex, doc_id|path, pinpoint}]
    addressee          jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {name, title, office, email, email_confidence, confirm_by_phone}
    lint_result        jsonb,                             -- per-rule pass/refuse/flag
    status             text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','checked','corrected','approved','printed','served','superseded','refused_lint')),
    approval_ref       text,                              -- Jonathan's per-item go (A39); required at approved+
    work_order_id      bigint REFERENCES work_orders(id), -- §0.4.7 every artifact on the ledger
    supersedes_id      bigint REFERENCES drip_instrument(id),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (status NOT IN ('approved','printed','served') OR approval_ref IS NOT NULL),
    CHECK (status <> 'approved' OR (lint_result IS NOT NULL AND NOT (lint_result ? 'refuse')))
);
CREATE INDEX IF NOT EXISTS drip_instrument_ob_idx ON drip_instrument (obligation_id, status);

-- Kristyle/officer service task — the closer (approved → served_running)
CREATE TABLE IF NOT EXISTS drip_service_task (
    id               bigserial PRIMARY KEY,
    instrument_id    bigint NOT NULL REFERENCES drip_instrument(id),
    assignee         text NOT NULL,                       -- 'kristyle' | 'lbc' | 'jonathan'
    address          text NOT NULL,
    due_date         date,
    method           text NOT NULL CHECK (method IN ('hand','lbc','registered_mail','email','efiling')),
    tracking_ref     text,                                -- LBC waybill etc.
    proof_doc_id     integer REFERENCES documents(id),    -- the ingested stamped copy / POD → feeds record_service
    state            text NOT NULL DEFAULT 'open' CHECK (state IN ('open','served_awaiting_proof','proof_ingested','failed')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 3b. R4 (Grok CHANGE 7.2/7.5; Legal 00:15): 15-WORKING-DAY FLOOR before any escalation rung.
--     Counted from receipt (served_at, proof doc required), day of receipt excluded, Sat/Sun skipped (Rule 22 §1,
--     legal_chunks 3837; RA 6713 §5(a), chunk 133). Holidays: drip_nonworking_day — EMPTY until the 2026 holiday
--     proclamation is ingested and counsel verifies (NEEDS-COUNSEL-VERIFICATION). This is a guard only; it is NOT
--     the calendar W4 shared working-day service and writes no clocks.
-- ════════════════════════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS drip_nonworking_day (
    day        date PRIMARY KEY,
    basis      text NOT NULL,          -- proclamation no. / source URL — no basis, no row
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION drip_working_days_since(p_from date, p_to date) RETURNS integer
LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN p_from IS NULL OR p_to IS NULL OR p_to <= p_from THEN 0 ELSE
    (SELECT count(*)::int FROM generate_series(p_from + 1, p_to, interval '1 day') g(d)
      WHERE extract(isodow FROM g.d) < 6
        AND NOT EXISTS (SELECT 1 FROM drip_nonworking_day h WHERE h.day = g.d::date)) END
$$;

CREATE OR REPLACE FUNCTION drip_escalation_floor_ok(p_obligation_id bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce((SELECT o.served_at IS NOT NULL AND o.service_proof_doc_id IS NOT NULL
                          AND drip_working_days_since(o.served_at, current_date) >= 15
                     FROM office_obligation o WHERE o.id = p_obligation_id), false)
$$;

-- escalation_rung may only leave 'pending' (be staged/approved/served/filed) once the floor is met
CREATE OR REPLACE FUNCTION drip_rung_floor_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state IS DISTINCT FROM 'pending' AND NEW.state NOT IN ('cancelled','withdrawn','superseded')
     AND (TG_OP = 'INSERT' OR OLD.state IS DISTINCT FROM NEW.state)
     AND NOT drip_escalation_floor_ok(NEW.obligation_id) THEN
    RAISE EXCEPTION 'drip floor: rung % (obligation %) refused — no escalation rung before 15 working days from proven receipt', NEW.seq, NEW.obligation_id;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_drip_rung_floor ON escalation_rung;
CREATE TRIGGER trg_drip_rung_floor BEFORE INSERT OR UPDATE OF state ON escalation_rung
  FOR EACH ROW EXECUTE FUNCTION drip_rung_floor_guard();

-- escalation instruments may not be approved/printed/served before the floor either
CREATE OR REPLACE FUNCTION drip_instrument_floor_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.kind IN ('reiteration_r1','escalation_r2_notarized','consequence_r3')
     AND NEW.status IN ('approved','printed','served')
     AND NOT drip_escalation_floor_ok(NEW.obligation_id) THEN
    RAISE EXCEPTION 'drip floor: instrument % (%) refused — no escalation before 15 working days from proven receipt', NEW.id, NEW.kind;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_drip_instrument_floor ON drip_instrument;
CREATE TRIGGER trg_drip_instrument_floor BEFORE INSERT OR UPDATE OF status, kind ON drip_instrument
  FOR EACH ROW EXECUTE FUNCTION drip_instrument_floor_guard();

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 4. THE PICK — determinism + cooldown audit (Stage 5; one-brain §0.12.4)
-- ════════════════════════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS drip_pick_log (
    id              bigserial PRIMARY KEY,
    pick_date       date NOT NULL,
    mode            text NOT NULL CHECK (mode IN ('shadow','live')),
    formula_version text NOT NULL,                 -- e.g. '005v2-§7.2'
    inputs_hash     text NOT NULL,                 -- same DB ⇒ same hash ⇒ same pick (pick_is_deterministic)
    candidates      jsonb NOT NULL,                -- [{ref, gates:{G1,G2,G3}, inputs:{money,credibility,deadline,leverage,pressure,ripeness}, rank}]
    chosen          jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ≤2 refs
    suppressed      jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{ref, reason: cooldown|court_day|dose|gate}]
    delivered_by    text,                          -- exactly one voice
    work_order_id   bigint REFERENCES work_orders(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (pick_date, mode)
);

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 5. EQUILIBRIUM COUPLINGS — E3 amount role; S5 response-rate view
-- ════════════════════════════════════════════════════════════════════════════════════════════════
ALTER TABLE fact_fields ADD COLUMN IF NOT EXISTS amount_role text;   -- at_stake | cost | unknown (derived from verbatim span)
DO $$ BEGIN
  ALTER TABLE fact_fields ADD CONSTRAINT fact_fields_amount_role_enum CHECK (amount_role IS NULL OR amount_role IN ('at_stake','cost','valuation','unknown')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- R5 (Grok CHANGE §5): ₱48,250,900.00 is the FMV/valuation of the land everywhere it appears — never at-stake money.
UPDATE fact_fields SET amount_role = 'valuation'
 WHERE field_kind = 'amount' AND regexp_replace(value_norm, '[^0-9.]', '', 'g') IN ('48250900','48250900.00')
   AND amount_role IS NULL;

-- R5: CV6839 at-stake principal = ₱5,124,922.47, TOTAL of the "Unpaid Amount" column, doc 377 (financial computation).
INSERT INTO matter_facts (matter_code, statement, fact_kind, source_kind, source_id, excerpt, provenance_level, created_by, notes)
SELECT 'MWK-CV6839',
       'CV6839 unpaid principal (TOTAL, "Unpaid Amount" column, T-4494/T-4501/T-4502/T-4503): P5,124,922.47 — the at-stake amount; P48,250,900 is the FMV valuation, not at stake.',
       'fact', 'doc', '377', E'TOTAL\nP5,124,922.47', 'inferred_strong', 'drip_v2_fabric',
       'Grok CHANGE 07:35 / Jonathan GO 2026-10-20; amount_role at_stake'
 WHERE NOT EXISTS (SELECT 1 FROM matter_facts WHERE matter_code='MWK-CV6839' AND created_by='drip_v2_fabric' AND source_id='377');

INSERT INTO fact_fields (fact_id, matter_code, field_kind, value_raw, value_norm, provenance_level, extraction_method, source_span, amount_role)
SELECT f.id, 'MWK-CV6839', 'amount', 'P5,124,922.47', 'PhP5,124,922.47', 'inferred_strong', 'operator_go_20261020', 'P5,124,922.47', 'at_stake'
  FROM matter_facts f WHERE f.matter_code='MWK-CV6839' AND f.created_by='drip_v2_fabric' AND f.source_id='377'
ON CONFLICT (fact_id, field_kind, value_norm) DO NOTHING;

UPDATE matter_objectives SET money_target_php = 5124922.47, money_source_doc_id = 377
 WHERE matter_code = 'MWK-CV6839' AND money_target_php IS NULL;

-- S5: how offices actually respond, by pressure type and rung (counts, not model weights — §7.3)
CREATE OR REPLACE VIEW v_office_response_rate AS
SELECT coalesce(o.office_cluster, o.office)                       AS office_cluster,
       coalesce(o.pressure_type, 'none')                          AS pressure_type,
       coalesce((e.detail->>'rung_seq')::int, 0)                   AS rung_seq,
       count(*) FILTER (WHERE e.kind = 'performed')               AS performed,
       count(*) FILTER (WHERE e.kind = 'replied_not_performed')   AS replied_not_performed,
       count(*) FILTER (WHERE e.kind = 'partial')                 AS partial,
       count(*) FILTER (WHERE e.kind = 'lapse')                   AS silent_past_lapse,
       count(*)                                                   AS outcomes,
       round(count(*) FILTER (WHERE e.kind = 'performed')::numeric / NULLIF(count(*), 0), 3) AS performance_rate
  FROM drip_event e
  JOIN office_obligation o ON o.id = e.obligation_id
 WHERE e.kind IN ('performed','replied_not_performed','partial','lapse')
 GROUP BY 1, 2, 3;

COMMENT ON VIEW v_office_response_rate IS
  'Drip learning loop (RELATIONSHIP_EQUILIBRIUM §7.3): a cell''s V2 weight = performance_rate only when outcomes ≥ 5; weight changes are logged and shown to Jonathan.';

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 6. THE REFERENCE TABLE — every track (judicial + administrative) and the pressure it accumulates
--    A matter can run several tracks (ARTA CTN → OP manifestation → CSC referral → Ombudsman docket); many
--    tracks have no matters row today. One row per track, one row per official × track, one view per question.
-- ════════════════════════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS matter_track (
    track_code         text PRIMARY KEY,               -- stable short id: 'ARTA-1321', 'OP-SPINE', 'OMB-1214', 'CSC-OACL-270', 'CV26360'
    client_code        text NOT NULL,                  -- A5
    parent_matter_code text,                           -- matters.matter_code (NULL ⇒ flagged 'needs matter row')
    kind               text NOT NULL CHECK (kind IN ('judicial','complaint','referral','appeal','supervisory',
                         'records_request','permit','audit','tax_remedy','registration')),
    forum              text NOT NULL,                  -- exact office
    forum_code         text,                           -- joins forum_power (G1)
    docket_or_ref      text,
    our_role           text,                           -- complainant | petitioner | plaintiff | applicant | requester | referred_party
    true_status        text NOT NULL,                  -- as the latest RECORD shows (not the DB's belief)
    status_as_of       date NOT NULL,
    status_source      text NOT NULL,                  -- doc id / path / gmail id — no source, no row
    opened_on          date,
    opened_source      text,
    last_event_on      date,
    last_event         text,
    last_event_source  text,
    next_move          text,
    next_move_date     date,                           -- only from an order / rule / calendar row; else NULL
    feeds_matters      text[] NOT NULL DEFAULT '{}',   -- cross-pollination (§0.4.6)
    counsel_gate       text,
    can_sanction       boolean,                        -- G1: can THIS forum sanction the official? (else: record-builder / exhaustion exhibit)
    provenance_level   text NOT NULL DEFAULT 'inferred_strong',
    notes              text,
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS matter_track_parent_idx ON matter_track (parent_matter_code);

-- Who each track touches and what it adds to the pressure on them (the rope accumulates here)
CREATE TABLE IF NOT EXISTS track_party (
    id               bigserial PRIMARY KEY,
    track_code       text NOT NULL REFERENCES matter_track(track_code) ON DELETE CASCADE,
    official         text NOT NULL,                    -- as named in the source
    entity_id        integer,                          -- entities.id when resolved
    office           text,
    appointive       boolean,                          -- NULL = [?]; decides CSC-RO V vs Ombudsman
    role             text NOT NULL CHECK (role IN ('respondent','duty_holder','supervisor','referred','witness','adverse_party')),
    pressure_adds    text NOT NULL,                    -- 'attributes duty' | 'supervisor informed' | 'personal-liability count pending' | 'exhaustion exhibit' | ...
    pressure_type    text CHECK (pressure_type IS NULL OR pressure_type IN ('attribution','personal_liability','removes_deflect','prices_delay','none')),
    source           text NOT NULL,
    UNIQUE (track_code, official, role)
);

-- REFERENCE VIEW — one line per track, joined to its matter, goal and drip slice
CREATE OR REPLACE VIEW v_matter_reference AS
SELECT t.client_code, t.parent_matter_code, t.track_code, t.kind, t.forum, t.docket_or_ref, t.our_role,
       t.true_status, t.status_as_of, t.status_source,
       m.status AS db_status, m.current_stage AS db_stage,
       (m.matter_code IS NOT NULL AND m.status IS DISTINCT FROM 'active' AND t.true_status ~* 'active|pending|awaiting')
         OR (m.status = 'active' AND t.true_status ~* 'closed|dismissed|lapsed|resolved')        AS db_mismatch,
       (t.parent_matter_code IS NULL)                                                             AS needs_matter_row,
       t.last_event_on, t.last_event, t.next_move, t.next_move_date,
       (t.next_move_date IS NOT NULL AND t.next_move_date < current_date)                         AS next_move_stale,
       t.can_sanction, t.counsel_gate, t.feeds_matters,
       mo.internal_goal,
       (SELECT string_agg(DISTINCT p.official, '; ') FROM track_party p WHERE p.track_code = t.track_code) AS officials
  FROM matter_track t
  LEFT JOIN matters m            ON m.matter_code = t.parent_matter_code
  LEFT JOIN matter_objectives mo ON mo.matter_code = t.parent_matter_code;

-- PRESSURE VIEW — per official: how many tracks, which kinds, open drip clocks, OMB leads, nearest sanction forum
CREATE OR REPLACE VIEW v_official_pressure AS
SELECT t.client_code,
       p.official,
       max(p.office)                                              AS office,
       bool_or(p.appointive)                                      AS appointive,
       count(DISTINCT p.track_code)                               AS tracks,
       count(DISTINCT p.track_code) FILTER (WHERE p.role IN ('respondent','duty_holder')) AS as_respondent_or_duty_holder,
       count(DISTINCT p.track_code) FILTER (WHERE t.can_sanction)                         AS in_sanctioning_forums,
       array_agg(DISTINCT p.track_code)                           AS track_codes,
       array_agg(DISTINCT p.pressure_type) FILTER (WHERE p.pressure_type IS NOT NULL)     AS pressure_types,
       CASE WHEN bool_or(p.appointive) THEN 'CSC-RO V (appointive)'
            WHEN bool_or(p.appointive) = false THEN 'Office of the Ombudsman (elective / §3 counts)'
            ELSE '[?] confirm appointive vs elective' END         AS sanctioning_forum
  FROM track_party p
  JOIN matter_track t ON t.track_code = p.track_code
 GROUP BY t.client_code, p.official;   -- client-scoped by construction (A5); callers filter on client_code

COMMENT ON VIEW v_official_pressure IS
  'Rope accumulation per official across all tracks (RELATIONSHIP_EQUILIBRIUM §7.6). Callers filter by client (A5).';

-- ════════════════════════════════════════════════════════════════════════════════════════════════
-- 7. THE DERELICTION METER — time × inaction → pesos, per track and per official
--    Legal spine (NEEDS-COUNSEL-VERIFICATION): Civil Code Art. 27 (damages vs a public servant who refuses/
--    neglects without just cause) · Arts. 2199 (actual, must be proved) / 2224 (temperate) / 2208 (fees) ·
--    Art. 1169 (mora from demand) · Art. 2209 + Nacar (6% p.a. from demand) · LGC §24 (LGU liable for damage
--    to property) · RA 3019 §3(e) needs ACTUAL, quantified undue injury (Llorente) — the meter is what
--    ripens a §3(f)/admin count into a §3(e) count. Speculative lines never leave the internal plane.
-- ════════════════════════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS loss_line (
    id                   bigserial PRIMARY KEY,
    client_code          text NOT NULL,                       -- A5
    matter_code          text,
    track_code           text REFERENCES matter_track(track_code),
    obligation_id        bigint REFERENCES office_obligation(id),
    official             text,                                -- NULL = institutional (LGU) loss
    loss_kind            text NOT NULL CHECK (loss_kind IN (
                           'paid_unrendered',        -- fee paid, service never rendered
                           'penalty_imposed',        -- charge imposed by the derelict act (e.g. interest for their own delay)
                           'occupation_compensation',-- reasonable compensation for use of registered land
                           'foregone_rent',          -- income the estate can't earn because of the inaction
                           'cost_incurred',          -- courier, travel, fees, notarization caused by the refusals
                           'value_held_up')),        -- principal/value frozen behind the inaction (not a loss; a meter)
    causation            text NOT NULL CHECK (causation IN ('direct','enabling','evidentiary_delay')),
                           -- direct: their act imposed it · enabling: their inaction keeps it running
                           -- evidentiary_delay: their refusal delays our proof (INTERNAL ONLY — too remote to plead)
    legal_class          text NOT NULL CHECK (legal_class IN ('actual_proven','accruing_from_demand','contingent','estimate_internal')),
    principal_php        numeric(14,2),                       -- one-off amount (paid, imposed, value)
    opening_accrued_php  numeric(14,2),                       -- interest already accrued before accrual_start (e.g. doc 377 to 5 Sep 2025)
    monthly_php          numeric(14,2),                       -- running amount per month (compensation, rent)
    annual_interest_pct  numeric(5,2) DEFAULT 6.00,           -- legal interest from demand (Nacar); NULL = none
    rate_basis           text NOT NULL,                       -- e.g. 'LGU ARP GR-2014-HH-07-005-00236: ₱970/sqm × 6% p.a.'
    basis_ref            text NOT NULL,                       -- doc id / path — no basis, no line
    basis_doc_id         integer REFERENCES documents(id),
    accrual_start        date,                                -- the date the clock legally starts
    start_rule           text NOT NULL,                       -- 'service of demand' | 'payment date' | 'lapse of §252 period' | ...
    start_proof_doc_id   integer REFERENCES documents(id),    -- REQUIRED for accruing_from_demand to accrue (corpus-proof rule)
    accrual_end          date,
    pleadable            boolean NOT NULL DEFAULT false,      -- counsel-confirmed safe to state outward
    provenance_level     text NOT NULL DEFAULT 'inferred_strong',
    notes                text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (principal_php IS NOT NULL OR monthly_php IS NOT NULL),
    CHECK (legal_class <> 'accruing_from_demand' OR accrual_start IS NULL OR start_proof_doc_id IS NOT NULL),
    CHECK (causation <> 'evidentiary_delay' OR pleadable = false)
);

-- The meter: accrued to date, what each month of inaction adds, and what each month WE leave unserved costs us
CREATE OR REPLACE VIEW v_dereliction_meter AS
WITH b AS (
  SELECT l.*,
         (l.accrual_start IS NOT NULL
          AND (l.legal_class <> 'accruing_from_demand' OR l.start_proof_doc_id IS NOT NULL))       AS running,
         GREATEST(0, (coalesce(l.accrual_end, current_date) - l.accrual_start))::int               AS days_running
    FROM loss_line l)
SELECT b.id, b.client_code, b.matter_code, b.track_code, b.official, b.loss_kind, b.causation, b.legal_class,
       b.running, CASE WHEN b.running THEN b.days_running ELSE 0 END AS days_in_default,
       b.principal_php, b.monthly_php,
       round(CASE WHEN b.running THEN
               coalesce(b.principal_php,0) + coalesce(b.opening_accrued_php,0)
             + coalesce(b.monthly_php,0) * b.days_running / 30.4375
             + coalesce(b.principal_php,0) * coalesce(b.annual_interest_pct,0)/100 * b.days_running / 365.0
             ELSE coalesce(b.principal_php,0) END, 2)                                              AS accrued_php,
       round(coalesce(b.monthly_php,0)
             + coalesce(b.principal_php,0) * coalesce(b.annual_interest_pct,0)/100 / 12, 2)        AS adds_per_month_php,
       -- the closer gap priced: a demand-based stream that isn't running yet because we haven't served
       CASE WHEN b.legal_class = 'accruing_from_demand' AND NOT b.running
            THEN coalesce(b.monthly_php,0) END                                                     AS unaccruable_per_month_until_served_php,
       b.rate_basis, b.basis_ref, b.start_rule, b.pleadable, b.notes
  FROM b;

-- Per official: what their inaction has cost / is costing, split by how far it is usable in law
CREATE OR REPLACE VIEW v_official_loss AS
SELECT client_code, coalesce(official, '(institution)') AS official,
       sum(accrued_php) FILTER (WHERE legal_class = 'actual_proven')        AS actual_proven_php,
       sum(accrued_php) FILTER (WHERE legal_class = 'accruing_from_demand') AS accruing_php,
       sum(accrued_php) FILTER (WHERE legal_class = 'contingent')           AS contingent_php,
       sum(accrued_php) FILTER (WHERE legal_class = 'estimate_internal')    AS internal_estimate_php,
       sum(adds_per_month_php) FILTER (WHERE running)                       AS adds_per_month_php,
       max(days_in_default)                                                 AS longest_default_days,
       bool_or(legal_class = 'actual_proven' AND causation = 'direct')      AS s3e_injury_element_present
  FROM v_dereliction_meter
 GROUP BY client_code, coalesce(official, '(institution)');

COMMENT ON VIEW v_official_loss IS
  'INTERNAL. s3e_injury_element_present = an actual, proven, directly caused loss exists (Llorente) — the §3(e) gate. Never shown outward unless pleadable.';

-- The record of NOTICE: which official was told, kindly and in writing, what the open request costs — the knowledge
-- element (Art. 27 'without just cause'; gross neglect; §3(e) evident bad faith) is built here, one served line at a time.
CREATE TABLE IF NOT EXISTS loss_notice (
    id                   bigserial PRIMARY KEY,
    loss_line_id         bigint NOT NULL REFERENCES loss_line(id),
    instrument_id        bigint REFERENCES drip_instrument(id),   -- the edition / R1 / R2 that carried it
    official             text NOT NULL,
    stated_amount_php    numeric(14,2) NOT NULL,                 -- exactly the figure printed in the instrument
    stated_as_of         date NOT NULL,
    stated_text          text NOT NULL,                          -- the verbatim sentence (warm form) as served
    served_proof_doc_id  integer REFERENCES documents(id),       -- NULL until the stamped copy is ingested; notice counts only with it
    created_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (loss_line_id, instrument_id)
);

-- Only pleadable lines may be stated outward (estimates and evidentiary-delay lines never leave the internal plane)
CREATE OR REPLACE FUNCTION loss_notice_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM loss_line l WHERE l.id = NEW.loss_line_id AND l.pleadable
                   AND l.legal_class IN ('actual_proven','accruing_from_demand')) THEN
    RAISE EXCEPTION 'loss_notice: loss_line % is not pleadable (counsel-confirmed actual or accruing) — cannot be stated outward', NEW.loss_line_id;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_loss_notice_guard ON loss_notice;
CREATE TRIGGER trg_loss_notice_guard BEFORE INSERT OR UPDATE ON loss_notice FOR EACH ROW EXECUTE FUNCTION loss_notice_guard();

-- Per official: informed of how much, since when, proven by what — feeds track_party ripeness and the §7.6 counter-punch
CREATE OR REPLACE VIEW v_official_burden_notice AS
SELECT l.client_code, n.official,
       count(*) FILTER (WHERE n.served_proof_doc_id IS NOT NULL)             AS notices_proven,
       min(n.stated_as_of) FILTER (WHERE n.served_proof_doc_id IS NOT NULL)  AS first_informed_on,
       max(n.stated_amount_php) FILTER (WHERE n.served_proof_doc_id IS NOT NULL) AS latest_stated_php,
       (current_date - min(n.stated_as_of) FILTER (WHERE n.served_proof_doc_id IS NOT NULL)) AS days_since_informed
  FROM loss_notice n JOIN loss_line l ON l.id = n.loss_line_id
 GROUP BY l.client_code, n.official;

-- The financial-legal remedies — who pays, under what, with which elements (seed = NEEDS-COUNSEL-VERIFICATION)
CREATE TABLE IF NOT EXISTS financial_remedy (
    remedy_code      text PRIMARY KEY,
    statute          text NOT NULL,
    liable           text NOT NULL CHECK (liable IN ('official_personally','institution','both')),
    elements         text[] NOT NULL,                 -- what must be on the record
    needs_actual_injury boolean NOT NULL DEFAULT false,
    forum            text NOT NULL,
    measure          text NOT NULL,                   -- what the money is
    notes            text
);
INSERT INTO financial_remedy VALUES
 ('ART27',  'Civil Code Art. 27', 'official_personally', '{duty owed,refusal or neglect,without just cause,damage}', false, 'RTC (personal-capacity civil action)', 'actual + moral damages (+ exemplary on bad faith; Art. 2208 fees)', 'Runs from demand; the burden notice (loss_notice) proves "without just cause" after warning'),
 ('ART32',  'Civil Code Art. 32 (6) property without due process', 'official_personally', '{public officer,direct or indirect obstruction or impairment of a property right}', false, 'RTC', 'actual + moral + exemplary; good faith is no defense', 'Fits officers who enable occupation of titled land [NEEDS-COUNSEL]'),
 ('MANDAMUS_DAMAGES', 'Rules of Court Rule 65 §3 and §9', 'both', '{ministerial duty,neglect,no other plain speedy remedy}', false, 'RTC', 'order to perform + damages sustained by reason of the neglect', 'Removes Deflect (Game B) and prices it'),
 ('S3E',    'RA 3019 §3(e) (+ civil liability; §9 penalties)', 'official_personally', '{public officer,manifest partiality / evident bad faith / gross inexcusable negligence,actual quantified undue injury or unwarranted benefit}', true, 'Office of the Ombudsman → Sandiganbayan/RTC', 'restitution/indemnity of the proven injury + perpetual disqualification', 'Llorente: injury must be actual and quantified (loss_line actual_proven, direct)'),
 ('ADMIN_FORFEITURE', 'RACCS 2017 accessory penalties; Ombudsman Act', 'official_personally', '{grave offense proven (e.g. grave misconduct, gross neglect)}', false, 'CSC-RO V (appointive) / Ombudsman (elective, concurrent)', 'dismissal + forfeiture of retirement benefits (the largest personal financial exposure)', 'Not paid to us; it is the officer''s cost of holding out'),
 ('COA_DISALLOWANCE', 'PD 1445 §§52, 103; COA Rules (ND)', 'official_personally', '{disbursement,illegal/irregular,approving/certifying signatories}', false, 'COA Regional Office V', 'amount disallowed, solidarily vs signatories', 'The ₱2.88M expenditure on the heirs'' land (HELD); signatories per 2024 DV'),
 ('LGC24_COMPENSATION', 'LGC §24; Civil Code Arts. 1169, 2209 (Nacar)', 'institution', '{registered land,occupation without instrument,demand}', false, 'RTC', 'reasonable compensation for use + 6% from demand; just compensation in the alternative', 'Paid by appropriation; refusal → mandamus to appropriate'),
 ('RPT_REFUND', 'LGC §§252–253', 'institution', '{protest,payment under protest or excess collection}', false, 'Treasurer → LBAA/courts', 'refund/credit of the excess + interest', 'Macale ₱14,391.50 line becomes actual on payment under protest')
ON CONFLICT (remedy_code) DO NOTHING;

-- Per official × remedy: which money angle applies, what is still missing, which loss lines feed it
CREATE TABLE IF NOT EXISTS official_remedy_fit (
    id               bigserial PRIMARY KEY,
    client_code      text NOT NULL,
    official         text NOT NULL,
    remedy_code      text NOT NULL REFERENCES financial_remedy(remedy_code),
    track_codes      text[] NOT NULL DEFAULT '{}',
    loss_line_ids    bigint[] NOT NULL DEFAULT '{}',
    fit              text NOT NULL CHECK (fit IN ('applies','applies_when_served','applies_when_paid','not_yet','not_applicable','counsel_gate')),
    missing_elements text[] NOT NULL DEFAULT '{}',
    basis            text NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (client_code, official, remedy_code)
);

COMMIT;
