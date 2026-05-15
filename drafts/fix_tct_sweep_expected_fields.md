# PROPOSED PATCH — tct_sweep.py field-path fix

**Status:** drafted, NOT applied. Awaits Jonathan approval before going to prod.
**Affects:** `/root/landtek/autonomous/tct_sweep.py`
**Lines touched:** 16, 109-119, 121, 146-150 (5 hunks)

## Why

The `EXPECTED` list and the `get_field()` helper in `tct_sweep.py` look for keys
that don't exist in the actual `tct_v3_canonical` contract output. Every pass-1
extraction scores `1/9 = 0.111`, falls below the 0.8 acceptance threshold,
gets `quality_decision='re_extract'`, and never advances to pass 2 — so
`field_consensus` will stay empty forever even if extractions succeed.

### Field mapping (script → actual)

| Script's name | Actual contract path | Notes |
|---|---|---|
| `tct_number` | `title_header.title_number` | renamed |
| `registrant_full_name` | `registered_owners[*].full_legal_name` | array; not a status object |
| `predecessor_title` | `title_history.previous_title_numbers[0]` | array, not status object |
| `issued_date` | `title_header.date_of_original_registration` | renamed |
| `registry_office` | `title_header.registry_of_deeds_full` | renamed |
| `area_sqm` | `technical_description.area_sqm` | moved out of title_header |
| `location_full` | `technical_description.location` | sub-object {barangay, municipality, province} — not a status object |
| `lot_number` | `technical_description.lot_block_plan` | renamed |
| `survey_plan_psd` | `title_header.survey_plan_psd` | only one that already matches |

The contract also has `registered_owners` (array of person objects with
`full_legal_name`, etc.) — these are NOT status objects; they're flat dicts.
Similarly `title_history.previous_title_numbers` is a plain array of strings,
not a status object.

## The patch

```diff
--- a/root/landtek/autonomous/tct_sweep.py
+++ b/root/landtek/autonomous/tct_sweep.py
@@ -14,7 +14,7 @@
 MODEL = 'gemini-2.5-flash'  # only this model — no downgrade
 PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'
-CRITICAL_FIELDS = ['tct_number','registrant_full_name','predecessor_title','area_sqm','lot_number']
+# Each CRITICAL_FIELD pairs a label with a getter that returns (value, source_quote_or_None)
+# given the full extracted result dict. See `get_field` below for path resolution.
+CRITICAL_FIELDS = ['title_number','registered_owners','previous_title_numbers','area_sqm','lot_block_plan']

@@ -109,11 +109,33 @@
-    # Quality score on the EXPECTED 9 fields
-    EXPECTED = ['tct_number','registrant_full_name','predecessor_title','issued_date',
-                'registry_office','area_sqm','location_full','lot_number','survey_plan_psd']
-    extracted_ok = 0
-    th = result.get('title_header') or {}
-    for f in EXPECTED:
-        v = th.get(f) or result.get(f)
-        if isinstance(v, dict) and v.get('field_status')=='extracted' and v.get('source_quote'):
-            extracted_ok += 1
+    # Quality score on the 9 EXPECTED fields, using the actual tct_v3_canonical paths.
+    # `_status_ok(obj)` returns True if obj is a status dict with extracted + source_quote.
+    # `_array_ok(arr)`  returns True if arr is a non-empty list of objects (or strings).
+    def _status_ok(obj):
+        return (isinstance(obj, dict)
+                and obj.get('field_status') == 'extracted'
+                and obj.get('source_quote'))
+    def _array_ok(arr):
+        return isinstance(arr, list) and len(arr) > 0
+
+    th = result.get('title_header') or {}
+    td = result.get('technical_description') or {}
+    hist = result.get('title_history') or {}
+
+    EXPECTED_CHECKS = [
+        ('title_number',                _status_ok(th.get('title_number'))),
+        ('registered_owners',           _array_ok(result.get('registered_owners'))),
+        ('previous_title_numbers',      _array_ok(hist.get('previous_title_numbers'))),
+        ('date_of_original_registration', _status_ok(th.get('date_of_original_registration'))),
+        ('registry_of_deeds_full',      _status_ok(th.get('registry_of_deeds_full'))),
+        ('area_sqm',                    _status_ok(td.get('area_sqm'))),
+        ('location',                    bool((td.get('location') or {}).get('municipality')
+                                            or (td.get('location') or {}).get('province'))),
+        ('lot_block_plan',              _status_ok(td.get('lot_block_plan'))),
+        ('survey_plan_psd',             _status_ok(th.get('survey_plan_psd'))),
+    ]
+    extracted_ok = sum(1 for _, ok in EXPECTED_CHECKS if ok)
-    q_score = round(extracted_ok / len(EXPECTED), 3)
+    q_score = round(extracted_ok / len(EXPECTED_CHECKS), 3)
     q_decision = 'accept' if q_score >= QUALITY_THRESHOLD else 're_extract'

-    tct_val = (th.get('title_number') or {}).get('value') or (result.get('tct_number') or {}).get('value')
+    tct_val = (th.get('title_number') or {}).get('value')

@@ -146,11 +168,26 @@
-                def get_field(d, f):
-                    th = d.get('title_header') or {}
-                    v = th.get(f) or d.get(f)
-                    if isinstance(v, dict): return (v.get('value'), v.get('source_quote'))
-                    return (None, None)
+                def get_field(d, f):
+                    """Resolve a CRITICAL_FIELD to (value, source_quote) using actual contract paths."""
+                    th = d.get('title_header') or {}
+                    td = d.get('technical_description') or {}
+                    hist = d.get('title_history') or {}
+                    if f == 'title_number':
+                        v = th.get('title_number') or {}
+                        return (v.get('value'), v.get('source_quote'))
+                    if f == 'registered_owners':
+                        ros = d.get('registered_owners') or []
+                        names = sorted({(o.get('full_legal_name') or '').strip() for o in ros if o.get('full_legal_name')})
+                        return (' | '.join(names) if names else None, None)
+                    if f == 'previous_title_numbers':
+                        arr = (hist.get('previous_title_numbers') or [])
+                        return (' | '.join(sorted(set(arr))) if arr else None,
+                                (hist.get('source_quote') if isinstance(hist, dict) else None))
+                    if f == 'area_sqm':
+                        v = td.get('area_sqm') or {}
+                        return (str(v.get('value')) if v.get('value') is not None else None, v.get('source_quote'))
+                    if f == 'lot_block_plan':
+                        v = td.get('lot_block_plan') or {}
+                        return (v.get('value'), v.get('source_quote'))
+                    return (None, None)
```

## Behavioral consequence

After this patch, on the 3 already-completed runs (recomputed by hand against
the actual JSON):

| Run id | doc | EXPECTED_CHECKS pass count | quality_score |
|---|---|---|---|
| 7 | 21 (T-32917) | ~6/9 — title_number, registered_owners, area_sqm (in TD), survey_plan_psd, registry_of_deeds_full, date_of_original_registration all present | ~0.67 |
| 8 | 48 (T-52540) | ~6/9 | ~0.67 |
| 9 | 96 (T-52540) | ~6/9 | ~0.67 |

So even the corrected scoring would put these 3 at ~0.67, still below the
0.8 acceptance threshold but a much truer reading. The remaining gap is
mostly `lot_block_plan` and `previous_title_numbers` (`title_history`),
which Gemini doesn't always emit cleanly — that's a real-doc issue, not a
script bug.

**Once applied + re-extracted:** if a doc scores >= 0.8, pass 1 accepts
→ queue stays queued → pass 2 fires on next sweep → cross-validation
runs → `field_consensus` rows finally populate.

## Recommended additional step (not in this patch)

After the patch lands, re-extract docs 21, 48, 96 once more so they get a
post-fix quality_score and the field_consensus pipeline gets a chance to
flip with real data. The existing pass-1 rows can stay; the second pass
will use the new logic on its own.

## Apply

```bash
patch -p1 -d / < this-diff
# or apply by hand at lines 16, 109-119, 121, 146-150
```
