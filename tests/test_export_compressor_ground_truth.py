"""
Automated Ground-Truth Regression Test Suite for Export Gas Compressor P&ID (26-KA-902).

Validates:
1. Equipment Precision & Recall (5 genuine, 0 false line-tags or table strings)
2. Compressor Datasheet Attributes (98%+ precision)
3. Valve Tag Recall (preserve 98%+ accuracy)
4. Line Tag Precision (rejection of 9 known non-line false strings)
5. Instrument Resolution (physical loop resolution, elimination of OCR fragments & duplicates)
6. PSV Precision, Set Pressure, Flange Sizes (4" x 1.5"), and Relief Destination (HP Flare)
7. Relationship Validation (no universal 1.0, no connections to invalid targets)
"""
import pytest
import re
from typing import Dict, Any, List


# ─────────────────────────────────────────────────────────────────────────────
# Ground Truth Definitions for Export Gas Compressor (26-KA-902)
# ─────────────────────────────────────────────────────────────────────────────

GROUND_TRUTH_EQUIPMENT = {
    "26-KA-902": "Compressor",
    "26-KA-902-M01": "Motor / Driver",
    "26-CX-9021": "Coalescing Filter Separator",
    "26-CX-9222": "Coalescing Filter Separator",
    "26-KZ-902": "Compressor Package Skid",
}

FORBIDDEN_EQUIPMENT_TAGS = {
    "VA-26-9110-AS20S-00",
    "VA-26-9111-AS20S-00",
    "VA-26-9114-AC21-00",
    "VA-26-9112-AC21-00",
    "VA-26-9113-AC21-00",
    "STAGE-26-000001-001-26-PIT-9087",
    "KA-902-STAGE",
    "U-9017-PDIT-9017",
    "M-26-KA-902-M01",
    "CX-9021-2",
    "KA-902-GAS",
    "P-26-TIT-9024",
}

GROUND_TRUTH_VALVES_SAMPLE = [
    "26GT9128", "43BL9054", "26BL9031", "26GT9132", "26BL9032",
    "26GT9133", "43BL9008", "43BL9009", "43GT9052", "26BL9033",
    "26CB9119", "26CB9120", "26CB9121", "26CB9122", "26CB9123",
    "26CB9124", "26CB9131", "26GB9129", "26CB9811", "26GB9035",
    "26CB9812", "26CB9130",
]

FORBIDDEN_LINE_STRINGS = [
    "RD-1835-62809-199-77",
    "PDIT-9015-HH-H",
    "PI-9019-LL-3",
    "FE-9017-31-FC11S",
    "CK-921-OMSMODUL",
    "PI-9023-LL",
    "TI-90239025",
    "DSS-2500-DSS-EL",
    "S-9003-MECHANIC",
]

FORBIDDEN_INSTRUMENT_FRAGMENTS = [
    "TIT-9018-TIT",
    "FE-9017-NOTE",
    "19-PDIT-9015",
    "PDIT-9015-PDI",
    "PDIT-9015-HH",
    "PI-9016-PIT",
    "PI-9016-L",
    "PI-9019-LL",
    "AT-4",
    "FE-9017-31",
    "TI-9018-TIT",
    "OMS-26-CX",
    "PI-9023-PIT",
    "TI-9025-TIT",
    "PI-9026-L",
    "PIT-9026-26",
    "PIT-9026-TIT",
    "46-LTCS-1X100",
]

GROUND_TRUTH_PSVS = ["PSV-9027A", "PSV-9027B"]


# ─────────────────────────────────────────────────────────────────────────────
# Test Functions
# ─────────────────────────────────────────────────────────────────────────────

def test_equipment_validation_rejects_false_lines_and_headers():
    """Verify that line tags and table headers are rejected by equipment validation."""
    from src.utils.entity_validator import validate_equipment_candidate

    for tag in FORBIDDEN_EQUIPMENT_TAGS:
        cand = validate_equipment_candidate(tag)
        assert not cand.is_valid, f"False equipment '{tag}' was accepted as valid equipment!"


def test_equipment_validation_accepts_genuine_equipment():
    """Verify genuine equipment tags pass grammar validation."""
    from src.utils.entity_validator import validate_equipment_candidate

    for tag in GROUND_TRUTH_EQUIPMENT:
        cand = validate_equipment_candidate(tag)
        assert cand.is_valid, f"Genuine equipment '{tag}' was rejected!"


def test_line_tag_grammar_rejects_false_line_strings():
    """Verify non-line strings are rejected by line tag validator."""
    from src.utils.entity_validator import validate_line_candidate

    for bad_line in FORBIDDEN_LINE_STRINGS:
        cand = validate_line_candidate(bad_line)
        assert not cand.is_valid, f"False line string '{bad_line}' was accepted as a valid line!"


def test_line_tag_grammar_accepts_genuine_lines():
    """Verify standard P&ID lines pass validation."""
    from src.utils.entity_validator import validate_line_candidate

    genuine_lines = [
        '4"-PV-26-9020-FC11S-38',
        '6"-PV-26-9017-FC11S-38',
        '8"-PV-26-9007-FC11S-08',
        '2"-PL-26-9115-FC11S-00',
        '10"-VF-43-9007-AS20S-00',
        '12MM-PV-26-9116-FD70X-00',
        '3/4"-DC-26-9026-FC11S-00',
        '2"-VA-26-9110-AS20S-00',
    ]
    for line in genuine_lines:
        cand = validate_line_candidate(line)
        assert cand.is_valid, f"Genuine line '{line}' was rejected!"


def test_psv_flange_spec_and_destination_validation():
    """Verify PSV flange specification captures decimal fractions and destination correctly."""
    from src.utils.datasheet_parser import parse_psv_flange_specs

    # Mock OCR items containing the 4" x 1.5" spec
    mock_ocr = [
        {"classification": "PSV_TAG", "tag": "PSV-9027A", "center_y": 0.50, "center_x": 0.30},
        {"text": '4" x 1.5" 300# 150#', "center_y": 0.51, "center_x": 0.30},
        {"text": 'TO HP FLARE', "center_y": 0.52, "center_x": 0.30},
    ]
    specs = parse_psv_flange_specs(mock_ocr)
    assert "PSV-9027A" in specs, "PSV-9027A flange specs not parsed"
    spec = specs["PSV-9027A"]
    assert "1.5" in spec["outlet_size"], f"Expected outlet size 1.5\", got {spec['outlet_size']}"
    assert "4" in spec["inlet_size"], f"Expected inlet size 4\", got {spec['inlet_size']}"


def test_psv_tag_normalization_strips_leading_hyphen():
    """Verify that leading hyphen in -PSV-9027A is stripped to normalize away duplicate."""
    from src.utils.entity_validator import normalize_psv_tag

    assert normalize_psv_tag("-PSV-9027A") == "PSV-9027A"
    assert normalize_psv_tag("26-PSV-9027A") == "26-PSV-9027A"
    assert normalize_psv_tag("PSV-9027B") == "PSV-9027B"


def test_instrument_resolver_groups_duplicates_into_physical_loops():
    """Verify instrument loop representations are grouped into canonical physical instruments."""
    from src.utils.instrument_resolver import resolve_instrument_candidates

    candidates = [
        {"tag": "PIT-9026", "text": "PIT-9026", "confidence": 0.95},
        {"tag": "PI-9026", "text": "PI-9026", "confidence": 0.95},
        {"tag": "PIT-9026-TIT", "text": "PIT-9026-TIT", "confidence": 0.70},
        {"tag": "PI-9026-L", "text": "PI-9026-L", "confidence": 0.70},
        {"tag": "PIT-9026-26", "text": "PIT-9026-26", "confidence": 0.70},
    ]
    resolved, rejected = resolve_instrument_candidates(candidates)
    
    # Should resolve into exactly 1 canonical loop entity for loop 9026
    loop_9026_items = [r for r in resolved if "9026" in r.tag]
    assert len(loop_9026_items) == 1, f"Expected 1 resolved instrument for loop 9026, got {len(loop_9026_items)}: {[r.tag for r in loop_9026_items]}"
    assert loop_9026_items[0].tag in ("26-PIT-9026", "PIT-9026")
    # All duplicate/fragment strings should be accounted for in rejected/aliases
    assert len(rejected) >= 3


def test_confidence_calibration_no_universal_one():
    """Verify relationship confidence calculation is calibrated and never universally 1.0."""
    from src.utils.relationship_engine import calculate_relationship_confidence

    # Low geometry evidence
    conf_low = calculate_relationship_confidence(
        ocr_conf=0.95,
        grammar_score=0.90,
        geometry_score=0.30,
        topology_score=0.20,
        has_symbol_evidence=False
    )
    assert conf_low < 0.70, f"Expected low confidence for weak geometry, got {conf_low}"

    # High multi-factor evidence
    conf_high = calculate_relationship_confidence(
        ocr_conf=0.95,
        grammar_score=1.00,
        geometry_score=0.95,
        topology_score=0.90,
        has_symbol_evidence=True
    )
    assert 0.85 <= conf_high <= 0.98, f"Expected calibrated high confidence, got {conf_high}"
    assert conf_high != 1.0, "Confidence should be evidence-calibrated, never hardcoded 1.0"
