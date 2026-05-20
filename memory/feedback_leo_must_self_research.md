---
name: feedback-leo-must-self-research
description: "Leo's clarification questions must be unanswerable from the corpus. If the answer is derivable from existing documents, Leo MUST research first and propose an answer, only escalating to Jonathan for confirmation. Stated 2026-05-16 after Leo asked about Civil Case 6839 which was already in DOC 351/352."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

When Leo has a question, the answer-source priority is:
  1. **Search the corpus first** (documents, entities, conversations, chat_notes)
  2. If corpus yields a likely answer → state it, ask Jonathan to confirm/correct
  3. Only if no corpus answer is findable → ask Jonathan the open question

**Why:** Stated by Jonathan 2026-05-16 after Leo asked clarification_question #1 *"Is Civil Case 6839 the same as 26-360?"* — the answer was sitting in DOC 351 + 352 ("Just compensation volume 1+2") which clearly identify 6839 as a DAR/Land Bank just-compensation case at RTC Branch 40 represented by Cesar Dela Fuente. Jonathan: *"this is something LEO should be able to decipher"* + *"I will not answer because LEO should know"*.

**How to apply:**

When synthesizing clarification_questions (educate_leo / synthesize_case): explicitly filter to questions that are NOT answerable from the corpus. Indicators an answer IS in the corpus:
  - The entity name (case docket, party, TCT) has 2+ document mentions → likely derivable
  - The question is about historical facts/dates/parties → likely derivable
  - The question is about who/what/when of an already-extracted instrument → likely derivable

Indicators a question genuinely needs Jonathan:
  - Subjective intent ("should we file motion X or Y?")
  - Future plans ("when do you want to do Z?")
  - External-world facts not in any doc ("is Cesar still alive?")
  - Confirmation of an inference ("Leo proposes X — confirm?")

For each pending question, BEFORE asking Jonathan:
  1. Run a corpus search for question keywords
  2. Pull top 5 docs with relevant excerpts
  3. Call LLM with question + excerpts → likely_answer + confidence
  4. If confidence > 0.7: propose the answer in DM ("I think 6839 is X — confirm?")
  5. If confidence < 0.7: ask the open question

When Jonathan answers a question (even partially, like "6839 is pending writ of execution"):
  1. Treat as authoritative — UPDATE pending_questions.answer
  2. INSERT chat_note capturing the answer
  3. UPDATE related entities/assets with the new info
  4. Do NOT re-ask the same question even if not fully answered

When Jonathan says "Leo should know" / "you should be able to find this":
  → Demote the question to "self_research_required" state
  → Don't re-ask; do the corpus research now
  → If still not found, propose what Leo CAN find as a starting point

Related: [[feedback-information-is-gold]], [[feedback-legal-ops-ai]] (granular understanding implies derivability).
