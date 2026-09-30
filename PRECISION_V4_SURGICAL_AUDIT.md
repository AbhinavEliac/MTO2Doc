# PRECISION V4 SURGICAL AUDIT
**System:** MTO2Doc / SID-AI Universal Engineering Graph  
**Branch:** `precision`  
**Phase:** Precision Stabilization v4 — Surgical Entity-Boundary Repair  
**Target Regression Fixtures:**  
- Drawing A: `26-KA-901` (3rd Stage HP Gas Lift Compressor)
- Drawing B: `26-KA-902` (3rd Stage HP Gas Export Compressor, PID(9))
- Drawing C: `26-KA-902` (3rd Stage HP Gas Export Compressor, PID(10))

---

## 1. Current Runtime Architecture
The authoritative MTO2Doc processing pipeline runs in strict sequence:
```
IngestionAgent (PDF / raster load)
      ↓
Supervisor / GridRouter (Metadata & layout segmentation)
      ↓
ParallelVision (TextRecognitionAgent [PaddleOCR + TypoRectifier]
                + SymbolRecognitionAgent [YOLO ISA-5.1]
                + PipelineRecognitionAgent [LineTracer])
      ↓
Dual-Anchor Universal Engineering Object Compiler (CompilerAgent)
      ↓
ValidationAgent (VAL-005 consistency & deterministic gates)
      ↓
CompletenessChecker (Targeted re-extraction router)
      ↓
OutputGenerator (Excel, Master JSON Graph, AVEVA XML, COMOS JSON, SPPID CSV)
```

No downstream exporter performs entity reasoning, dataframe mutations, or row deletions. The `CompilerAgent` produces the authoritative `UniversalEngineeringGraph`.

---

## 2. Current Candidate Lifecycle
1. **Raw OCR Observations:** Extracted as `text`, `confidence`, `bbox`, `center_x`, `center_y`.
2. **Pre-Stitching:** `stitch_fragmented_tags` cleans OCR typos, stitches size-to-core line fragments, split valve prefixes, and symbol bubbles (`stitch_symbol_bubbles`).
3. **Classification Pass (`classify_paddle_results`):** Evaluates regexes for PSV, LINE, INSTRUMENT, VALVE, EQUIPMENT, ELECTRICAL, and NOTE.
4. **Candidate Post-Deduplication Pass:** Merges observation variants sharing canonical keys with priority scoring (`_tag_priority_score`) and preserves aliases, alarms, and provenance.
5. **Compiler Ingestion:** `CompilerAgent` consumes classified candidates and compiles canonical domain items.

---

## 3. Current Entity Lifecycle & Separation
The universal graph separates items into distinct collections:
- `graph.equipment: List[EquipmentItem]`
- `graph.lines: List[LineItem]`
- `graph.instruments: List[InstrumentItem]`
- `graph.valves: List[ValveItem]`
- `graph.safety_relief_valves: List[SafetyReliefValveItem]`
- `graph.references: List[ReferenceItem]`
- `graph.generic_components: List[GenericComponentItem]`
- `graph.annotations: List[AnnotationItem]`
- `graph.relationships: List[Relationship]`

---

## 4. Problem Audits & Exact Root Causes

### A. Reference vs. Note / Annotation Contamination
* **Problem:** Ordinary drawing notes containing the word `TO` or `FROM` (e.g. `BE FINALIZED BY PIPING AS PER PIPING`, `START-UP. PUSH BUTTON WITH PERMISSIVE TO START`, `SAFE LOCATION`, `AVOID DAMAGE DUE TO`, `BE TAKEN INTO CONSIDERATION ON TW SELECTION`, `SEAL GAS SYSTEM RUPTURE DISCS`, `PDIT FOR PRIMARY SEAL GAS`) were promoted to `ReferenceItem`.
* **Runtime Path:** `compiler.py` $\rightarrow$ `_compile_references(texts)`.
* **Root Cause:** Line 1473 contained an open fallback:
  ```python
  m_sub = re.search(r'((?:\d{2}-)?[A-Z]{2,4}-\d{3,5}[A-Z]?)', captured)
  if m_sub:
      ref_tag = m_sub.group(1)
  else:
      ref_tag = captured.split('\n')[0].strip()  # <-- PROMOTES ARBITRARY SENTENCES
  ```
  Any text following `TO` or `FROM` was converted into a `ReferenceItem` even if it contained no engineering reference tag or recognized plant boundary destination.
* **Correction:** Restrict reference promotion so that `captured` text MUST resolve to:
  1. An engineering tag (`r'((?:\d{2}-)?[A-Z]{2,4}-\d{3,5}[A-Z]?)'`), OR
  2. A recognized process continuation sink/source header (`HP FLARE`, `LP FLARE`, `CLOSED DRAIN`, `OPEN DRAIN`, `HAZ. OPEN DRAIN`, `ATMOSPHERE`, `SUCTION SCRUBBER`, `INLET HEADER`, `DISCHARGE HEADER`), OR
  3. A continuation drawing reference number (`r'\b(?:\d{2}-)?\d{6}-\d{3}\b'`).
  If no engineering tag, header, or drawing reference is present, the item remains a `NOTE` / `ANNOTATION`.

---

### B. Reference vs. Local Physical Entity Resolution
* **Problem:** External off-sheet instrument and equipment references (`FROM 27-PIT-0001B`, `FROM 26-PIT-9087`, `FROM 26-PIT-9077`) risk becoming local physical equipment or instruments.
* **Runtime Path:** `tag_classifier.py` $\rightarrow$ `compiler.py` (`_compile_equipment`, `_compile_instruments`).
* **Root Cause:** In `_compile_instruments` and `_compile_equipment`, reference tags were checked against `ref_keys`. However, suffix variants like `26-PIT-9087-GAS` or `26-PIT-9077-GAS-HP` had their suffixes stripped *after* the reference check, allowing them to evade the filter.
* **Correction:** Suffix cleaning occurs *before* reference key matching. An item is marked as an external reference only when it is explicitly a `FROM`/`TO` continuation AND lacks a local symbol/bubble on the current drawing.

---

### C. Local Instrument Recall
* **Problem:** Instrument recall must be protected so that legitimate local instruments with graphical bubbles or tag grammar (`PIT`, `PI`, `PDIT`, `PDI`, `TIT`, `TI`, `FE`, `FI`, `PY`) are never erroneously suppressed by reference filters.
* **Runtime Path:** `compiler.py` $\rightarrow$ `_compile_instruments`.
* **Root Cause:** Over-broad reference keywords (such as `VENDOR`, `BY PIPING`, `HEADER`) in regexes previously matched notes that mentioned local instruments (e.g. `26-TIT-9211, SUCTION PRESSURE 26-PIT-9055...`), causing real local transmitters to be misflagged as references.
* **Correction:** Strictly limit reference pre-scanning to direct flow continuations (`^\s*(?:FROM|TO)\s+`). If an object exists as a local symbol bubble or standalone tag on the drawing, local graphical evidence overrides note mentions.

---

### D. Malformed Line Candidate Promotion
* **Problem:** Non-line text strings (such as `CX-9122`, `G-150`, `A-26-9122-AC21-00`, `A-2500-26BL9073-4`, `B-300-2500`, `PSI-9758-HH`) were promoted to `LineItem`.
* **Runtime Path:** `tag_classifier.py` (`_LINE_SEARCH`) $\rightarrow$ `compiler.py` (`_compile_lines`).
* **Root Cause:** 
  1. `_LINE_SEARCH` branch 2 allowed single-letter service codes (`[A-Z]{1,4}`) without pipe size, matching rating strings (`A-2500-...`, `B-300-...`) and pressure units (`PSI-9758-...`).
  2. `_validate_line_tag_size` skipped validation if no size prefix was present (`if not re.match(r'^[\d/]', p0): return True, None`), allowing single-letter and rating tokens to pass as lines.
  3. `_compile_lines` accepted single-letter services (`^[A-Z]{1,4}$`) and pure numeric specs (`2500`, `300`), valve specs (`26BL9073`), and alarms (`HH`).
* **Correction:**
  1. Require that line tags without size prefixes have a standard multi-letter service code ($\ge 2$ characters, e.g. `PV`, `VA`, `WF`, `FG`, `IA`, `DR`, `FL`, `PL`, `BD`, `VD`), rejecting single letters (`A`, `B`, `G`).
  2. Reject pressure units (`PSI`, `BAR`, `KPA`) and equipment codes (`CX`, `KA`, `HA`, `TK`, `FA`, `PU`, `PA`, `KO`, `CK`, `ST`) as line service codes.
  3. Reject numeric specs (`2500`, `300`, `150`), valve codes (`BL`, `GB`, `GT`, `CB`, `CK`, `NV`), and alarm indicators (`HH`, `LL`, `SD`) from being line specification classes.

---

### E. Cross-Type Duplicate Entity Resolution
* **Problem:** `26-CK-921` (Suction Strainer) appeared as both `EQUIPMENT` and `VALVE`.
* **Runtime Path:** `compiler.py` $\rightarrow$ `_compile_valves`.
* **Root Cause:** Line 873 in `_compile_valves` had a hardcoded check for `CK-911` (`if tag_upper in ('CK-911', '26-CK-911')`), failing to reject `CK-921` or any other 3-digit suction strainer.
* **Correction:**
  1. In `_compile_valves`, check `re.match(r'^(?:26-)?CK-\d{3}\b', tag_upper)` to reject all suction strainers from the valve registry.
  2. Maintain a cross-type registration check: any tag already registered in `equipment` is excluded from `valves`.

---

### F. Generic Component Residual Leakage
* **Problem:** Residual duplicate entries in generic components.
* **Runtime Path:** `compiler.py` $\rightarrow$ `_compile_generic`.
* **Root Cause:** Previously ingested `EQUIPMENT_TAG` and lacked full alias matching.
* **Correction:** Retain strict restriction to `GENERIC_TAG` only, with lookup against `tag_alias_map` and base tags. Only true unknown candidates with no physical resolution remain generic.

---

## 5. File Modification Budget

### Files to be Modified:
1. `src/agents/compiler.py`:
   - `_compile_references`: Enforce strict target resolution (engineering tag, boundary sink/source, or drawing number); demote non-engineering phrases to annotations/notes.
   - `_compile_lines`: Enforce line grammar (multi-letter service if no size, reject equipment/pressure-unit services, reject numeric/valve/alarm specs).
   - `_compile_valves`: Reject all suction strainers (`CK-\d{3}`) and check against compiled equipment tags.
   - `_compile_instruments`: Clean suffixes before reference check; preserve local graphical instruments.
2. `src/utils/tag_classifier.py`:
   - `_validate_line_tag_size` / line candidate filtering: Reject single-letter non-sized tokens, pressure units, and equipment codes from `LINE_TAG`.

### Files Explicitly Protected (DO NOT MODIFY):
- EasyOCR & PaddleOCR configuration (`src/utils/paddle_ocr.py`)
- YOLO model & weights
- Ray-casting line tracing algorithm (`src/utils/line_tracer.py`)
- Relationship topology engine (`CONNECTED_TO`, `INSTALLED_ON`, `MEASURES`)
- Core workflow state graph (`src/graph.py`, `src/state.py`)
- All deliverable exporter formats (`src/agents/output_generator.py`)
- Streamlit UI (`app.py`)
