# Precision Branch Regression Report
**Engineering Drawing Intelligence System (MTO2Doc)**  
**Target Drawing:** `pid_stuff/Lift Gas compressor-PID.pdf`  
**Execution Date:** September 30, 2026

---

## 1. Test Execution Summary

| Test Suite | Commands Executed | Tests Collected | Passed | Failed | Execution Time | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Pytest Full Suite** | `pytest tests/` | 60 | 60 | 0 | 10.41s | **100% PASS** |
| **Valve & Line Accuracy** | `python tests/test_valve_line_accuracy.py` | 43 | 43 | 0 | 11.23s | **100% PASS** |
| **Ground Truth Precision** | `python scratch_compute_precision.py` | 104 GT Entities | 104 TP | 0 FN | 13.56s | **100% PASS** |

---

## 2. Regression Analysis by Test Category

### A. Tag Parsing & OCR Rectification
- Stitched 3-fragment lines: `8"-PV-26-9035-FC11S-08` [PASS]
- Split valve tags: `HV-` + `101` $\rightarrow$ `HV-101` [PASS]
- OCR typo rectification (`B"` $\rightarrow$ `8"`, `l/2"` $\rightarrow$ `1/2"`, `FC115` $\rightarrow$ `FC11S`): [PASS]
- Dense manual valve classification (`26GB9178`, `26CB9131` as `VALVE_TAG`): [PASS]

### B. Dual-Anchor Hybrid Valve Compilation
- Total compiled valves from mixed text + vision symbols: 4 valves [PASS]
- Gate valve recognition and attribute inheritance: [PASS]
- Size inheritance from host line (8"): [PASS]
- Rating derivation from line spec (`FC11S` $\rightarrow$ `2500#`): [PASS]
- Hand control valve classification (`HV-101`): [PASS]
- Untagged check valve detection (`CB-SYM-01`): [PASS]
- Geometrically associated gate valve (`GV-SYM-02`): [PASS]
- Spec-to-ANSI class mapping (`GC11S` $\rightarrow$ `150#`): [PASS]

### C. Equipment Taxonomy & PSV Recovery
- Coalescing filter separator (`26-CX-9122`): [PASS]
- Compressor classification (`26-KA-901`): [PASS]
- PSV unit number recovery (`Unit 26`): [PASS]
- Relief destination assignment (`HP Flare Header`): [PASS]

### D. Advanced Pipeline Checks
- Rejected hallucinated line with `-NOTE`: [PASS]
- Rejected hallucinated line with `-TIT`: [PASS]
- Rejected motor driver tag from Line List: [PASS]
- Rejected transmitter cable tag from Line List: [PASS]
- Reversal of inverted relation directions: [PASS]
- Sibling instrument extraction (`27-PY-0001BA`, `27-PY-0001BB`): [PASS]
- Suction strainer recognition (`26-CK-911` / `26-ST-9002`): [PASS]
- Zero orphan instruments (Rule VAL-004): [PASS]

---

## 3. Ground Truth Recall Guarantee

Baseline Recall was **96.15%**.  
Precision Branch Recall is **100.00%** (104 / 104).  
No ground truth entities were suppressed or dropped:
- `26-CK-911` (Equipment Suction Strainer): Captured and compiled.
- `26-PSE-9216` & `26-PSE-9758` (Rupture Discs): Captured and compiled into instruments.
- `26-PSV-9066A` & `26-PSV-9066B` (Safety Relief Valves): Captured and compiled into safety relief valves.
- `40-XV-9010` (Cooling Water Isolation Valve): Captured and compiled.
- All 40 Manual Valves (`26BL9072` through `40GT9308`): Captured and compiled.
- All 35 Process Lines (`1"-DC-57-9015` through `2"-VF-43-9032`): Captured and compiled.

**Conclusion:** Zero regressions occurred. All perception recall capabilities have been preserved and expanded to 100% ground truth coverage.
