# PRECISION SURGICAL AUDIT
**Date:** September 30, 2026  
**Branch:** `precision`  
**Focus:** Surgical Root Cause Audit for Reference Contamination, Generic Component Duplication, and Topology Repair

---

## 1. System Context & Freeze Directive

The MTO2Doc / SID-AI Universal Engineering Graph system on the `precision` branch has achieved **100% recall** across core engineering entities on Drawing A (26-KA-901) and **95.45% recall** on Drawing B (26-KA-902).

In accordance with Sections 2, 46, and 51 of the instructions:
- **Upstream perception components remain frozen:** EasyOCR, PaddleOCR, YOLO models, line-tag stitching, DPI preprocessing, and ray-casting algorithms are NOT to be rewritten.
- **No monkey patches:** No drawing-specific tag checks, no pandas/csv post-processing hacks, no hardcoded exclusions.
- **Surgical scope:** Changes are strictly localized to downstream entity classification, reference isolation, generic component deduplication, and topology generation/validation.

---

## 2. Comprehensive Runtime Path Audit

### Path 1: Current Canonical Entity Registry
* **Source Files:** [`src/candidate_models.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/candidate_models.py#L176-L320), [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L163-L192)
* **Mechanisms:**
  - `CanonicalEntityRegistry` in `src/candidate_models.py` provides multi-factor candidate deduplication (`canonical_dedup_key`), tracking observations and merge provenance.
  - In `CompilerAgent` (`src/agents/compiler.py`), `tag_alias_map` registers uppercase, canonicalized (`canonicalize_tag`), and stripped-alphanumeric forms for every compiled entity.
* **Findings:** `tag_alias_map` successfully indexes aliases, but downstream compilation lacked a structured model for `ReferenceItem` to hold off-sheet continuation references.

### Path 2: Current Generic-Component Creation Path
* **Source Files:** [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L158,L1358-L1380), [`src/agents/output_generator.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/output_generator.py#L629-L631)
* **Current Code in `_compile_generic`:**
  ```python
  generic_items = [
      t for t in texts
      if t["classification"] in ('EQUIPMENT_TAG', 'GENERIC_TAG')
  ]
  ```
* **Root Cause Identified:** `_compile_generic` intentionally ingested all `EQUIPMENT_TAG` elements in addition to `GENERIC_TAG`. As a direct result, canonical equipment like `26-KA-902`, `26-CX-9021`, `26-CX-9222`, `26-KZ-902`, and `26-KA-902-M01` were inserted into `graph.generic_components`. Then in `output_generator.py`, each generic component was exported to `sppid_import_tables.csv` as a duplicate `GENERIC_COMPONENT`.
* **Surgical Fix:** Remove `EQUIPMENT_TAG` from `_compile_generic`. Attempt resolution of `GENERIC_TAG` items against `tag_alias_map` before emitting. If matched to an existing canonical entity or reference, absorb as attribute/alias; only true unknowns remain generic.

### Path 3: Current Reference Classification Path
* **Source Files:** [`src/utils/tag_classifier.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py#L661-L740), [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L276-L401,L660-L779)
* **Mechanisms:**
  - `tag_classifier.py` checks `is_ref_context` using `r'\b(?:FROM|TO|TIE-IN|CONTINUED\s+ON|SEE\s+DWG|REF\s+DWG)\b'` and sets `it_copy["is_reference"] = True`.
  - However, in `_compile_equipment` and `_compile_instruments`, the `is_reference` attribute was completely ignored.
  - Furthermore, `_BARE_INSTRUMENT_SEARCH` in `tag_classifier.py` did not check `is_ref_context`.
* **Root Cause Identified:** Tags with external continuation context (such as `FROM 27-PIT-0001B` and `FROM 26-PIT-9087` on Drawing B) were classified as `INSTRUMENT_TAG` and compiled directly into `graph.instruments`, polluting the physical entity count.
* **Surgical Fix:** In `CompilerAgent`, extract and route all items marked with `is_reference` or reference context (`FROM ...`, `TO ...`, `REFER DWG`) into a new `graph.references` collection (`ReferenceItem`). They must not become local physical equipment or instruments.

### Path 4: Current Relationship Generation Path
* **Source Files:** [`src/utils/line_tracer.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/line_tracer.py#L115-L376), [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L196-L228)
* **Mechanisms:**
  - `line_tracer.py` traces lines and pairs valves, instruments, PSVs, lines, panels, and earthing.
  - In `line_tracer.py` lines 225-234, an instrument lacking a target fell back to `line_items[0]` or `equipment[0]`.
  - In `compiler.py` lines 204-228, another fallback loop forcibly added `MONITORS` relationships from instruments to `graph.lines[0].tag` or `graph.equipment[0].tag` with `confidence=0.85` to "guarantee zero orphan instruments".
* **Root Cause Identified:** Both layers generated artificial, non-physical `MONITORS` edges solely to eliminate orphan instruments, creating severe relationship false positives.
* **Surgical Fix:** Remove the generic fallback `MONITORS` in both `line_tracer.py` and `compiler.py`. If physical/signal connection evidence does not exist, do not fabricate edges; leave them unlinked or tag them `NEEDS_REVIEW`.

### Path 5: Current Relationship Confidence Calculation
* **Source Files:** [`src/utils/line_tracer.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/line_tracer.py#L178-L242), [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L1451)
* **Current Code:** Confidence is hardcoded as `1.0` or `0.85` without evaluating geometric proximity, continuity, or port alignment.
* **Surgical Fix:** Compute `confidence` from an evidence vector:
  - `geometry_confidence`: distance from trace / snap distance
  - `topology_confidence`: port / inline match vs proximity
  - `semantic_confidence`: loop sequence number match (e.g. `9054` in line `PV-26-9054`)
  Composite relationship confidence = $w_g \cdot C_{\text{geom}} + w_t \cdot C_{\text{topo}} + w_s \cdot C_{\text{sem}}$.

### Path 6: Current Relationship Validation Path
* **Source Files:** [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L1402-L1456), [`src/agents/validation.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/validation.py#L69-L86)
* **Current Code:** `_compile_relationships` checks that source and target map to canonical tags in `tag_alias_map`, drops self-loops, and deduplicates edges.
* **Surgical Enhancement:** Expand validation to check domain compatibility (e.g. `INSTRUMENT` cannot have process `FEEDS` to a `LINE`; `REFERENCE` cannot have physical `CONNECTED_TO` to a local entity).

### Path 7: Current Graph Insertion Path
* **Source Files:** [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L148-L195)
* **Mechanisms:** Compiles each entity category into `UniversalEngineeringGraph` fields (`equipment`, `lines`, `instruments`, `valves`, `safety_relief_valves`, `generic_components`, `annotations`, `relationships`).
* **Surgical Enhancement:** Add `references: List[ReferenceItem]` to `UniversalEngineeringGraph`.

### Path 8: Current Re-Extraction Merge Path
* **Source Files:** [`src/agents/re_extractor.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/re_extractor.py), [`src/graph.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/graph.py#L115-L125), [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L279,L406,L660)
* **Idempotency Guarantee:** Deduplication dictionaries (`seen_equip`, `seen_lines`, `seen_loops`, `seen_valves`) merge repeated observations of the same tag. Re-extracting `PIT-9016` does not produce two entities; it merges into the existing entity and updates observations/provenance.

### Path 9: Current Exporter Input Path
* **Source Files:** [`src/agents/output_generator.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/output_generator.py#L18-L60,L158-L224,L620-L642)
* **Finding:** Exporters consume `UniversalEngineeringGraph` directly. By eliminating duplicate generic components and reference pollution at the compiler stage, export outputs (Excel, CSV, JSON, XML) remain strictly canonical without requiring post-export cleanup hacks.

---

## 3. Specific Defect Discoveries & Exact Root Causes

| Defect ID | Observed Defect | Root Cause Location | Exact Root Cause |
|---|---|---|---|
| **AUD-01** | `26-KA-902`, `26-CX-9021`, etc. duplicated in `generic_components` | [`src/agents/compiler.py#L1363`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L1363) | `_compile_generic` explicitly filtered for `('EQUIPMENT_TAG', 'GENERIC_TAG')`, re-compiling every equipment tag into generic components. |
| **AUD-02** | `STAGE-26-000001-001-26-PIT-9087` created as equipment | [`src/utils/tag_stitcher.py#L385`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_stitcher.py#L385) & [`src/utils/tag_classifier.py#L730`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py#L730) | Vertical bubble stitcher concatenated vertically adjacent drawing number and text. Then `_GENERIC_EQUIP_PATTERN` matched prefix `STA` from `STAGE` against `_EQUIP_PREFIX_ALLOWLIST`. |
| **AUD-03** | `27-PIT-0001B` & `26-PIT-9087` created as physical instruments | [`src/agents/compiler.py#L662`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L662) | `_compile_instruments` ignored `is_reference` flag set by `tag_classifier.py`, promoting off-sheet references to physical instruments. |
| **AUD-04** | `27-PY-0001BA` & `27-PY-0001BB` missed from instruments (classified as `NOTE`) | [`src/utils/tag_classifier.py#L696`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py#L696) | `if len(seq) == 6: continue` assumed all 6-character sequences were drawing numbers. For `0001BA` (4 digits + 2 letters), `len == 6` caused it to be dropped to `NOTE`. |
| **AUD-05** | `26-CK-921` missed from equipment on Drawing B | [`src/agents/compiler.py#L283`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L283) | Hardcoded condition `re.search(r'^(?:26-)?CK-911\b', ...)` only included `CK-911` (Drawing A), leaving `CK-921` (Drawing B) in `VALVE_TAG`. |
| **AUD-06** | Generic fallback `MONITORS` relationship hallucination | [`src/agents/compiler.py#L220-L226`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L220-L226) & [`src/utils/line_tracer.py#L225-L242`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/line_tracer.py#L225-L242) | Unconnected instruments were artificially linked to `graph.lines[0]` or `equipment[0]` with `confidence=0.85` / `1.0`. |
| **AUD-07** | Non-piping specs (`DSS-2500-DSS-EL`, `S-9003-MECHANIC`) compiled as lines | [`src/agents/compiler.py#L422-L432`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L422-L432) | Line tag filter did not reject spec codes or mechanical note sequences without standard fluid service codes. |

---

## 4. Dual-Drawing Baseline Metrics (Pre-Modification)

Evaluated via [`scratch_evaluate_both.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/scratch_evaluate_both.py) against Ground Truth from `pid_stuff/PID_Extraction_RevB_Corrected_26-KA-901_902 (2).xlsx`:

### Drawing A (26-KA-901):
* **Ground Truth:** 104 entities (Equipment: 7, PSV: 2, Instruments: 20, Valves: 40, Lines: 35)
* **Compiled Entities:** 136
* **True Positives (TP):** 104
* **False Positives (FP):** 32
* **False Negatives (FN):** 0
* **Overall Recall:** **100.00%**
* **Overall Precision:** **76.47%**
* **Overall F1:** **0.8667**
* **Generic Components:** 14 (all duplicates of equipment)
* **Relationships:** 85

### Drawing B (26-KA-902):
* **Ground Truth:** 88 entities (Equipment: 6, PSV: 2, Instruments: 14, Valves: 37, Lines: 29)
* **Compiled Entities:** 114
* **True Positives (TP):** 84
* **False Positives (FP):** 27
* **False Negatives (FN):** 4 (`26-CK-921`, `27-PY-0001BA`, `27-PY-0001BB`, `26GB9178`)
* **Overall Recall:** **95.45%**
* **Overall Precision:** **76.32%**
* **Overall F1:** **0.8482**
* **Generic Components:** 12 (all duplicates of equipment/references)
* **Relationships:** 78

---

## 5. Surgical Action Plan

1. **Model Extension (`src/models.py`):**
   - Add `ReferenceItem` model to represent off-sheet, continuation, and tie-in boundary references.
   - Add `references: List[ReferenceItem]` to `UniversalEngineeringGraph`.
   - Add `domain: str` and `evidence_vector: Optional[Dict[str, float]]` to `Relationship`.

2. **Classification & Stitcher Precision (`src/utils/tag_classifier.py` & `src/utils/tag_stitcher.py`):**
   - In `tag_stitcher.py`: prevent stitching multi-line bubbles if any line matches drawing number patterns (`\d{5,6}`) or stage note words.
   - In `tag_classifier.py`: update `len(seq) == 6` drawing reference check to `seq.isdigit() and len(seq) == 6` so alphanumeric sequences like `0001BA` / `0001BB` are preserved as instruments.
   - In `tag_classifier.py`: refine `_GENERIC_EQUIP_PATTERN` prefix extraction to take the full word before the hyphen (preventing `STAGE` from matching prefix `STA`).
   - In `tag_classifier.py`: generalize `CK` equipment classification for suction strainers with 3-digit sequence numbers (`CK-\d{3}`).

3. **Compiler Surgery (`src/agents/compiler.py`):**
   - **Eliminate Generic Duplication:** Change `_compile_generic` to only ingest `GENERIC_TAG`. Attempt resolution of `GENERIC_TAG` items against canonical entities and aliases; if resolved, merge; otherwise emit.
   - **Isolate References:** In `_compile_equipment` and `_compile_instruments`, items with `is_reference=True` or contextual reference markers (`FROM`, `TO`, `REFER`) are compiled into `graph.references`, NOT physical entities.
   - **Base Tag / Suffix Resolution:** Tags with suffix qualifiers (e.g. `26-KA-902-STAGE`, `26-CX-9222-2500`) resolve to their base canonical entity (`26-KA-902`, `26-CX-9222`), recording the suffix as an attribute/alias without creating duplicate objects.
   - **Line Quality Filter:** Exclude spec strings lacking standard fluid service codes (`DSS-2500-DSS-EL`, `S-9003-MECHANIC`).

4. **Relationship Engine & Confidence Overhaul (`src/utils/line_tracer.py` & `src/agents/compiler.py`):**
   - Delete arbitrary fallback `MONITORS` attachments to `lines[0]` / `equipment[0]`.
   - Calculate relationship confidence from the multi-factor evidence vector (geometry, topology, semantics).
   - Enforce relationship type semantics and domain compatibility.

5. **Dual-Drawing Verification:**
   - Execute regression test across both Drawing A and Drawing B.
   - Validate that Drawing A recall remains 100%, Drawing B recall reaches $\ge 98\%$, generic duplication drops to near zero, reference contamination is eliminated, and relationship precision improves.

---

**Audit Status:** APPROVED FOR IMPLEMENTATION.
