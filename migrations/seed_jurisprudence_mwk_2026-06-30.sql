-- Ingest verified controlling PH jurisprudence into legal_authorities.
-- Each verified 2026-06-30 against lawphil.net (source_url); holding = quoted from the actual decision.
-- provenance_level=verified (cited source + excerpt). Idempotent on (citation, source).
--
-- FULL REPRODUCTION (two stores):
--  1) Structured authorities + matter links (this file):
--       docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/seed_jurisprudence_mwk_2026-06-30.sql
--     (this file also inserts the matter_authorities links to MWK-001 at the bottom — see below)
--  2) Retrievable embedded corpus (legal_chunks, forum CIVIL) via the local Ollama embedder:
--       python3 scripts/legal_authority.py --ingest --forum CIVIL --citation "G.R. No. 114311 (Nov. 29, 1996)" --title "Cosmic Lumber Corp. v. CA"  --source "lawphil:juri1996/nov1996/gr_114311_1996" --file law_seed/case1.txt --verify
--       python3 scripts/legal_authority.py --ingest --forum CIVIL --citation "G.R. No. 165133 (Apr. 19, 2010)" --title "Sps. Alcantara v. Nido"      --source "lawphil:juri2010/apr2010/gr_165133_2010" --file law_seed/case2.txt --verify
--       python3 scripts/legal_authority.py --ingest --forum CIVIL --citation "G.R. No. 248974 (Sept. 7, 2022)" --title "Heirs of Tulauan v. Mateo"   --source "lawphil:juri2022/sep2022/gr_248974_2022" --file law_seed/case3.txt --verify
--       python3 scripts/legal_authority.py --ingest --forum CIVIL --citation "G.R. No. L-30573 (Oct. 29, 1971)" --title "Domingo v. Domingo"          --source "lawphil:juri1971/oct1971/gr_30573_1971" --file law_seed/case4.txt --verify
--  Guarded by scripts/law_coverage.py (CONTROLLING JURISPRUDENCE block).

INSERT INTO legal_authorities (citation, authority_type, title, holding, effective_date, jurisdiction, source, source_url, as_of_checked, provenance_level)
VALUES
($c$G.R. No. 114311 (Nov. 29, 1996)$c$, 'case',
 $t$Cosmic Lumber Corporation v. Court of Appeals and Isidro Perez$t$,
 $h$Agency authority is STRICTLY CONSTRUED: a power of attorney couched in general terms (or for one purpose) does not authorize a sale unless it expressly mentions a sale or includes a sale as a necessary ingredient of the act authorized. The attorney-in-fact, empowered only to institute/file an ejectment suit, instead sold a portion of the principal's land by compromise — acting without authority. Held: "The sale ipso jure is consequently void. So is the compromise agreement." [Bellosillo, J.] — Directly on point: "authority to negotiate" does NOT include authority to sell (de la Fuente SPA).$h$,
 '1996-11-29', 'PH', 'lawphil', 'https://lawphil.net/judjuris/juri1996/nov1996/gr_114311_1996.html', '2026-06-30', 'verified'),

($c$G.R. No. 165133 (Apr. 19, 2010)$c$, 'case',
 $t$Spouses Alcantara, et al. v. Brigida L. Nido (as attorney-in-fact of Revelen N. Srivastava)$t$,
 $h$Civil Code Art. 1874: "When a sale of a piece of land or any interest therein is through an agent, the authority of the latter shall be in writing; otherwise, the sale shall be void." Where the agent lacked WRITTEN authority to sell, the transaction produced no legal effect and could NOT be ratified or enforced by specific performance. [Carpio, J.] — Core test of every de la Fuente land conveyance under the SPA.$h$,
 '2010-04-19', 'PH', 'lawphil', 'https://lawphil.net/judjuris/juri2010/apr2010/gr_165133_2010.html', '2026-06-30', 'verified'),

($c$G.R. No. 248974 (Sept. 7, 2022)$c$, 'case',
 $t$Heirs of Teodoro Tulauan v. Manuel Mateo, et al.$t$,
 $h$An action for reconveyance grounded on a void/inexistent contract (e.g., a forged or unauthorized deed) is IMPRESCRIPTIBLE. Per Civil Code Art. 1410: "the action or defense for the declaration of the inexistence of a contract does not prescribe." [Inting, J.] — Defeats any prescription/laches defense against recovery of the MWK titles built on the void de la Fuente deeds.$h$,
 '2022-09-07', 'PH', 'lawphil', 'https://lawphil.net/judjuris/juri2022/sep2022/gr_248974_2022.html', '2026-06-30', 'verified'),

($c$G.R. No. L-30573 (Oct. 29, 1971)$c$, 'case',
 $t$Vicente M. Domingo (represented by his heirs) v. Gregorio M. Domingo and Teofilo P. Purisima$t$,
 $h$Civil Code Art. 1891: "Every agent is bound to render an account of his transactions and to deliver to the principal whatever he may have received by virtue of the agency." An agent who breaches this fiduciary duty of loyalty (here, a secret profit concealed from the principal) FORFEITS all compensation — whether or not the principal suffered injury. [Makasiar, J.] — Anchors the accounting claim: de la Fuente collected sale proceeds and remitted nothing to the principal ("never a peso").$h$,
 '1971-10-29', 'PH', 'lawphil', 'https://lawphil.net/judjuris/juri1971/oct1971/gr_30573_1971.html', '2026-06-30', 'verified')

ON CONFLICT (citation, source) DO UPDATE
  SET title=EXCLUDED.title, holding=EXCLUDED.holding, effective_date=EXCLUDED.effective_date,
      source_url=EXCLUDED.source_url, as_of_checked=EXCLUDED.as_of_checked, provenance_level=EXCLUDED.provenance_level, updated_at=now();

-- Link the authorities to matter MWK-001 (linkage = inferred_strong: analytical mapping, distinct
-- from the cases themselves which are verified). Idempotent-ish: clear MWK-001 case links first.
DELETE FROM matter_authorities WHERE matter_code='MWK-001'
  AND authority_id IN (SELECT id FROM legal_authorities WHERE source='lawphil');
INSERT INTO matter_authorities (matter_code, authority_id, element_code, relevance, note, provenance_level)
SELECT 'MWK-001', la.id, e.element_code, e.relevance, e.note, 'inferred_strong'
FROM legal_authorities la
JOIN (VALUES
  ('G.R. No. 114311 (Nov. 29, 1996)','agency_scope','SPA "to negotiate" does not authorize a sale; conveyance beyond SPA scope is void','Maps to PE-170453 negotiate-only SPA; voids the de la Fuente deeds of sale/confirmation'),
  ('G.R. No. 165133 (Apr. 19, 2010)','art1874_written_authority','Land sale through agent w/o written authority to sell is void and cannot be ratified','Core validity test for every de la Fuente conveyance; ratification barred (₱0 received)'),
  ('G.R. No. 248974 (Sept. 7, 2022)','reconveyance_imprescriptible','Reconveyance on a void/inexistent deed does not prescribe (Art. 1410)','Defeats prescription/laches vs recovery of titles built on the void post-2005 deeds'),
  ('G.R. No. L-30573 (Oct. 29, 1971)','agent_duty_account','Agent must account & remit all received; unfaithful agent forfeits compensation (Art. 1891)','Anchors the accounting/turnover claim; de la Fuente remitted nothing to the principal')
) AS e(cite, element_code, relevance, note) ON la.citation = e.cite AND la.source='lawphil';

SELECT id, citation, left(title,42) title, provenance_level FROM legal_authorities ORDER BY effective_date;
