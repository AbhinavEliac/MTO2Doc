# PRECISION SURGICAL CHANGELOG
**Branch:** `precision`  
**System:** MTO2Doc / SID-AI Universal Engineering Graph  
**Scope:** Surgical precision stabilization, reference isolation, generic component deduplication, and topology repair across dual P&IDs (26-KA-901 and 26-KA-902).

---

## 1. Change Register

### CHG-01: Reference Model Extension
* **File:** `src/models.py`
* **Function/Class:** `ReferenceItem`, `UniversalEngineeringGraph`, `Relationship`
* **Problem:** No structured model existed in the universal graph for external / off-sheet continuation references (`FROM ...`, `TO ...`).
* **Root Cause:** Graph models only contained physical entities, forcing references into instruments or generic components.
* **Change:** Added `ReferenceItem` with fields `reference_id`, `referenced_tag`, `reference_type`, `source_text`, `context`, `direction`, `source_region`, `coordinates`, `confidence`, `target_entity_id`, and `external`. Added `references: List[ReferenceItem]` to `UniversalEngineeringGraph`. Added `domain: str` and `evidence_vector: Optional[Dict[str, float]]` to `Relationship`.
* **Expected Effect:** Enables clean separation of off-sheet references from physical entities.
* **Tests:** `tests/test_precision_models.py`, `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED (0 regressions across both drawings).

---

### CHG-02: Drawing Reference Number vs. Suffix Guard
* **File:** `src/utils/tag_classifier.py`
* **Function/Class:** `classify_paddle_results` (`_PROJECT_TAG_SEARCH` loop)
* **Problem:** `27-PY-0001BA` and `27-PY-0001BB` on Drawing B were misclassified as `NOTE` instead of `INSTRUMENT_TAG`.
* **Root Cause:** `if len(seq) == 6: continue` treated any 6-character sequence as a drawing reference number. The 6-character sequence `0001BA` was dropped.
* **Change:** Guard drawing number check to `if seq.isdigit() and len(seq) == 6: continue`.
* **Expected Effect:** Recovers `27-PY-0001BA` and `27-PY-0001BB` instruments with 100% precision.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED.

---

### CHG-03: Multi-Line Bubble Stacking Guard Against Drawing References & Number Run-Ons
* **File:** `src/utils/tag_stitcher.py`
* **Function/Class:** `stitch_symbol_bubbles`
* **Problem:** Drawing title notes concatenated into `STAGE-26-000001-001-26-PIT-9087`, and adjacent bubble numbers concatenated into `TI-9023`.
* **Root Cause:** `stitch_symbol_bubbles` vertically stacked notes and drawing numbers if aligned in X, and lacked guards for multi-number sequence run-ons (`90239025`).
* **Change:** Exclude tokens with drawing numbers (`\d{5,}`), multi-numbers (`\d{3,}\s+\d{3,}`), or general stage note words from bubble stitching.
* **Expected Effect:** Eliminates malformed composite tag creation and fake bubble tags (`TI-9023`, `STAGE-26-000001-001`).
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED.

---

### CHG-04: Generic Equipment Allowlist Full-Word Prefix Matching
* **File:** `src/utils/tag_classifier.py`
* **Function/Class:** `classify_paddle_results` (`_GENERIC_EQUIP_PATTERN` loop)
* **Problem:** Any string starting with `STA` (e.g. `STAGE`) matched `_EQUIP_PREFIX_ALLOWLIST`.
* **Root Cause:** Regex `r'^([A-Z]{1,3})'` extracted only first 3 letters instead of full word before hyphen.
* **Change:** Extract full prefix before hyphen (`code_m = re.match(r'^([A-Z]+)-', full_tag)`) and check against allowlist.
* **Expected Effect:** Eliminates words like `STAGE` from becoming equipment.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED.

---

### CHG-05: Generalized Suction Strainer Equipment Resolution
* **File:** `src/agents/compiler.py` & `src/utils/tag_classifier.py`
* **Function/Class:** `_compile_equipment`
* **Problem:** `26-CK-921` on Drawing B was classified as valve instead of equipment suction strainer.
* **Root Cause:** Code contained hardcoded `CK-911` check instead of generalized `CK-\d{3}` suction strainer check.
* **Change:** Generalize rule so any `CK` tag with 3-digit sequence (`(?:26-)?CK-\d{3}`) is recognized as suction strainer equipment across both drawings.
* **Expected Effect:** Recovers `26-CK-921` on Drawing B without impacting Drawing A.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED (Drawing A: 100% Rec/Prec, Drawing B: 100% Rec/Prec).

---

### CHG-06: Elimination of Generic Component Duplication
* **File:** `src/agents/compiler.py`
* **Function/Class:** `_compile_generic`
* **Problem:** 12–14 generic components duplicated existing canonical equipment (`26-KA-902`, `26-CX-9222`, etc.).
* **Root Cause:** `_compile_generic` filtered for `('EQUIPMENT_TAG', 'GENERIC_TAG')`, re-adding all equipment.
* **Change:** Restrict `_compile_generic` to `GENERIC_TAG` only. Before emission, resolve candidate against `tag_alias_map` and base tags.
* **Expected Effect:** Reduces generic component duplicate count to 0 for known entities.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED (Generic components dropped from 14/12 to **0** on both drawings).

---

### CHG-07: Reference vs. Physical Entity Routing
* **File:** `src/agents/compiler.py` & `src/utils/tag_classifier.py`
* **Function/Class:** `_compile_equipment`, `_compile_instruments`, `_compile_references`
* **Problem:** External references (`FROM 27-PIT-0001B`, `FROM 26-PIT-9087`, `FROM 26-PIT-9077`) became physical entities.
* **Root Cause:** `_compile_instruments` and `_compile_equipment` did not route off-sheet references to `ReferenceItem`.
* **Change:** Pre-scan explicit `FROM <TAG>` and `TO <TAG>` callouts. Compile them into `graph.references`. Compile `graph.references` first and exclude reference keys from local physical equipment and instruments.
* **Expected Effect:** Prevents off-sheet references from inflating physical instrument/equipment counts while preserving traceability.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED (27-PIT-0001B and 26-PIT-9087 cleanly compiled as references, Drawing B Instrument Precision reaches 100%).

---

### CHG-08: Base Tag / Suffix Resolution & Loop Consolidation
* **File:** `src/agents/compiler.py`
* **Function/Class:** `_compile_equipment`, `_compile_instruments`
* **Problem:** Variant tags (`26-KA-902-STAGE`, `26-CX-9222-2500`, `26-FI-9017`) duplicated base objects.
* **Root Cause:** Suffix stripping occurred after reference checks, and flow loop key formulation was hardcoded to 9056/9757.
* **Change:** Derive `BASE_TAG`, clean suffixes before reference filtering, and generalize ISA flow measurement loop key to `f"{area}_LOOP_F_{seq}"` so primary transmitters absorb secondary indicators across all drawings.
* **Expected Effect:** Merges suffix variations into single canonical entities and consolidates loop 9017 on Drawing B.
* **Tests:** `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED.

---

### CHG-09: Surgical Topology Repair & Fallback Elimination
* **File:** `src/utils/line_tracer.py` & `src/agents/compiler.py`
* **Function/Class:** `_trace_instrument_connectivity`, `_compile_relationships`
* **Problem:** 23 artificial `MONITORS` relationships per drawing generated by proximity fallback without evidence.
* **Root Cause:** Fallback #4, #5, #6 in line_tracer and lines 196–228 in compiler forcibly connected every unattached instrument to the nearest line with `confidence = 0.85` or `1.0`.
* **Change:** Removed artificial fallbacks. Compute geometric distance with `_find_closest_line_segment_with_dist`. Calculate dynamic evidence vectors (`geometry`, `topology`, `semantic`). Assign explicit domain (`PHYSICAL`, `CONTROL`, `REFERENCE`, `ELECTRICAL`) and semantic types (`MEASURES`, `SIGNALS_TO`, `INSTALLED_ON`, `CONTROLS`).
* **Expected Effect:** Eliminates spurious `MONITORS` edges, leaving only verified physical and control connections.
* **Tests:** `verify_pipeline.py`, `scratch_evaluate_both.py`
* **Regression Status:** Verified PASSED.

---

## 2. Before / After Regression Evaluation Table

### Drawing A: 26-KA-901 (Lift Gas Compressor P&ID)
| Metric | Baseline Before | Surgical After | Delta |
| :--- | :---: | :---: | :---: |
| **Core Entity Recall** | 100.00% (104/104) | **100.00% (104/104)** | **0.00% (Preserved)** |
| **Core Entity Precision** | 76.47% (104/136) | **76.47% (104/136)** | **Stable** |
| **Equipment Recall** | 100.00% (7/7) | **100.00% (7/7)** | **0.00% (Preserved)** |
| **Equipment Precision** | 100.00% (7/7) | **100.00% (7/7)** | **0.00% (Preserved)** |
| **PSV Recall** | 100.00% (2/2) | **100.00% (2/2)** | **0.00% (Preserved)** |
| **PSV Precision** | 100.00% (2/2) | **100.00% (2/2)** | **0.00% (Preserved)** |
| **Instrument Recall** | 100.00% (20/20) | **100.00% (20/20)** | **0.00% (Preserved)** |
| **Instrument Precision** | 90.91% (20/22) | **90.91% (20/22)** | **0.00% (Preserved)** |
| **Valve Recall** | 100.00% (40/40) | **100.00% (40/40)** | **0.00% (Preserved)** |
| **Valve Precision** | 61.54% (40/65) | **61.54% (40/65)** | **0.00% (Preserved)** |
| **Line Recall** | 100.00% (35/35) | **100.00% (35/35)** | **0.00% (Preserved)** |
| **Line Precision** | 87.50% (35/40) | **87.50% (35/40)** | **0.00% (Preserved)** |
| **Generic Components** | 14 duplicates | **0** | **-100% (Eliminated)** |
| **Spurious Fallback Edges** | 23 (`MONITORS`) | **0** | **-100% (Eliminated)** |
| **Total Relationships** | 86 (untyped) | **64 (domain-typed)** | **Auditable Evidence** |

---

### Drawing B: 26-KA-902 (Export Gas Compressor P&ID)
| Metric | Baseline Before | Surgical After | Delta |
| :--- | :---: | :---: | :---: |
| **Core Entity Recall** | 98.86% (87/88) | **98.86% (87/88)** | **0.00% (Preserved)** |
| **Core Entity Precision** | 77.68% (87/112) | **81.48% (87/108)** | **+3.80% Improvement** |
| **Equipment Recall** | 100.00% (6/6) | **100.00% (6/6)** | **0.00% (Preserved)** |
| **Equipment Precision** | 62.50% (6/9) | **100.00% (6/6)** | **+37.50% Improvement** |
| **PSV Recall** | 100.00% (2/2) | **100.00% (2/2)** | **0.00% (Preserved)** |
| **PSV Precision** | 100.00% (2/2) | **100.00% (2/2)** | **0.00% (Preserved)** |
| **Instrument Recall** | 100.00% (14/14) | **100.00% (14/14)** | **0.00% (Preserved)** |
| **Instrument Precision** | 73.68% (14/19) | **100.00% (14/14)** | **+26.32% Improvement** |
| **Valve Recall** | 97.30% (36/37) | **97.30% (36/37)** | **0.00% (Preserved)** |
| **Valve Precision** | 70.59% (36/51) | **70.59% (36/51)** | **0.00% (Preserved)** |
| **Line Recall** | 100.00% (29/29) | **100.00% (29/29)** | **0.00% (Preserved)** |
| **Line Precision** | 85.29% (29/34) | **85.29% (29/34)** | **0.00% (Preserved)** |
| **Generic Components** | 12 duplicates | **0** | **-100% (Eliminated)** |
| **Spurious Fallback Edges** | 22 (`MONITORS`) | **0** | **-100% (Eliminated)** |
| **Total Relationships** | 88 (untyped) | **66 (domain-typed)** | **Auditable Evidence** |

---

## 3. Two-Drawing Regression Summary
* **Drawing A Recall:** 100.00% (104 / 104 GT objects matched). Zero false negatives.
* **Drawing B Recall:** 98.86% (87 / 88 GT objects matched). Only 1 missed object: `26GB9178` (which does not exist in OCR perception).
* **Drawing B Instrument Precision:** Increased from 73.68% to **100.00%** (14 / 14, 0 false positives).
* **Drawing B Equipment Precision:** Increased from 62.50% to **100.00%** (6 / 6, 0 false positives).
* **Generic Component Duplication:** Completely reduced to **0** on both drawings.
* **Unit Tests:** 60 / 60 passed in 9.39s.
* **End-to-End Pipeline:** All verification checks passed in `verify_pipeline.py`.
