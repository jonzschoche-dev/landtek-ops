# LandTek product interview (started 2026-11-02, Claude Code, Mac desk)

Purpose: Claude asks Jonathan questions until it knows how to build LandTek into the best product
for its purposes. Answers are recorded verbatim (lightly typo-fixed in brackets only where needed).
When the interview ends, the synthesis is folded into MASTER_PLAN.md in place (no parallel plan doc).
This file is the raw record of his answers, not a plan.

## Round 1 (2026-11-02)

**Q1. Three years from now, who is LandTek mainly for?**
> landtek will be the solution to all stakeholders and the clear choice among potential clients for its
> quality, ease of use and advantageous products to bring clarity and speed to a matter

**Q2. What should a client feel?**
> that the information is clear, trustworthy, adds proper guidance cuts costs brings profit the stack
> cuts out human error and syncs the stakeholders

**Q3. What hurts most today?**
> the products and stack is never live the way I lay out, constantly having to go back over the same
> problems, no visible product as a result

**Q4. Who logs in?**
> all stakeholders should have a permissions usage and that will distill the interactivity and
> information they are privy to

### Claude's read of round 1
- Product = one shared workspace where every stakeholder (Jonathan, officers, clients, counsel,
  partners) sees a permission-filtered slice of the same matter. "Syncs the stakeholders" is the core.
- Value promise: clarity + trust + guidance + lower cost + profit + fewer human errors + speed.
- The real problem is not missing capability. It is that what Jonathan designs never becomes a
  live, visible product, and the same problems recur. Fix that first.

## Round 2 (2026-11-03)

**Q5. Morning surface?** All, one brain: same live record behind web app, chat and email; each
stakeholder uses the channel they already use.

**Q6. Why problems recur?** All four: built but never switched on; sessions forget; scope too wide;
breaks silently.

**Q7. First visible proof?**
> the drip, the chat bot

**Q8. Test for "live"?** Others use it daily (a stakeholder other than Jonathan uses it without
being walked through it).

### Claude's read of round 2
- The first product is the drip plus the chat bot, judged by one test: someone other than
  Jonathan uses it daily, unprompted.
- Every one of the four failure modes is a "finish and keep alive" problem, not a "build more"
  problem. The plan has to include a guard against each.

## Round 3 (2026-11-03)

**Q9. First daily user other than Jonathan?** Kristyle.

**Q10. What must the bot do on day one?**
> it should operate as the ultimate glue to all sections of the corpus, and it should be able to
> answer without using expensive api and tokens

**Q11. After approval, who gets the drip letter to the office?**
> each situation has its prescription, we need an agentic system

**Q12. First channel?** Messenger.

### Claude's read of round 3
- Bot = the glue across the whole corpus (every matter, every section), answering on local/cheap
  inference, not paid frontier tokens.
- Service is not one path: an agent picks the prescribed service route per office/situation
  (email, paper by officer, courier) and runs it.
- Launch: Kristyle on Messenger. Known gap to close first: the Messenger bridge drops inbound media,
  so her proof photos would be lost (memory: chat-bridge-attachment-gap).

## Round 4 (2026-11-03)

**Q13. Drip autonomy after content approval?** Selected all four (pick route, routine follow-ups,
task Kristyle, nothing outward) plus:
> we refine through daily use and there becomes a pattern machine learning style

**Q14. Where the bot's brain runs?**
> we stage it free until we are clear that the stack only needs tokens to become what we need;
> at this time the stack is the bottleneck not the tokens

**Q15. Kristyle's language?**
> you will talk to them and ask them how they want to be talked to

**Q16. Freeze anything?** Nothing frozen.

### Claude's read of round 4
- Earned autonomy: start with every outward act on Jonathan's tap; each approve/reject is logged as
  a training signal; once a pattern (office x action x route) has a clean record, it is promoted to
  run alone. Autonomy is graduated by evidence, not granted up front. (Claude's interpretation of
  the combined answer; confirm with Jonathan.)
- Free/local stack now. Tokens are not the constraint; the stack is.
- Each stakeholder's voice is learned by asking them (onboarding asks how they want to be talked to),
  then stored per person.
- No freeze: so the anti-sprawl guard must be something else (e.g. one "live" gate every track
  must pass before new work on it).

## Round 5 (2026-11-03)

**Q17. Earned autonomy read correct?** Yes, exactly.
**Q18. Anti-sprawl guard?** Live gate: no new feature on a track until its last one is switched on
and used by someone. Built-but-off counts as not done.
**Q19. Where Jonathan approves?** Messenger too (same channel, one item at a time, yes/no/edit).
**Q20. Kristyle using the bot daily by?** This week: Sun 8 Nov 2026.

## Synthesis after 5 rounds (Claude, 2026-11-03; for Jonathan to confirm before it goes into MASTER_PLAN)

**What LandTek is for:** one live record that syncs every stakeholder on a matter, each seeing a
permission-filtered slice, on whatever channel they already use. Promise: clear, trustworthy,
guided, cheaper, profitable, fewer human errors, faster.

**The one problem to beat:** designs never go live, sessions forget, scope sprawls, things break
silently. Capability is not the gap.

**First product:** the drip + the chat bot, on Messenger, first daily user Kristyle, live by
Sun 8 Nov 2026. Jonathan approves on Messenger too.

**Bot:** glue across the whole corpus; answers from the record via database lookups and local
inference (free); no paid tokens until the stack, not tokens, is proven to be the limit. Learns each
person's preferred voice by asking them.

**Drip agent:** per-situation prescriptions (email / officer paper / courier); every outward act on
Jonathan's tap at first; each tap logged; an action pattern graduates to autonomous on a clean
record; Jonathan can revoke.

**Guards (one per failure mode):**
- Built-never-on -> Live gate: a track gets no new feature until its last one is ON and used.
- Sessions forget -> the record (this file, MASTER_PLAN, work_orders), not chat, carries state.
- Scope sprawl -> same Live gate.
- Breaks silently -> the daily-use test itself: if Kristyle's day breaks, it is seen that day.

**Known blockers to check before building (UNVERIFIED until checked):**
- Messenger bridge drops inbound media (memory: chat-bridge-attachment-gap): her proof photos.
- Omnichannel reply brain is forked (memory: project-omnichannel-status, agent_specs/004).
- Leo n8n workflow listed inactive in MASTER_PLAN §4A (as of 2026-06-27; current state UNKNOWN).

## Round 6 (2026-11-03, asked mid-build)

Jonathan: "can you build while we continue to refine?" (A background build agent was refused by the
permission check because it would deploy to the live server unsupervised; build continues in this
session with questions between steps, and every live-server step asks first.)

**Q21. Test the staff desk on the VPS?** Yes, test on VPS (new tables, Kristyle seeded inactive,
dry-run tests that roll back, nothing sent). Deploying the code live is a separate go.

**Q22. How to restart with Kristyle?** Bot opens with her (on go: asks how she wants to be talked
to, then gives her first task).

**Q23. First task = one of the two paper letters to the Mayor?**
> if the bot cannot ascertain the next steps for kristyle its not sufficiently up to date with the
> project so should not communicate about which it does not know

**Q24. Who decides a proof photo counts?** Jonathan, for now (yes/no on Messenger, recorded).

### Claude's read of round 6
- New rule (readiness before speech): the bot works out Kristyle's next steps from the record
  itself. If it can't, the record is out of date, and the fix is the record, not a question to her
  or to Jonathan. It says nothing about what it doesn't know. Built as a readiness check that must
  pass before she is switched on.

## Round 7 (2026-11-03)

**Q25. Where do Kristyle's non-letter errands live?**
> this should be a live corpus, every piece of information should create a ripple throughout the
> corpus, so all pertinent info goes to the proper table

**Q26. Next stakeholder after Kristyle?** Jonathan, fully (complete the operator experience before
adding anyone else).

**Q27. Approval-question budget?**
> no limit one at a time, but stupid questions waste time so we need to train the bot never to ask
> a stupid question

### Claude's read of round 7
- Ripple principle: one input (a message, photo, email, reply) updates every table it bears on
  (task, obligation clock, step plan, matter facts, calendar), not just the one it arrived for.
  Errands are not a separate list; they are derived from the live record.
- Question quality is a trained metric: a question is "stupid" if the record already answers it,
  it's a repeat, or it doesn't change the next action. Each no/edit and each "why are you asking"
  is a signal against that question type.

## Round 8 (2026-11-03)

**Q28. (Jonathan asked) How long until LandTek is the premier stack for its purposes in the PH?**
Claude's answer (ESTIMATE, not a record fact; no competitor data in the record):
staged by the daily-use test. (1) Kristyle daily: this month, blocked only on Jonathan's comments
on letters #9/#11. (2) Jonathan runs his whole day from it: ~4-8 weeks of weekly shipping under the
live gate. (3) A client (Patricia/Allan) self-serves their matter: ~2-3 months after (2). (4) A paying
outside client picks LandTek over a law office/broker: ~6-12 months, if the live gate holds.

**Backups (decided this round):** backups go to a new private Drive folder (Jonathan). Restore the
small nightly record-only dump without the weekly 1.4 GB copy (Jonathan: yes).

## Round 9 (2026-11-03)

Jonathan: "lets relentlessly refine it." Then, instead of answering the stage-2 questions (morning
message, ripple, stupid questions, one brain), he said:
> I should be able to see a very simple dashboard that shows me the state of everything,
> kristyle should have her own dashboard

Built: /ops/now (needs you · office clocks · fronts · field officers · machine) and
/ops/staff/<assignee> (her tasks, done list), SQL-only, behind the existing /ops login.
First read of the live board: 9 items need Jonathan (letters #9 and #11 waiting 14 days),
22 clocks running with 1 overdue (DENR Surveys), and 26 of 26 fronts with no current date
(matters.next_deadline past or empty). That last number is the "record not current" problem
Jonathan named in round 6.

## Round 10 (2026-11-03): first live contact attempt, and what it taught

- Mayor letters #9/#11: never sent (live Gmail checked, all accounts). Both asks already covered
  (DILG Schedule of Default items 1 and 8; Assessor Magana 23 Oct / 2 Nov). Jonathan: supersede both.
- Jonathan: "hayuma is an internal email, jonzschoche is the official communications email."
- Kristyle's real work = Jonathan's 2 Nov email (gmail 152157): loaded as 7 staff_task rows with
  date bases (deploy_1317). Readiness then passed; Jonathan: deploy, switch her on.
- Switched on 03 Nov 01:11 UTC. Facebook refused the opening message to Kristyle:
  "(#100) No matching user found" (subcode 2018001): the page no longer recognizes her July account
  (likely her tester role on the development-mode app lapsed, or her account changed; UNKNOWN which).
- Line check to Jonathan's Messenger: "(#10) sent outside of allowed window" (2018278): the page token
  is valid, but Messenger lets the page write only within 24h of the person's last message.
- PRODUCT LESSON: Messenger is reply-only for a bot. Anything LandTek starts (morning tasks, approval
  questions) cannot ride Messenger unless the person wrote in the last 24 hours.
- Jonathan: "shes got a new messenger elle cece". Explains 2018001: the bot was writing to her old
  July account. "Elle Cece" has never messaged the page. App LEO LANDTEK (1718290972649941) webhook is
  active (page: messages, messaging_postbacks). Fix path: Jonathan adds Elle Cece as app Tester (dev
  mode) -> she accepts -> she messages the page once -> Jonathan confirms it's her -> staff_desk rebind.
- Kristyle LIVE on Messenger (Elle Cece, PSID 40472896185635007) from 03 Nov 02:10 UTC; Jonathan's
  "she writing now" taken as confirmation of identity; rebind carried her contact details.
- Her first minutes taught: voice must be honored (she asked "Taglish and make everything detailed");
  "why?" must be answerable (added staff_task.why from the email); "pass ... go to the second task"
  must work (skip/goto/ordinals); dependencies must travel with tasks (Task 1 before BIR).
- Claude sent her one guess ("pwede mo nang kunin ang TIN") not in the source, then corrected it.
  Lesson recorded: hand-sent messages get the same no-invention discipline as the bot.
