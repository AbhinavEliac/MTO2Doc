# Precision Classification Report & Engineering Taxonomy

**Document Version:** 1.0.0  
**Phase:** Phase 3 Implementation  
**Status:** Completed & Tested (99/99 Tests Passing)  

---

## 1. Universal Engineering Entity Taxonomy

The engineering taxonomy implemented in [`src/taxonomy.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L30) categorizes all physical and logical drawing components according to ISA 5.1, ISO 15926, and CFIHOS:

### Taxonomy Breakdown

```
UniversalEngineeringTaxonomy
│
├── PIPING & TRANSPORT
│   ├── LINE
│   └── PIPELINE
│
├── VALVES (Physical In-Line Mechanical Devices)
│   ├── VALVE (Manual In-line)
│   ├── CONTROL_VALVE (Actuated / In-line Control)
│   ├── CHECK_VALVE (Non-Return)
│   ├── BALL_VALVE (Quarter-Turn)
│   ├── GATE_VALVE (Isolation)
│   ├── GLOBE_VALVE (Throttling)
│   ├── BUTTERFLY_VALVE (Quarter-Turn Disk)
│   ├── NEEDLE_VALVE (Fine Control)
│   ├── PLUG_VALVE (Quarter-Turn Plug)
│   ├── RELIEF_VALVE (Pressure Relief)
│   ├── SAFETY_VALVE (Safety Relief)
│   └── PSV (Pressure Safety Valve)
│
├── INSTRUMENTS (Physical Sensors & Bubbles)
│   ├── PRESSURE_INSTRUMENT (PIT, PDT, PT, PI, PDI)
│   ├── TEMPERATURE_INSTRUMENT (TIT, TDT, TT, TI, TE, TW)
│   ├── FLOW_INSTRUMENT (FIT, FT, FI, FE, FO)
│   ├── LEVEL_INSTRUMENT (LIT, LT, LI, LG)
│   ├── ANALYZER (AIT, AT, AI)
│   ├── VIBRATION_INSTRUMENT (VIT, VT, VI)
│   └── POSITION_INSTRUMENT (ZIT, ZT, ZI)
│
├── LOGICAL / CONTROL FUNCTIONS (Not Standalone Physical Devices)
│   ├── CONTROL_FUNCTION (e.g. Anti-Surge, ESD)
│   ├── TRANSMITTER (Transmitting Loop Function)
│   ├── INDICATOR (Display / Dial Readout)
│   ├── SWITCH (State Trip: PSH, PSL, TSH, TSL)
│   ├── CONTROLLER (Feedback Loop: PIC, TIC, FIC)
│   ├── ELEMENT (Primary Sensor Element: TE, FE)
│   └── SAFETY_INTERLOCK (Trip Logic Function)
│
├── EQUIPMENT (Process & Mechanical Machinery)
│   ├── COMPRESSOR (Centrifugal, Reciprocating, Blower: KA, KB, CP, CM)
│   ├── PUMP (Centrifugal, Positive Displacement: PA, PB, GA, GB)
│   ├── VESSEL (Separator, Drum, Column: VA, VB, DA, DB, KO)
│   ├── TANK (Storage Tank: TK, TA)
│   ├── HEAT_EXCHANGER (Shell & Tube, Plate: HA, HB, HX, HE)
│   ├── COOLER (Air Cooler, Aftercooler: EA, EB)
│   ├── FILTER (Cartridge, Coalescer: FA, FB, FC, FL)
│   ├── SEPARATOR (Scrubber, Coalescing Filter: SA, SB, SC, CX)
│   ├── STRAINER (Suction / Line Strainer: ST)
│   ├── COLUMN (Distillation, Absorption: CA, CB)
│   ├── REACTOR (Process Reactor: R)
│   ├── MOTOR (Electrical Driver / Driver Tag: M01, MOTOR)
│   └── PACKAGE_SKID (Skid Unit: KZ, SK, PK)
│
├── TOPOLOGICAL CONNECTORS
│   ├── NOZZLE (Equipment Flanged Nozzle)
│   ├── JUNCTION (Piping T-Junction / Header Tap)
│   └── CONNECTION (Physical Joint / Tie-in Point)
│
├── NON-ENTITY DOCUMENTATION
│   ├── ANNOTATION (Text Callouts, General Labels)
│   ├── NOTE (Drawing Notes, Revisions, Holds)
│   ├── ATTRIBUTE (Design Pressure, Rating, Material)
│   ├── SPECIFICATION (Piping Class: FC11S, 150#)
│   ├── REFERENCE (Off-page continuation pointer: TO FLARE)
│   ├── LEGEND_OBJECT (Definition symbols on legend)
│   └── TITLE_BLOCK_OBJECT (Sheet metadata block)
│
└── UNCERTAINTY STATES
    ├── UNKNOWN_ENGINEERING_OBJECT (Evidence incomplete)
    └── NEEDS_REVIEW (Ambiguity flagged for engineer review)
```

---

## 2. Critical Disambiguation Rules

### A. The Control Valve vs. Instrument Disambiguation Rule

**The Problem:**  
In conventional systems, tags such as `26-FV-9076`, `PV-26-9127`, `XV-201`, or `HV-101` are often misclassified as `INSTRUMENT_TAG` because their prefix begins with an ISA 5.1 letter (`F`, `P`, `X`, `H`). At the same time, the vision model detects a valve body symbol on the pipeline. This creates **two duplicate entities** for a single physical valve:
1. An `InstrumentItem` named `26-FV-9076`
2. A `ValveItem` named `26-FV-9076` or `V-SYM-01`

**The Resolution Rule ([`src/taxonomy.py#L425-L435`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L425-L435)):**
* Function codes `FV`, `PV`, `TV`, `LV`, `HV`, `XV`, `CV`, `FCV`, `PCV`, `TCV`, `LCV`, `MOV`, `SDV`, `BDV`, `ESV`, `UV`, `ZV` are **explicitly classified as `CONTROL_VALVE` (is_valve=True, is_instrument=False)**.
* Their control purpose (e.g. Flow Control, Shutdown) is bound as `secondary_function = CONTROL_FUNCTION`.
* When both text OCR (`26-FV-9076`) and vision (valve symbol) are observed, they **fuse into a single canonical `ValveItem`** with `type = "Control Valve"`.
* The system is mathematically barred from generating a duplicate `InstrumentItem` for an in-line control valve.

---

### B. Alarm Suffix & State Attribute Extraction Rule

**The Problem:**  
Transmitter bubbles often have alarm suffixes on drawings or adjacent callouts:
* `26-PDI-9054`
* `26-PDI-9054-HH`
* `PDI-9054-LL`

Earlier regex scanners treated `-HH` or `-LL` as distinct tag strings, emitting **three separate instruments** for a single differential pressure indicator.

**The Resolution Rule ([`src/taxonomy.py#L372-L381`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L372-L381)):**
* The tag deconstruction engine applies [`ALARM_SUFFIX_PATTERNS`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L299):
  ```python
  ALARM_SUFFIX_PATTERNS = re.compile(
      r'[-_]?(HH|LL|H|L|HIGH|LOW|TRIP|SD|ESD|ALARM|ALM|SH|SL|AH|AL|O|C)$',
      re.IGNORECASE
  )
  ```
* Any recognized alarm suffix is stripped from the tag string and appended to the candidate's `alarms: List[str]` list.
* The base tag resolves to `PDI-9054`.
* All observations share the identical `canonical_base_tag = "PDI-9054"` and automatically merge in [`CanonicalEntityRegistry`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/candidate_models.py#L210), producing **one physical instrument with structured alarm attributes `['HH', 'LL']`**.

---

### C. Equipment Sub-Component & Driver Separation Rule

**The Problem:**  
Major machinery often includes driver designations:
* `26-KA-901` (Compressor)
* `26-KA-901-M01` (Compressor Motor Driver)

Without structural awareness, `26-KA-901-M01` can be misclassified as a line tag (matching hyphenated patterns) or duplicate equipment item.

**The Resolution Rule ([`src/taxonomy.py#L391-L396`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L391-L396)):**
* Sub-component suffixes (`-M01`, `-MOTOR`, `-STAGE`, `-C01`) are parsed into `sub_component = "M01"`.
* The base tag cleanly extracts `KA-901`.
* The entity taxonomy is correctly set to `EngineeringTaxonomy.MOTOR` or `EngineeringTaxonomy.COMPRESSOR`, maintaining clear parent-child linkage.

---

### D. Piping Line vs. Area-Prefixed Tag Disambiguation Rule

**The Problem:**  
A tag starting with digits (e.g. `26-PDI-9054` or `26-KA-901`) can falsely match generic line tag regexes like `^\d+-[A-Z]+-...` if pipe size tokens are not strictly enforced.

**The Resolution Rule ([`src/taxonomy.py#L354-L368`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/src/taxonomy.py#L354-L368)):**
* A line tag **must** have:
  1. An explicit pipe size token ending with `"`, `'`, `mm`, or `DN` (e.g. `8"-`, `1/2"-`, `25mm-`, `DN50-`), OR
  2. A verified 4-to-6 segment ISA piping format with a recognized piping specification code (e.g. `PV-26-9035-FC11S-08`).
* Area-prefixed instrument and equipment tags lacking pipe size tokens are routed to the proper device classification logic.

---

## 3. Confusion Matrix Analysis (Baseline vs. Phase 3 Architecture)

| Ambiguous Input Tag | Previous Behavior (Baseline) | Phase 3 Behavior (Resolved) | Correct Engineering Meaning |
|---|---|---|---|
| `26-FV-9076` | Duplicate: `InstrumentItem` + `ValveItem` | Single `ValveItem` (`CONTROL_VALVE`) with control function | In-line flow control valve |
| `26-PDI-9054-HH` | Separate `InstrumentItem` | Merged into `26-PDI-9054` with `alarm: HH` | High-high alarm on differential pressure indicator |
| `26-KA-901-M01` | Misclassified as `LineItem` or duplicate equipment | Dissected as `KA-901` sub-component `M01` (`MOTOR`) | Electrical motor driver for compressor |
| `26-PSV-9066A` | Inconsistent (`Instrument` vs `Valve`) | Canonical `SafetyReliefValveItem` (`PSV`) | Pressure safety relief valve |
| `0.05 BARG` | Extracted as partial tag / unclassified entity | Classified as `SETPOINT` attribute | Operating pressure setpoint |
| `FC11S-08` | Misclassified as short line tag | Classified as `SPECIFICATION` attribute | Piping material spec & insulation |
| `PIT-9055` + `26-PIT-9055` | 2 separate instrument items | Merged into 1 primary candidate with alias | Area prefix variant of same physical instrument |

---

## 4. Verification Results

All taxonomy and classification rules were verified using unit tests in [`tests/test_precision_models.py`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/tests/test_precision_models.py). The entire test suite was executed:

* **`pytest`:** 56/56 Passed (100%)
* **Accuracy Test Suite (`test_valve_line_accuracy.py`):** 43/43 Passed (100%)
* **Combined Verification:** **99/99 Tests Passing**
