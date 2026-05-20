---
name: feedback-bilingual-corpus-search
description: Leo must ALWAYS search Filipino keywords alongside English when querying the corpus. PH legal pleadings + judicial affidavits frequently use Tagalog for substantive testimony. English-only search misses facts buried in Filipino Q&A.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Concrete miss (2026-05-16):** Jonathan asked whether Cesar de la Fuente was alive. Leo's first pass (truth_negotiator + self_research) returned "TRULY EXTERNAL — not in corpus."

The answer was in fact buried in **doc #407 — Salvador Osum Dela Fuente's Judicial Affidavit**, under oath:

> T5: Asan na ang iyong ama na si Cesar M. dela Fuente?
> S5: **Patay na po.** ("He is already dead.")

Leo's regex searched English: 'deceased','died','death','alive','passed away'. Missed because the affidavit is in Filipino.

Jonathan: "Cesars mortal status has been in the files, if that answer is unavailable we know that the data has not been extracted properly."

**Rule (permanent):** Every corpus search must include BOTH English and Filipino keyword sets for the same concept.

**Bilingual keyword pairs Leo must keep current:**

| concept | English | Filipino |
|---|---|---|
| dead/deceased | dead, deceased, died, late, passed away, expired | patay, namatay, yumao, namayapa, sumakabilang-buhay, pumanaw, namaalam |
| alive | alive, living | buhay, nabubuhay |
| signed | signed, executed | nilagdaan, lumagda, pumirma, lagda |
| received | received, got | natanggap, tinanggap |
| sold | sold | naipagbili, ipinagbili, binili |
| owner | owner | may-ari, mga may-ari |
| land | land, property | lupa, lupain, ari-arian, lupang |
| heir | heir | tagapagmana, mga tagapagmana, mga magmamana |
| father/son | father, son | ama, anak |
| witness | witness | saksi, tagasaksi |
| court | court | hukuman, korte |
| filing | filing | isinampa, isinumpa |
| revoked | revoked, cancelled | binawi, kinansela, pinawalang-bisa |
| authority | authority, power | kapangyarihan, awtoridad, karapatan |
| sworn | sworn, under oath | sumumpa, nakapanunumpa, nanunumpa |
| true | true, truthful | totoo, katotohanan, makatotohanan |
| paid | paid | nagbayad, binayaran |

**How to apply:**

1. Every regex/ILIKE in self_research, truth_negotiator, classify_*, extraction scripts MUST use BOTH columns of the pairs above.
2. Build a `bilingual_search.py` helper module — single function returns SQL-friendly pattern lists per concept.
3. Add unit-test sentinels: known Filipino facts that Leo must surface.
4. When asked a question in English, run the search in BOTH languages and merge results.

Related: [[feedback-leo-must-self-research]] (self-research now must include Filipino),
[[feedback-no-invented-schemas]] (this is a fact-retrieval discipline, same family).
