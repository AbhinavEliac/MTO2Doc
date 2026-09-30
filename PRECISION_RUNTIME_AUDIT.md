# Precision Runtime Audit: Full Runtime Execution & Identity Flow

**Document Version:** 1.0.0  
**Target Branch:** `precision`  
**Date:** 2026-09-30  
**Repository:** `MTO2Doc` (`pid_project`)  
**Status:** Runtime Tracing Complete — Zero Speculation  

---

## Executive Summary

This document establishes the line-by-line runtime architecture audit of the MTO2Doc engineering drawing intelligence platform.
It answers all 14 mandatory audit questions specified in the Precision Architecture directive, identifying every module, class, function, state model, and lifecycle boundary across the pipeline.

The audit proves that the current system possesses **strong raw detection recall (96.15% overall recall on the ground truth P&ID)**, but suffers from **poor canonical precision (48.87% overall precision, 51.13% duplicate/false entity rate)**. The primary root cause is that raw observations and sub-component text tokens bypass a rigorous candidate evidence fusion lifecycle, directly instantiating separate physical engineering entities.

---

## 1. Complete End-to-End Runtime Execution Path

The runtime execution is orchestrated by a compiled **LangGraph** `StateGraph` defined in [`src/graph.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/graph.py#L54-L127).

```mermaid
flowchart TD
    Start([Input Drawing PDF/Image]) --> IngestNode["ingest\nIngestionAgent.run()\n(src/agents/ingestion.py)"]
    IngestNode --> ContextNode["context_loader\nContextLoaderAgent.run()\n(src/agents/context_loader.py)"]
    ContextNode --> SuperNode["supervisor\nSupervisorAgent.run()\n(src/agents/supervisor.py)"]

    SuperNode --> ForkPerception{Fork to Parallel Perception}
    ForkPerception --> TextNode["text_recognition\nTextRecognitionAgent.run()\n(src/agents/parallel_vision.py)"]
    ForkPerception --> SymbolNode["symbol_recognition\nSymbolRecognitionAgent.run()\n(src/agents/parallel_vision.py)"]
    ForkPerception --> LineNode["pipeline_recognition\nPipelineRecognitionAgent.run()\n(src/agents/parallel_vision.py)"]

    TextNode --> JoinCompiler{Join at Compiler}
    SymbolNode --> JoinCompiler
    LineNode --> JoinCompiler

    JoinCompiler --> CompNode["compiler\nCompilerAgent.run()\n(src/agents/compiler.py)"]
    CompNode --> ValidNode["validation\nValidationAgent.run()\n(src/agents/validation.py)"]
    ValidNode --> CompCheckNode["completeness\nCompletenessAgent.run()\n(src/agents/completeness.py)"]

    CompCheckNode --> RouteCond{route_completeness\n(missing & retries < 3?)}
    RouteCond -->|Yes: Target Missing| ReExtractNode["re_extractor\nReExtractorAgent.run()\n(src/agents/re_extractor.py)"]
    ReExtractNode --> CompNode
    RouteCond -->|No: Complete / Exhausted| OutGenNode["output_generator\nOutputGeneratorAgent.run()\n(src/agents/output_generator.py)"]
    OutGenNode --> Finish([Deliverables: Excel, JSON, XML, CSV])
```

---

## 2. Inventory of Runtime Artifacts

### 2.1 Modules, Classes, and Functions
| Stage / Responsibility | File / Module | Class | Runtime Function(s) |
|---|---|---|---|
| **Ingestion** | `src/agents/ingestion.py` | `IngestionAgent` | `run(state)` |
| **Context Loading** | `src/agents/context_loader.py` | `ContextLoaderAgent` | `run(state)` |
| **Supervisor & Grid Routing** | `src/agents/supervisor.py` | `SupervisorAgent` | `run(state)` |
| **Text & Tag Recognition** | `src/agents/parallel_vision.py` | `TextRecognitionAgent` | `run(state)`, `_inject_datasheet_attributes()` |
| **Vector Text Layer OCR** | `src/utils/paddle_ocr.py` | Standalone module | `run_pdf_text_extraction(pdf_path)` |
| **Raster OCR (EasyOCR / Paddle)** | `src/utils/paddle_ocr.py` | Standalone module | `_run_easyocr()`, `run_paddle_ocr()` |
| **OCR Typo Rectification** | `src/utils/tag_stitcher.py` | Standalone module | `rectify_ocr_typos(text)` |
| **Line Tag Spatial Stitching** | `src/utils/tag_stitcher.py` | Standalone module | `stitch_fragmented_tags(items)` |
| **Tag Classification & Grammar** | `src/utils/tag_classifier.py` | Standalone module | `classify_paddle_results()`, `_make_item()` |
| **Datasheet Parsing** | `src/utils/datasheet_parser.py` | Standalone module | `parse_equipment_datasheets()`, `parse_psv_set_pressures()` |
| **Symbol Recognition** | `src/agents/parallel_vision.py` | `SymbolRecognitionAgent` | `run(state)`, `_deduplicate_tiled_boxes()` |
| **Trained YOLOv8 Model** | `ultralytics.YOLO` | YOLO model class | `yolo_model.predict()` in `SymbolRecognitionAgent` |
| **Pipeline & Connectivity Recognition** | `src/agents/parallel_vision.py` | `PipelineRecognitionAgent` | `run(state)` |
| **OpenCV Line & Topology Tracer** | `src/utils/line_tracer.py` | Standalone module | `trace_lines_and_connections()` |
| **Cross-Document Provenance Filter** | `src/utils/provenance.py` | Standalone module | `filter_relationships_by_provenance()` |
| **Dual-Anchor Compiler** | `src/agents/compiler.py` | `CompilerAgent` | `run(state)`, `_compile_equipment()`, `_compile_lines()`, `_compile_instruments()`, `_compile_valves()`, `_compile_safety_relief_valves()`, `_compile_relationships()` |
| **Validation Engine** | `src/agents/validation.py` | `ValidationAgent` | `run(state)` (VAL-001 to VAL-005) |
| **Completeness Engine** | `src/agents/completeness.py` | `CompletenessAgent` | `run(state)` |
| **High-DPI Re-Extractor** | `src/agents/re_extractor.py` | `ReExtractorAgent` | `run(state)`, `_extract_from_crop()` |
| **Final Deliverables Generator** | `src/agents/output_generator.py` | `OutputGeneratorAgent` | `run(state)`, `_generate_excel()`, `_generate_aveva_xml()`, `_generate_comos_json()`, `_generate_sppid_csv()`, `_generate_relationships_csv()` |

### 2.2 State Objects, Schemas, and Pydantic Models
* **Workflow State:** `GraphState` in [`src/state.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/state.py#L26-L101)
  * `raw_documents`: `List[str]`
  * `metadata`: `Dict[str, Any]`
  * `engineering_context`: `Dict[str, Any]`
  * `extracted_entities`: `Dict[str, Any]` (`text_elements`, `symbols`, `relations`, `geometry`)
  * `engineering_graph`: `UniversalEngineeringGraph`
  * `validation_reports`: `List[Dict[str, Any]]`
  * `missing_entities`: `List[Dict[str, Any]]`
  * `re_extracted_targets`: `List[str]`
  * `ocr_token_set`: `Set[str]`
  * `deliverables`: `Dict[str, str]`
* **Precision Intermediate Models (Implemented in `src/candidate_models.py`):**
  * `ConfidenceVector`: Multi-evidence confidence breakdown (detection, ocr, symbol, classification, normalization, resolution, relationship, validation).
  * `RawObservation`: Atomic perception evidence item.
  * `EntityAttribute`: Isolated attribute attached to canonical entity.
  * `EngineeringCandidate`: Fused multi-observation candidate object.
  * `MergeProvenanceRecord`: Explainable record of candidate merging.
  * `CanonicalEntityRegistry`: Centralized registry for candidate resolution.
* **Master Canonical Graph Models (Pydantic v2 in `src/models.py`):**
  * `EquipmentItem`: Equipment tag, service, design pressure, design temperature, duty, vendor, motor details, coordinates, aliases, confidence.
  * `LineItem`: Line tag, size, service, spec, sequence_number, insulation, from_node, to_node, coordinates.
  * `InstrumentItem`: Instrument tag, type, service, location, loop_id, coordinates, aliases, confidence.
  * `ValveItem`: Valve tag, type, size, line_tag, rating, normal_state, coordinates, aliases, type_source.
  * `SafetyReliefValveItem`: PSV tag, type, service, unit, set_pressure, inlet_size, outlet_size, relief_destination, coordinates.
  * `Relationship`: Source, target, type, confidence, attributes, flag_reason.
  * `UniversalEngineeringGraph`: Top-level container aggregating all canonical entity collections.

---

## 3. The 14 Mandatory Audit Questions Answered

### 1. Where Raw OCR Observations Are Created
* **File:** [`src/utils/paddle_ocr.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/paddle_ocr.py)
* **Function:** `run_pdf_text_extraction(pdf_path)` (PyMuPDF vector text layer on original PDF) and `_run_easyocr()` / `run_paddle_ocr()` (raster OCR fallback).
* **Details:** `run_pdf_text_extraction` extracts words with coordinates `(x0, y0, x1, y1)` via `page.get_text("words")`, assembles adjacent words along lines, and performs vertical assembly for instrument bubbles. On the representative P&ID (`Lift Gas compressor-PID.pdf`), it creates **2,024 raw OCR observations**.

### 2. Where Symbol Observations Are Created
* **File:** [`src/agents/parallel_vision.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/parallel_vision.py#L605-L890)
* **Function:** `SymbolRecognitionAgent.run(state)`
* **Details:**
  1. Option A: Pathnovo ISA 5.1 API.
  2. Option B: Trained YOLOv8 model (`yolov8m.pt` / `yolo26n.pt`) with tiled 800x800 patch inference and NMS suppression (`_deduplicate_tiled_boxes`).
  3. Option C: Multimodal VLM symbol extraction.
  4. Option D: Text-based heuristic symbol harvesting fallback.
  * Also contains the untagged valve harvester (lines 843–884) which synthesizes `prefix-SYM-NN` tags (e.g. `CB-SYM-01`, `GV-SYM-02`).

### 3. Where Line Observations Are Created
* **File:** [`src/utils/line_tracer.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/line_tracer.py#L115-L250) and [`src/agents/parallel_vision.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/parallel_vision.py#L896-L1031)
* **Function:** `trace_lines_and_connections()` and `PipelineRecognitionAgent.run(state)`.
* **Details:** OpenCV morphological thinning, Hough Line transforms, and polyline run tracing generate geometric traces `geometry["traces"]`. Text-level line tags are parsed in `tag_classifier.py` via `_LINE_SEARCH` regex.

### 4. Where Candidates Are Created
* **File:** [`src/utils/tag_classifier.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py#L720-L819)
* **Function:** `classify_paddle_results()` and `_make_item()`
* **Details:** Every text token matching a regex pattern creates an entry in `found[tag] = _make_item(...)`. On the representative P&ID, **1,450 candidate items** are created from the 2,024 raw observations.

### 5. Where Candidates Become Engineering Entities
* **File:** [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py)
* **Function:**
  * `_compile_equipment`: lines 273–373
  * `_compile_lines`: lines 376–573
  * `_compile_instruments`: lines 601–738
  * `_compile_valves`: lines 741–840
  * `_compile_safety_relief_valves`: lines 843–890
* **Details:** In `CompilerAgent`, candidates are mapped directly into Pydantic model instances (`EquipmentItem`, `LineItem`, `InstrumentItem`, `ValveItem`, `SafetyReliefValveItem`).

### 6. Where Entity Classification Occurs
* **File:** [`src/utils/tag_classifier.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py) and [`src/taxonomy.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py)
* **Function:** `classify_paddle_results()` and `decompose_engineering_tag()`
* **Details:** Classification is performed via regex rules matching ISA-5.1 prefixes, project tag formats (`\d{2}-[A-Z]{2,4}-...`), valve patterns (`_VALVE_SEARCH`), equipment allowlists (`_EQUIP_PREFIX_ALLOWLIST`), and line patterns.

### 7. Where Deduplication Occurs
* **File:**
  1. `src/utils/tag_classifier.py`: Lines 821–850 (tag-level post-deduplication using `canonicalize_tag` stripping `\d{2,3}-`).
  2. `src/agents/compiler.py`:
     - Lines 275–318 in `_compile_equipment` (merges bare tags into area-prefixed tags).
     - Lines 396–410 in `_compile_lines` (merges duplicate line observations).
     - Lines 606–644 in `_compile_instruments` (canonical key deduplication).
     - Lines 747–775 in `_compile_valves` (canonical key deduplication).
  3. `src/agents/parallel_vision.py`: Lines 67–80 (`_deduplicate_tiled_boxes` using 0.45 IoU).

### 8. Where Attributes Are Created
* **File:** [`src/agents/parallel_vision.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/parallel_vision.py#L257-L396) and [`src/utils/datasheet_parser.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/datasheet_parser.py)
* **Function:** `_inject_datasheet_attributes()`
* **Details:** Injects parsed table parameters (`design_pressure`, `design_temperature`, `flow_rate`, `duty`, `material`, `vendor`, `quantity`) into `EQUIPMENT_TAG` items, and `set_pressure` into `PSV_TAG` items.

### 9. Where Relationships Are Created
* **File:** [`src/utils/line_tracer.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/line_tracer.py#L115-L250) and [`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py#L191-L225)
* **Function:** `trace_lines_and_connections()` and `CompilerAgent._compile_relationships()`
* **Details:** Evaluates component-to-line spatial proximity and loop number sequence matching. In `compiler.py`, an orphan-instrument safeguard generates synthetic `monitors` relationships if an instrument has no edges.

### 10. Where Validation Occurs
* **File:** [`src/agents/validation.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/validation.py#L13-L100)
* **Function:** `ValidationAgent.run(state)`
* **Details:** Evaluates rules:
  - `VAL-001` (ERROR): Duplicate tag detected across components.
  - `VAL-002` (ERROR): Valve size mismatch with host line.
  - `VAL-003` (WARNING): Orphan valve not associated with pipeline.
  - `VAL-004` (WARNING): Orphan instrument with no logical connection.
  - `VAL-005` (WARNING): Equipment tag format violation.

### 11. Where Re-Extraction Enters the Pipeline
* **File:** [`src/graph.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/graph.py#L34-L52), [`src/agents/completeness.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/completeness.py), [`src/agents/re_extractor.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/re_extractor.py)
* **Function:** `CompletenessAgent.run(state)` flags targets with `VAL-003`/`VAL-004`. LangGraph conditional router `route_completeness` sends state to `ReExtractorAgent.run(state)`, which crops regions and loops back to `CompilerAgent`.

### 12. Where Exports Are Created
* **File:** [`src/agents/output_generator.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/output_generator.py#L18-L81)
* **Function:**
  - `_generate_excel`: Styled OpenPyXL multi-tab workbook (`outputs/engineering_deliverables.xlsx`)
  - `_generate_aveva_xml`: Hierarchical XML for AVEVA Diagrams (`outputs/aveva_diagrams_export.xml`)
  - `_generate_comos_json`: Hierarchical JSON for COMOS (`outputs/comos_hierarchy_export.json`)
  - `_generate_sppid_csv`: Relational CSV tables (`outputs/sppid_import_tables.csv`)
  - `_generate_relationships_csv`: Edge list CSV (`outputs/relationships.csv`)

### 13. Whether Exports Receive Canonical Entities or Raw Detections
* **Finding:** Exporters consume `state["engineering_graph"]` (`UniversalEngineeringGraph`).
* **Evaluation:** Exporters **do NOT receive raw OCR strings**; they consume compiled Pydantic models. However, because `CompilerAgent` previously promoted duplicate or misclassified candidates into `engineering_graph`, the exported tables reflected poor precision (e.g. 61 instruments instead of 20, 20 equipment items instead of 7).

### 14. Which Exact Function Generated the Evaluation Output
* **Baseline Calculation Script:** [`scratch_compute_baseline.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/scratch_compute_baseline.py)
* **Functions Evaluated:**
  - `run_pdf_text_extraction` ([`src/utils/paddle_ocr.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/paddle_ocr.py#L24))
  - `classify_paddle_results` ([`src/utils/tag_classifier.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/utils/tag_classifier.py#L535))
  - `CompilerAgent._compile_equipment`, `_compile_lines`, `_compile_instruments`, `_compile_valves`, `_compile_safety_relief_valves` ([`src/agents/compiler.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/agents/compiler.py))
  - Ground truth comparison against [`pid_stuff/PID_Extraction_RevB_Corrected_26-KA-901_902 (2).xlsx`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/pid_stuff/PID_Extraction_RevB_Corrected_26-KA-901_902%20(2).xlsx)

---

## 4. Current Entity Lifecycle

```
[PDF / Image Page]
       │
       ▼  (PyMuPDF / EasyOCR)
RAW OBSERVATION  (2,024 items: text tokens with bboxes, confidences, coordinates)
       │
       ▼  (tag_classifier.py regex scanners: _PROJECT_TAG_SEARCH, _LINE_SEARCH, etc.)
ENGINEERING CANDIDATE  (1,450 items: raw OCR matched to classes or generic NOTE)
       │
       ▼  (CompilerAgent._compile_* without cross-anchor fusion ledger)
CANONICAL ENTITY  (221 items: instantiated directly into Pydantic models)
       │
       ▼  (ValidationAgent & CompletenessAgent)
VALIDATION REPORTS  (VAL-001 to VAL-005)
       │
       ▼  (OutputGeneratorAgent)
CLIENT DELIVERABLES  (Excel, JSON, XML, CSV with 221 entities vs 104 ground truth)
```

---

## 5. Root Causes of Precision Failure

1. **OCR Observations Directly Becoming Canonical Entities:**
   Any token matching a regex pattern is promoted directly into a model. Suffix variations (`26-PDI-9054` vs `26-PDI-9054-HH`) generate two distinct instruments.
2. **Control Valves Conflated with Instruments:**
   Tags like `26-FV-9076` or `40-XV-9010` were historically placed into `graph.instruments` by text rules while simultaneously being detected by symbol recognition as valves, manufacturing duplicates.
3. **Line Fragments and Specs Promoted to Lines:**
   Line tags repeated across continuous piping runs or standalone spec fragments were instantiated as independent `LineItem` records (66 compiled vs 35 ground truth).
4. **Sub-components and Package Boundaries Creating False Equipment:**
   Equipment descriptions, skid labels, and repeat occurrences (`KA-901`, `26-KA-901`, sub-assembly callouts) generated 20 equipment items for 7 ground truth pieces.
5. **No Intermediate Evidence Ledger:**
   The compiler lacked an authoritative centralized `CanonicalEntityRegistry` to fuse multi-pass evidence before constructing the engineering graph.
