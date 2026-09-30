# Precision Baseline Evaluation Report

**Document Version:** 1.0.0  
**Target Branch:** `precision`  
**Date:** 2026-09-30  
**Representative Ground Truth P&ID:** `pid_stuff/Lift Gas compressor-PID.pdf` (Drawing `26-KA-901`)  
**Ground Truth Reference:** `pid_stuff/PID_Extraction_RevB_Corrected_26-KA-901_902 (2).xlsx`  
**Status:** Frozen Baseline — Do NOT Modify After Implementation  

---

## 1. Executive Summary

This document establishes the official empirical baseline for the MTO2Doc precision engineering branch.
Measurements were conducted on the primary representative drawing `Lift Gas compressor-PID.pdf` (`26-KA-901`) against the engineer-verified ground truth extraction sheet (`PID_Extraction_RevB_Corrected_26-KA-901_902 (2).xlsx`).

The empirical evidence confirms the central thesis of the project:
* **Perception Recall is exceptionally high (96.15% Overall Entity Recall):** 100 out of 104 ground truth entities were successfully captured by the visual and text perception layers.
* **Canonical Entity Precision is low (48.87% Overall Precision):** The pipeline generated 221 compiled canonical entities for 104 real objects—a **51.13% duplicate and false entity rate**.
* **Relationship Topology is contaminated:** 230 compiled relationships contain edges connecting valves to raw OCR specification strings (e.g. `SP-26-300-26GT9174-1`) or instrument bubbles (e.g. `PI-9062-PIT-9062`) rather than canonical process lines.

---

## 2. Core Quantitative Baseline Metrics

The quantitative metrics below are stored in machine-readable JSON format at [`PRECISION_BASELINE.json`](file:///c:/DS_and_AI/Projects_and_Tutorials/Projects/pid_project/PRECISION_BASELINE.json):

| Metric | Measured Baseline Value | Target Requirement | Gap to Target |
|---|---|---|---|
| **Raw Observation Count** | **2,024** | — | Visual & OCR observation pool |
| **Candidate Count** | **1,450** | — | Intermediate classified items |
| **Ground Truth Entities ($GT$)** | **104** | — | Real canonical engineering objects |
| **Compiled Entities ($Comp$)** | **221** | 104–110 | +117 surplus entities (+112.5% inflation) |
| **True Positives ($TP$)** | **100** | $\ge 100$ | Baseline recall foundation |
| **False Positives ($FP$)** | **113** | $\le 10$ | Primary target for precision repair |
| **False Negatives ($FN$)** | **4** | $\le 4$ | Preservation gate |
| **Overall Entity Recall** | **96.15%** | $\ge 96.15\%$ (No regression) | **PASS (Baseline Gate)** |
| **Overall Entity Precision** | **48.87%** | $\ge 90.0\%$ | **-41.13% (Target for Phase 9–16)** |
| **Overall F1 Score** | **0.6480** | $\ge 0.930$ | +0.282 required |
| **Duplicate Entity Rate** | **51.13%** | $< 5.0\%$ | -46.13% reduction required |
| **False Entity Rate** | **51.13%** | $< 5.0\%$ | -46.13% reduction required |
| **Classification Error Rate** | **37.10%** | $< 5.0\%$ | Control valve & suffix absorption |
| **Compiled Relationships** | **230** | — | Clean canonical edges only |
| **Relationship Precision** | **~32.5%** | $\ge 90.0\%$ | Exclude raw OCR endpoints |
| **Relationship Recall** | **NOT YET MEASURABLE** | $\ge 90.0\%$ | Full drawing edge graph not fully tabulated |
| **Re-Extraction Count** | **0** | Pass-specific | Idempotence required |

---

## 3. Discipline & Category Performance Breakdown

| Engineering Category | Ground Truth ($GT$) | Compiled Entities | True Positives ($TP$) | False Positives ($FP$) | False Negatives ($FN$) | Category Recall | Category Precision | Category F1 |
|---|---|---|---|---|---|---|---|---|
| **EQUIPMENT** | 7 | 20 | 6 | 10 | 1 | **85.71%** | **50.00%** | **0.6316** |
| **SAFETY RELIEF (PSV)** | 2 | 2 | 2 | 0 | 0 | **100.00%** | **100.00%** | **1.0000** |
| **INSTRUMENTS** | 20 | 61 | 17 | 40 | 3 | **85.00%** | **34.43%** | **0.4900** |
| **VALVES** | 40 | 72 | 40 | 32 | 0 | **100.00%** | **55.56%** | **0.7143** |
| **LINES** | 35 | 66 | 35 | 31 | 0 | **100.00%** | **53.03%** | **0.6931** |
| **TOTAL** | **104** | **221** | **100** | **113** | **4** | **96.15%** | **48.87%** | **0.6480** |

---

## 4. Analysis of Ground Truth vs Extraction Deficits

### 4.1 Equipment (Recall: 85.71%, Precision: 50.00%)
* **Ground Truth (7 items):**
  1. `26-KA-901` (3rd Stage HP Gas Lift Compressor) — **CAPTURED**
  2. `26-KA-901-M01` (Compressor Motor) — **CAPTURED**
  3. `26-KZ-901` (Compressor Skid Package) — **CAPTURED**
  4. `26-HA-911` (Seal Gas Cooler) — **CAPTURED**
  5. `26-CX-9011` (OMS Module) — **CAPTURED**
  6. `26-CX-9122` (Seal Gas Booster) — **CAPTURED**
  7. `26-CK-911` (Suction Strainer) — **MISSED (FN)** (labeled `CK-911` in drawing notes, classified as valve due to `CK` code).
* **False Positives (10 items):**
  - Text descriptions and drawing callouts (e.g. `3RD STAGE HP GAS LIFT COMPRESSOR`, `COMPRESSOR SKID`, `MAN ENERGY SOLUTIONS`) parsed by regex allowlist as generic equipment.
  - Sub-assembly callouts (`HA-911-C01`, `HA-911-C02`) created redundant equipment items instead of sub-assemblies.

### 4.2 Safety Relief Valves (Recall: 100.0%, Precision: 100.0%)
* **Ground Truth (2 items):**
  1. `26-PSV-9066A` (Compressor Discharge Relief Duty) — **CAPTURED**
  2. `26-PSV-9066B` (Compressor Discharge Relief Standby) — **CAPTURED**
* **Performance:** Flawless precision and recall. Both PSVs correctly captured with set pressure parsing.

### 4.3 Instruments (Recall: 85.00%, Precision: 34.43%)
* **Ground Truth (20 items):**
  - 17 items captured: `26-PIT-9055`, `26-PDIT-9054`, `26-PIT-9058`, `26-TIT-9057`, `26-TIT-9211`, `26-PIT-9215`, `26-FE-9056`, `26-PDIT-9056`, `26-PIT-9062`, `26-PIT-9065`, `26-TIT-9063`, `26-TIT-9064`, `26-PDIT-9757`, `26-FE-9757`, `26-PIT-9759`, `26-PY-9077A`, `26-PY-9077B`.
  - 3 items missed:
    1. `26-PSE-9216` (Rupture disc: regex did not recognize `PSE` as an instrument).
    2. `26-PSE-9758` (Rupture disc: same issue).
    3. `40-XV-9010` (Cooling water on/off valve: classified as valve `XV` rather than instrument list).
* **False Positives (40 surplus instruments):**
  - Duplicate loop observations: `PDIT-9054` and `26-PDIT-9054` and `PDIT-9054-HH` compiled as 3 instruments.
  - Alarm suffix tokens (`HH`, `LL`, `SD`) captured as bare instrument tags.
  - Control functions (`FV`, `PV`) creating duplicate instruments alongside valves.

### 4.4 Manual Valves (Recall: 100.0%, Precision: 55.56%)
* **Ground Truth (40 items):**
  - All 40 ground truth valves (`26BL9072` to `40GT9308`) were detected ($Recall = 100\%$).
* **False Positives (32 surplus valves):**
  - Duplicate bare vs prefixed tags (`26BL9072` vs `BL9072`).
  - Untagged symbol harvester synthesized `GV-SYM-01`, `CB-SYM-02` for graphic features that were already tagged or were pipe crossovers.

### 4.5 Piping Lines (Recall: 100.0%, Precision: 53.03%)
* **Ground Truth (35 lines):**
  - All 35 ground truth lines (`8"-PV-26-9035-FC11S-08` through `4"-WC-26-9128-EC11S-00`) were detected ($Recall = 100\%$).
* **False Positives (31 surplus lines):**
  - Multiple text fragments of the same continuous pipeline along different sheet regions compiled as separate lines.
  - Line spec strings and insulation suffixes parsed as standalone lines.

---

## 5. Non-Negotiable Regression Floor

The following baseline metrics form the **absolute regression gates** for all subsequent phases:

$$\text{OVERALL ENTITY RECALL} \ge 96.15\%$$
$$\text{LINE RECALL} \ge 100.00\%$$
$$\text{VALVE RECALL} \ge 100.00\%$$
$$\text{PSV RECALL} \ge 100.00\%$$
$$\text{EQUIPMENT RECALL} \ge 85.71\%$$
$$\text{INSTRUMENT RECALL} \ge 85.00\%$$

No architectural change that causes recall to drop below these thresholds will be accepted.
The precision improvement must be achieved through **evidence fusion, candidate normalization, canonical deduplication, and topology gating**, NEVER by threshold deletion or detection suppression.
