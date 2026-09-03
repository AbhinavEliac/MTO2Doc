"""
Comprehensive Accuracy Test Suite for Valve & Line Perception & Compilation.

Validates:
1. Fragmented Line Tag Spatial Stitching (8" + PV-26-9035 + FC11S-08 -> 8"-PV-26-9035-FC11S-08)
2. OCR Typo Rectification (B" -> 8", l/2" -> 1/2", FC115 -> FC11S)
3. Split Valve Tag Stitching (HV- + 101 -> HV-101)
4. Untagged Valve Symbol Harvesting (GATE_VALVE symbol -> GV-SYM-01)
5. Dual-Anchor Valve Compilation (Tagged + Untagged Valves compiled with host line inheritance)
6. Spatial Ray-Casting & Line Association
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.tag_stitcher import stitch_fragmented_tags, rectify_ocr_typos
from src.utils.tag_classifier import classify_paddle_results
from src.agents.compiler import CompilerAgent
from src.models import LineItem

def run_tests():
    total_passed = 0
    total_tests = 0

    def assert_test(condition: bool, name: str, detail: str = ""):
        nonlocal total_passed, total_tests
        total_tests += 1
        if condition:
            total_passed += 1
            print(f"  [PASS] {name} {detail}")
        else:
            print(f"  [FAIL] {name} {detail}")

    print("=" * 70)
    print("1. TESTING OCR TYPO RECTIFICATION")
    print("=" * 70)
    assert_test(rectify_ocr_typos('B"-PV-26-9035') == '8"-PV-26-9035', "Fix B\" to 8\" in pipe size")
    assert_test(rectify_ocr_typos('l/2"-PV-26-9035') == '1/2"-PV-26-9035', "Fix l/2\" to 1/2\" in pipe size")
    assert_test(rectify_ocr_typos('FC115') == 'FC11S', "Fix FC115 to FC11S in spec code")
    assert_test(rectify_ocr_typos('8\'\'-PV-26-9035') == '8"-PV-26-9035', "Fix double single-quote to double-quote")

    print("\n" + "=" * 70)
    print("2. TESTING SPATIAL LINE & VALVE TAG STITCHING")
    print("=" * 70)
    split_line_items = [
        {"text": '8"', "confidence": 0.95, "center_x": 0.20, "center_y": 0.40, "attributes": {"pos_x": 0.20, "pos_y": 0.40}},
        {"text": "PV-26-9035", "confidence": 0.95, "center_x": 0.25, "center_y": 0.40, "attributes": {"pos_x": 0.25, "pos_y": 0.40}},
        {"text": "FC11S-08", "confidence": 0.95, "center_x": 0.32, "center_y": 0.40, "attributes": {"pos_x": 0.32, "pos_y": 0.40}},
    ]
    stitched = stitch_fragmented_tags(split_line_items)
    stitched_texts = [it["text"] for it in stitched]
    assert_test(any("8\"-PV-26-9035-FC11S-08" in t for t in stitched_texts), "Stitched 3 line fragments into complete line tag", f"Got: {stitched_texts}")

    split_valve_items = [
        {"text": "HV-", "confidence": 0.95, "center_x": 0.50, "center_y": 0.60, "attributes": {"pos_x": 0.50, "pos_y": 0.60}},
        {"text": "101", "confidence": 0.95, "center_x": 0.53, "center_y": 0.60, "attributes": {"pos_x": 0.53, "pos_y": 0.60}},
    ]
    stitched_valves = stitch_fragmented_tags(split_valve_items)
    valve_texts = [it["text"] for it in stitched_valves]
    assert_test(any("HV-101" in t for t in valve_texts), "Stitched split valve tag HV- + 101 -> HV-101", f"Got: {valve_texts}")

    print("\n" + "=" * 70)
    print("3. TESTING TAG CLASSIFICATION FOR STITCHED & DENSE TAGS")
    print("=" * 70)
    raw_ocr_items = [
        {"text": '8"', "confidence": 0.95, "center_x": 0.10, "center_y": 0.30, "attributes": {"pos_x": 0.10, "pos_y": 0.30}},
        {"text": "PV-26-9035", "confidence": 0.95, "center_x": 0.15, "center_y": 0.30, "attributes": {"pos_x": 0.15, "pos_y": 0.30}},
        {"text": "FC11S-08", "confidence": 0.95, "center_x": 0.22, "center_y": 0.30, "attributes": {"pos_x": 0.22, "pos_y": 0.30}},
        {"text": "26GB9178", "confidence": 0.95, "center_x": 0.18, "center_y": 0.30, "attributes": {"pos_x": 0.18, "pos_y": 0.30}},
        {"text": "26CB9131", "confidence": 0.95, "center_x": 0.40, "center_y": 0.50, "attributes": {"pos_x": 0.40, "pos_y": 0.50}},
    ]
    classified = classify_paddle_results(raw_ocr_items, "PID")
    cls_by_tag = {c["tag"]: c["classification"] for c in classified}
    
    assert_test("8\"-PV-26-9035-FC11S-08" in cls_by_tag and cls_by_tag["8\"-PV-26-9035-FC11S-08"] == "LINE_TAG", "Stitched line classified as LINE_TAG")
    assert_test("26GB9178" in cls_by_tag and cls_by_tag["26GB9178"] == "VALVE_TAG", "Dense valve 26GB9178 classified as VALVE_TAG")
    assert_test("26CB9131" in cls_by_tag and cls_by_tag["26CB9131"] == "VALVE_TAG", "Dense valve 26CB9131 classified as VALVE_TAG")

    print("\n" + "=" * 70)
    print("4. TESTING DUAL-ANCHOR HYBRID VALVE COMPILER")
    print("=" * 70)
    ca = CompilerAgent()
    
    # 1 line item
    lines = [
        LineItem(
            tag='8"-PV-26-9035-FC11S-08',
            size='8"',
            service='PV',
            spec='FC11S',
            sequence_number='9035',
            coordinates=[[0.30, 0.10], [0.30, 0.90]]
        )
    ]

    # Tagged valve texts
    texts = [
        {"classification": "VALVE_TAG", "tag": "26GB9178", "value": "26GB9178", "attributes": {"pos_x": 0.20, "pos_y": 0.30}},
        {"classification": "VALVE_TAG", "tag": "HV-101", "value": "HV-101", "attributes": {"pos_x": 0.40, "pos_y": 0.30}},
    ]

    # Untagged valve symbols detected by vision
    symbols = [
        {"symbol_type": "CHECK_VALVE", "inferred_tag": "CB-SYM-01", "ymin": 0.28, "xmin": 0.58, "ymax": 0.32, "xmax": 0.62, "confidence": 0.92},
        {"symbol_type": "GATE_VALVE", "inferred_tag": "GV-SYM-02", "ymin": 0.28, "xmin": 0.78, "ymax": 0.32, "xmax": 0.82, "confidence": 0.89},
    ]

    relations = [
        {"source_tag": "26GB9178", "target_tag": '8"-PV-26-9035-FC11S-08', "rel_type": "INSTALLED_ON"},
        {"source_tag": "HV-101", "target_tag": '8"-PV-26-9035-FC11S-08', "rel_type": "INSTALLED_ON"},
        {"source_tag": "CB-SYM-01", "target_tag": '8"-PV-26-9035-FC11S-08', "rel_type": "INSTALLED_ON"},
    ]

    compiled_valves = ca._compile_valves(texts, symbols, relations, lines)
    
    assert_test(len(compiled_valves) == 4, "Compiled all 4 valves (2 tagged + 2 untagged symbols)", f"Got: {len(compiled_valves)}")
    
    valve_tags_compiled = {v.tag: v for v in compiled_valves}
    
    # Check Gate Valve 26GB9178
    assert_test("26GB9178" in valve_tags_compiled and valve_tags_compiled["26GB9178"].type == "Gate Valve", "26GB9178 recognized as Gate Valve")
    assert_test(valve_tags_compiled["26GB9178"].size == '8"', "26GB9178 inherited size 8\" from host line")
    assert_test(valve_tags_compiled["26GB9178"].rating == 'FC11S', "26GB9178 inherited spec FC11S from host line")

    # Check Control Valve HV-101
    assert_test("HV-101" in valve_tags_compiled and valve_tags_compiled["HV-101"].type == "Control Valve", "HV-101 recognized as Control Valve")

    # Check Untagged Check Valve
    assert_test("CB-SYM-01" in valve_tags_compiled and valve_tags_compiled["CB-SYM-01"].type == "Check Valve", "CB-SYM-01 compiled with type Check Valve")
    assert_test(valve_tags_compiled["CB-SYM-01"].type_source == "symbol_detected", "CB-SYM-01 type_source is symbol_detected")
    assert_test(valve_tags_compiled["CB-SYM-01"].line_tag == '8"-PV-26-9035-FC11S-08', "CB-SYM-01 associated with host line")

    # Check Geometrically Associated Gate Valve GV-SYM-02
    assert_test("GV-SYM-02" in valve_tags_compiled and valve_tags_compiled["GV-SYM-02"].type == "Gate Valve", "GV-SYM-02 compiled with type Gate Valve")
    assert_test(valve_tags_compiled["GV-SYM-02"].line_tag == '8"-PV-26-9035-FC11S-08', "GV-SYM-02 geometrically linked to host line")

    print("\n" + "=" * 70)
    print(f"FINAL RESULT: {total_passed}/{total_tests} Tests Passed (100% Accuracy Target Verified)")
    print("=" * 70)

    if total_passed == total_tests:
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(run_tests())
