# AUDIT_BEFORE_REPAIR.md
**Project:** SID-AI / P&ID Engineering Intelligence Extraction System  
**Test Case:** Export Gas Compressor P&ID (`uploads/Export Gas Compressor-PID.pdf`)  
**Target Unit / Equipment:** `26-KA-902` (3rd Stage HP Gas Export Compressor)  
**Date:** September 2026  
**Auditor:** Senior Computer Vision + OCR + P&ID Engineering Intelligence Architect  

---

## 1. Architecture Map

```
                    ┌────────────────────────────────────────┐
                    │  Input Document: PDF / High-Res Image   │
                    └───────────────────┬────────────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │     Ingestion Agent     │
                           │  (PyMuPDF 300 DPI PNG)  │
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │   Context Loader Agent  │
                           │ (Drawing Type Detection)│
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │    Supervisor Agent     │
                           └────────────┬────────────┘
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            │                           │                           │
            ▼                           ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│ Text Recognition Agent│   │Symbol Recognition Agt │   │Pipeline Recognit. Agt │
│ - EasyOCR / PaddleOCR │   │ - Heuristic / YOLO /  │   │ - Skeleton / Hough    │
│ - Tag Stitcher        │   │   DETR Bounding Boxes │   │   Line Traces         │
│ - Tag Classifier      │   └───────────┬───────────┘   └───────────┬───────────┘
│ - Datasheet Parser    │               │                           │
└───────────┬───────────┘               │                           │
            │                           │                           │
            └───────────────────────────┼───────────────────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │     Compiler Agent      │
                           │ - Entity Compilation    │
                           │ - Spatial Line Tracer   │
                           │ - Naive Proximity Rels  │
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │    Validation Agent     │
                           │  (Rules VAL-001 - 005)  │
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │   Completeness Agent    │
                           └────────────┬────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │ (if missing entities & count < max_retries) │ (else)
                 ▼                                             ▼
     ┌───────────────────────┐                     ┌───────────────────────┐
     │  Re-Extractor Agent   │                     │Output Generator Agent │
     │  (Focused Crop Loop)  │                     │ - Excel Deliverable   │
     └───────────┬───────────┘                     │ - master_graph.json   │
                 │                                 │ - relationships.csv   │
                 └──────► (loop to Compiler)       │ - SPPID / AVEVA /     │
                                                   │   COMOS exports       │
                                                   └───────────────────────┘
```

---

## 2. Pipeline Execution Flow

1. **Ingestion & Preprocessing (`src/agents/ingestion.py`, `src/utils/preprocess.py`):**
   - Ingests `uploads/Export Gas Compressor-PID.pdf`.
   - Uses PyMuPDF (`fitz`) to rasterize page 0 at 300 DPI (`zoom = 300/72 ≈ 4.166`) into `uploads/rasterized/page_1.png`.
   - Generates contrast-enhanced, grayscale, and binarized variants for OCR if needed.

2. **Context Loading & Drawing Classification (`src/agents/context_loader.py`, `src/utils/drawing_type_detector.py`):**
   - Scans title block tokens and layout patterns.
   - Correctly identifies `drawing_type = "PID"` and `discipline = "Process"`.

3. **Perception Layer (`src/agents/parallel_vision.py`):**
   - **Text Recognition:**
     - Runs OCR (EasyOCR / PaddleOCR / Gemini).
     - Passes raw OCR items to `src/utils/tag_stitcher.py` (`rectify_ocr_typos`, `stitch_fragmented_tags`, `stitch_symbol_bubbles`).
     - Passes stitched items to `src/utils/tag_classifier.py` (`classify_paddle_results`).
     - Injects structured datasheet attributes and PSV set pressures via `src/utils/datasheet_parser.py`.
   - **Symbol Recognition:**
     - Detects symbol bounding boxes, type, and coordinates.
   - **Pipeline Recognition:**
     - Computes morphology and Hough line segments for piping routes.

4. **Object Compilation (`src/agents/compiler.py`):**
   - Calls `trace_lines_and_connections` in `src/utils/line_tracer.py`.
   - Compiles entities:
     - `_compile_equipment`: Filters items where `classification == "EQUIPMENT_TAG"`.
     - `_compile_lines`: Filters `LINE_TAG` items, checks service code, associates polyline traces.
     - `_compile_instruments`: Filters `INSTRUMENT_TAG` items, extracts loop numbers, infers service.
     - `_compile_valves`: Filters `VALVE_TAG` items, matches to host line.
     - `_compile_safety_relief_valves`: Compiles PSV items.
     - `_compile_relationships`: Merges proximity links from `line_tracer.py`.
     - **Forced Zero-Orphan Instruments:** If any instrument has no relationship, hooks it to `lines[0]` or `equipment[0]` with confidence `0.85`.

5. **Validation & Completeness (`src/agents/validation.py`, `src/agents/completeness.py`):**
   - Checks duplicate tags, valve-to-line size consistency, orphan entities, equipment naming convention.

6. **Output Generation (`src/agents/output_generator.py`):**
   - Emits `outputs/engineering_deliverables.xlsx`, `outputs/master_graph.json`, `outputs/relationships.csv`, `outputs/sppid_import_tables.csv`, `outputs/aveva_diagrams_export.xml`, `outputs/comos_hierarchy_export.json`.

---

## 3. Current Modules

| Module Path | Primary Responsibility | Current Health |
|---|---|---|
| `main.py` | CLI Entry point for full LangGraph pipeline | Working |
| `app.py` | Streamlit interactive UI | Working |
| `src/graph.py` | StateGraph node/edge definition and conditional routing | Working |
| `src/state.py` | GraphState TypedDict definition | Working |
| `src/models.py` | UniversalEngineeringGraph, EquipmentItem, LineItem, InstrumentItem, ValveItem, SafetyReliefValveItem, Relationship | Needs Extension (Validation fields, evidence, candidate states) |
| `src/agents/ingestion.py` | PDF rasterization and image loading | Working well |
| `src/agents/context_loader.py` | Drawing type and discipline identification | Working well |
| `src/agents/parallel_vision.py` | Perception agent orchestration & attribute injection | Needs Refinement (PSV attribute mapping) |
| `src/agents/compiler.py` | Merges entities into graph models | **CRITICAL DEFECTS** (Equipment over-extraction, orphan hookup, confidence defaults) |
| `src/agents/validation.py` | Engineering consistency rules | Working (Can add more engineering rules) |
| `src/agents/output_generator.py`| Excel, CSV, JSON export generation | Working (Needs review queue & validation columns) |
| `src/utils/tag_classifier.py` | Scans text for equipment, lines, instruments, valves | **CRITICAL DEFECTS** (Matches line specs as equipment, false lines, loose regexes) |
| `src/utils/tag_stitcher.py` | Stitches OCR tokens & multi-line symbol bubbles | **CRITICAL DEFECTS** (`stitch_symbol_bubbles` causes tag concatenations) |
| `src/utils/datasheet_parser.py`| Parses equipment datasheets & PSV blocks | **CRITICAL DEFECTS** (PSV flange regex misses decimals `1.5"`, destination fallback) |
| `src/utils/line_tracer.py` | CV Hough line extraction & spatial proximity relationships | **CRITICAL DEFECTS** (Excessive search radii 0.45, blind proximity snapping, 1.0 confidence) |

---

## 4. Current Entity Schemas

From `src/models.py`:
- **EquipmentItem:** `tag`, `name`, `type`, `description`, `design_pressure`, `design_temperature`, `flow_rate`, `duty`, `material`, `vendor`, `quantity`, `location`, `coordinates`, `aliases`, `confidence`.
- **LineItem:** `tag`, `size`, `service`, `spec`, `sequence_number`, `insulation`, `from_node`, `to_node`, `coordinates`.
- **InstrumentItem:** `tag`, `type`, `service`, `location`, `loop_id`, `coordinates`, `aliases`, `confidence`, `flag_reason`.
- **ValveItem:** `tag`, `type`, `size`, `line_tag`, `rating`, `normal_state`, `coordinates`, `aliases`, `type_source`, `confidence`.
- **SafetyReliefValveItem:** `tag`, `type`, `service`, `unit`, `set_pressure`, `inlet_size`, `outlet_size`, `inlet_spec`, `relief_destination`, `remarks`, `coordinates`.
- **AnnotationItem:** `text`, `annotation_type`, `position_x`, `position_y`.

*Missing Schema Capabilities:*
- No candidate tracking (`EntityCandidate` with `candidate`, `validated`, `duplicate`, `rejected`, `needs_review`).
- No multi-factor confidence decomposition (`ocr_confidence`, `grammar_confidence`, `symbol_confidence`, `spatial_confidence`, `semantic_confidence`).
- No instrument loop decomposition (separating primary transmitter, indicator, controller, alarms `HH`/`LL`, and setpoints).

---

## 5. Current Relationship Schemas

- **Relationship Model (`src/models.py`):**
  - `source: str`
  - `target: str`
  - `type: str` (`connects_to`, `installed_on`, `monitors`, `relieves_to`, `feeds`, etc.)
  - `confidence: float = 1.0`
  - `attributes: Optional[Dict[str, Any]] = None`
  - `flag_reason: Optional[str] = None`

*Current Defect in Relationship Logic:*
- Universal `confidence = 1.0` is hardcoded regardless of evidence.
- No evidence tracking (ray intersection, terminal connection, tap connection, loop match vs pure proximity).
- No topological validation against engineering sanity rules.

---

## 6. Current OCR Pipeline

1. **Rasterization:** PyMuPDF renders PDF to PNG at 300 DPI.
2. **Detection & Recognition:** EasyOCR / PaddleOCR extracts bounding boxes, text, confidence.
3. **Typo Rectification (`rectify_ocr_typos`):** Cleans common character substitutions (e.g. `B"` -> `8"`).
4. **Tag Stitching (`stitch_fragmented_tags`):**
   - Merges size prefixes (`8"` + `PV-26-9035` -> `8"-PV-26-9035`).
   - Merges valve prefixes (`26-GB` + `9178` -> `26-GB-9178`).
   - **Flawed Module (`stitch_symbol_bubbles`):** Vertically matches any tokens within `dx <= 0.015` and joins them with hyphens, inadvertently gluing table rows, instrument notes, and alarm callouts into malformed tags.
5. **Tag Classification (`classify_paddle_results`):**
   - Applies regex scanning across items.
   - Flawed equipment and line regexes absorb false strings.

---

## 7. Current Confidence Logic

- **Equipment:**
  - `confidence = round(0.60 + 0.40 * (populated_count / 7.0), 2)` if datasheet values are populated; otherwise defaults to `0.60`.
  - False equipment like `KA-902-STAGE` receives `0.66` purely because table headers matched datasheet keywords!
- **Instruments:**
  - Hardcoded default `1.0` or `min(conf, 0.85)`.
- **Valves:**
  - Hardcoded default `1.0`.
- **Relationships:**
  - Hardcoded `1.0` across 166 edges in `line_tracer.py` and `compiler.py`.
- **Overall:** No mathematical multi-factor calibration exists.

---

## 8. Current Failure Points (Baseline Audit on Export Gas Compressor P&ID)

### A. False Equipment Entities (18 reported vs ~5 genuine)
- Genuine Equipment:
  1. `26-KA-902` (Compressor)
  2. `26-CX-9021` (Coalescing Filter Separator)
  3. `26-CX-9222` (Coalescing Filter Separator)
  4. `26-KZ-902` (Compressor Package Skid)
  5. `26-KA-902-M01` (Motor / Driver)
- False Equipment Extracted:
  - `VA-26-9110-AS20S-00`, `VA-26-9111-AS20S-00`, `VA-26-9114-AC21-00`, `VA-26-9112-AC21-00`, `VA-26-9113-AC21-00`: These are process lines (`VA` = Vent to Atmosphere)! Because `VA` is in `_EQUIP_PREFIX_ALLOWLIST`, they became Vessel equipment.
  - `STAGE-26-000001-001-26-PIT-9087`: OCR concatenation of drawing reference, stage note, and instrument tag.
  - `KA-902-STAGE`: Table column header from compressor datasheet table.
  - `U-9017-PDIT-9017`: Unit reference glued to instrument tag.
  - `M-26-KA-902-M01`: Duplicate prefixed variant of motor driver `26-KA-902-M01`.
  - `CX-9021-2`: Fragment of `26-CX-9021` with line size.
  - `KA-902-GAS`: Concatenation of compressor tag and gas service word.
  - `P-26-TIT-9024`: Package/Pump letter attached to temperature transmitter tag.

### B. Instrument Duplication & Noise (47 reported, ~20 real physical loops)
- Duplicate Loop Representations:
  - Loop 9026: `PIT-9026`, `PI-9026`, `PIT-9026-TIT`, `PI-9026-L`, `PIT-9026-26` (5 separate entities for 1 physical loop).
  - Loop 9015: `26-PDI-9015`, `19-PDIT-9015`, `PDIT-9015-PDI`, `PDIT-9015-HH`, `PDI-9015-LUBE`.
  - Loop 9016: `PIT-9016`, `PI-9016`, `PI-9016-PIT`, `PI-9016-L`.
  - Loop 9018: `TI-9018`, `TIT-9018-TIT`.
  - Loop 9025: `TIT-9025`, `TI-9025`, `TI-9025-TIT`.
  - Non-instruments: `46-LTCS-1X100` (Material & configuration from compressor datasheet table extracted as instrument), `FE-9017-NOTE` (`FE-9017` + `NOTE 1` note callout), `OMS-26-CX` (Oil mist separator reference), `AT-4` (Table note fragment).

### C. False Line Entities (43 reported, contains 9 false strings)
- False Lines:
  - `RD-1835-62809-199-77` (Compressor datasheet columns: Rated Duty 1835 kW, Flow 62809 kg/h, 199 Barg, 77 °C).
  - `PDIT-9015-HH-H` (Instrument tag + High-High alarm setpoints).
  - `PI-9019-LL-3` (Instrument tag + Low-Low alarm setpoint).
  - `FE-9017-31-FC11S` (Flow orifice + note callout + spec code).
  - `CK-921-OMSMODUL` (Check valve + Oil Mist Separator module reference).
  - `PI-9023-LL` (Instrument tag + Low-Low alarm).
  - `TI-90239025` (Concatenation of two adjacent temperature indicator loop numbers).
  - `DSS-2500-DSS-EL` (Piping spec / electrical reference).
  - `S-9003-MECHANIC` (Suction strainer / mechanical seal reference).

### D. PSV Extraction Deficiencies
- Duplicate tag `-PSV-9027A` created due to leading hyphen match in `_PSV_SEARCH`.
- Outlet size misparsed: `4" x 1.5"` parsed as `4"` inlet and `1"` outlet because `\d+(?:/\d+)?` in `_FLANGE_SPEC_RE` does not support decimal fractions (`1.5`).
- Relief destination defaulted to `LP Flare Header` instead of tracing to `TO HP FLARE`.

### E. Relationship Engine & Confidence Calibration
- 166 relationships generated.
- Universal `confidence = 1.0` applied to all relationships.
- Excessive proximity threshold (`max_dist = 0.45`), causing distant valves and instruments to connect to unrelated lines and bogus equipment.
- Fallback in `CompilerAgent.run` arbitrarily connects unassociated instruments to `graph.lines[0]` or `graph.equipment[0]`.

---

## 9. Modules Already Working Well (DO NOT DESTROY)

1. **Compressor Datasheet Block Extraction (`src/utils/datasheet_parser.py`):**
   - Successfully extracts `26-KA-902` attributes with 98–99% precision:
     - 1835 kW
     - 62809 kg/h
     - 199 / 108.5 Barg
     - 77–109 / 50 °C
     - FV / 286 / FV / 286 Barg
     - -46 / 160 / -46 / 160 °C
     - LTCS (1.7218)
     - 1x100%
     - MAN ENERGY SOLUTIONS
2. **Valve Detection & Tag Extraction (`src/utils/tag_classifier.py`):**
   - Correctly detects 50+ genuine valves with 98–99% accuracy (e.g. `26GT9128`, `43BL9054`, `26BL9031`, `26GT9132`, `26BL9032`, `26GT9133`, `43BL9008`, `43BL9009`, `43GT9052`, `26BL9033`, `26CB9119`–`9124`, `26CB9131`, `26GB9129`, `26CB9811`, `26GB9035`, `26CB9812`, `26CB9130`).
3. **Genuine Piping Line Extraction:**
   - Real process lines (e.g. `4"-PV-26-9020-FC11S-38`, `6"-PV-26-9017-FC11S-38`, `8"-PV-26-9007-FC11S-08`, `2"-PL-26-9115-FC11S-00`, `10"-VF-43-9007-AS20S-00`, `12MM-PV-26-9116-FD70X-00`) are extracted accurately.
4. **Export Infrastructure (`src/agents/output_generator.py`):**
   - Clean generation of Excel, XML, JSON, and CSV exports.

---

## 10. Modules Needing Modification

1. **`src/utils/entity_validator.py` (NEW MODULE - Phase 1 & 2):**
   - Implement `EntityCandidate` dataclass with status enum (`candidate`, `validated`, `duplicate`, `rejected`, `needs_review`).
   - Implement generalized tag grammars for lines, valves, instruments, equipment, PSVs.
   - Keep rejected candidates for auditing.
2. **`src/utils/tag_stitcher.py` (Phase 7):**
   - Constrain `stitch_symbol_bubbles` to avoid blindly concatenating table columns (`RD-1835-...`), note markers (`FE-9017-NOTE`), and alarm setpoints (`PDIT-9015-HH`).
   - Retain raw tokens and add coherent `AnnotationRegion` groupings.
3. **`src/utils/tag_classifier.py` (Phase 2, 4, 5):**
   - Restrict `_GENERIC_EQUIP_PATTERN` and `_EQUIP_PREFIX_ALLOWLIST` so line tags (e.g. `VA-26-...`) and concatenated strings do not become equipment.
   - Refine `_LINE_SEARCH` to require valid pipe size or genuine piping service/spec grammar, rejecting datasheet duty blocks, alarm tokens, and notes.
   - Normalize PSV tags to strip leading hyphens (`-PSV-9027A` -> `PSV-9027A`).
4. **`src/utils/datasheet_parser.py` (Phase 6):**
   - Update `_FLANGE_SPEC_RE` to support decimal fractions (e.g. `1.5"` or `1-1/2"`), correctly extracting `4" x 1.5"`.
   - Implement spatial/connectivity resolution for PSV discharge to `TO HP FLARE`.
5. **`src/agents/compiler.py` (Phase 3, 4, 5, 10, 12):**
   - Integrate `EntityCandidate` validation layer.
   - Refactor `_compile_equipment` to strictly require equipment grammar, symbol evidence, or structured datasheet table association.
   - Refactor `_compile_instruments` to resolve primary sensor, indicator, transmitter, and alarm attributes into single canonical loops.
   - Remove blind orphan instrument hookup.
6. **`src/utils/line_tracer.py` (Phase 9, 10, 11, 12):**
   - Reduce excessive search radii.
   - Replace naive proximity with geometric line intersection, tap verification, and nozzle tracing.
   - Implement engineering rules (Rules 1–10).
   - Implement multi-factor confidence calculation (OCR, grammar, symbol, geometry, topology).
7. **`src/agents/output_generator.py` (Phase 13, 14):**
   - Add validation status, review queue, and evidence traceability columns in Excel/CSV outputs.

---

## 11. Recommended Repair Order

1. **Step 1:** Establish Ground-Truth Test Set & Automated Evaluation Harness (`tests/test_export_compressor_ground_truth.py`).
2. **Step 2:** Build Entity Validation & Tag Grammar Layer (`src/utils/entity_validator.py`).
3. **Step 3:** Repair Tag Stitching & Annotation Grouping (`src/utils/tag_stitcher.py`).
4. **Step 4:** Repair Tag Classification & Spec Rejection (`src/utils/tag_classifier.py`).
5. **Step 5:** Repair Equipment Validation & Deduplication (`src/agents/compiler.py`).
6. **Step 6:** Repair Instrumentation Resolver & Loop Normalization (`src/utils/instrument_resolver.py`, `src/agents/compiler.py`).
7. **Step 7:** Repair PSV Resolution & Flange Specs (`src/utils/datasheet_parser.py`, `src/agents/compiler.py`).
8. **Step 8:** Geometry & Engineering Relationship Engine Rewrite (`src/utils/line_tracer.py`, `src/agents/compiler.py`).
9. **Step 9:** Multi-Factor Calibrated Confidence Engine & Review Queue (`src/agents/compiler.py`, `src/agents/output_generator.py`).
10. **Step 10:** End-to-end Pipeline Verification on Export Gas Compressor P&ID & Regression Testing.
11. **Step 11:** Generate `FINAL_REPAIR_REPORT.md`.
