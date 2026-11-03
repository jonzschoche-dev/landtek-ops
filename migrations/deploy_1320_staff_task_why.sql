-- deploy_1320: staff_task.why — the reason for each errand, from the same source, so the officer's "why?" is
-- answered from the record (Kristyle asked "Why is it necessary?" about Task 1 on 3 Nov 2026). Idempotent.
ALTER TABLE staff_task ADD COLUMN IF NOT EXISTS why text;

UPDATE staff_task SET why = v.why FROM (VALUES
 (1, 'The Articles (Twelfth article) say the fiscal year begins on 31 December and ends on 30 December. That is an error in the system-generated form; it should be 1 January to 31 December. Fix it before BIR registration so BIR records the right year.'),
 (2, 'Until BIR registration is done (Form 2303 and registered invoices) the company cannot issue official invoices or bill anyone.'),
 (3, 'The company should not hold itself out to clients or open an office to the public until the barangay clearance and the mayor''s permit are issued. The complete lists mean you only go back once.'),
 (4, 'The company needs two accounts: one for operations and a separate one for client money only. The checklist shows what Landbank will ask for before you go.'),
 (5, 'His address goes on the officer form that he signs as alternate nominee, so it must be right before anyone signs.'),
 (6, 'The Certificate and Articles say the officers must be reported within 15 days of 2 November. Late filing carries a P10,000 fine.'),
 (7, 'The barangay clearance needs proof of the office address: a short lease or a consent letter signed by the owner of the premises, which Jonathan will prepare once he knows who the owner is.')
) AS v(seq, why)
WHERE staff_task.source_ref = 'gmail_messages:152157' AND staff_task.seq = v.seq AND staff_task.why IS NULL;
