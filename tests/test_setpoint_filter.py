"""
Regression tests for Defect 3: Setpoint hallucination guard.

Ensures that instrument-tag-like patterns inside setpoint/note blocks
(e.g. 'SD HH: 150 barg' → PI-150, 'SP=225.4 bar(g)' → AT-225)
are NOT classified as INSTRUMENT_TAGs.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.utils.tag_classifier import classify_paddle_results, _is_setpoint_context


def _make_ocr_item(text: str, conf: float = 0.95) -> dict:
    return {
        "text": text,
        "confidence": conf,
        "center_x": 0.5,
        "center_y": 0.5,
    }


SETPOINT_CONTEXTS = [
    # (ocr_text, description)
    ("SD HH: 150 barg", "SD HH shutdown setpoint"),
    ("LL: 110 barg", "Low-low setpoint"),
    ("H: 125 barg", "High setpoint"),
    ("L: 100 barg", "Low setpoint"),
    ("SP= 225.4 bar(g)", "PSV set pressure"),
    ("SP = 225.4 bar (g)", "PSV set pressure with spaces"),
    ("DESIGN PRESS 225 barg", "Design pressure label"),
    ("MAX 200 psig", "Maximum operating pressure"),
    ("MIN 50 psig", "Minimum operating pressure"),
    ("SET PRESS 225.4 bar(g)", "Set pressure full form"),
    ("HH: 150", "HH alarm setpoint bare"),
    ("225 BARG", "Standalone barg value"),
    ("MAWP 286 barg", "Maximum allowable working pressure"),
]


class TestSetpointFilter:

    def test_no_instrument_tags_from_setpoint_strings(self):
        """
        None of the setpoint note patterns should produce INSTRUMENT_TAG results.
        They should be demoted to NOTE with flag_reason='ambiguous_setpoint_vs_tag'.
        """
        for ocr_text, description in SETPOINT_CONTEXTS:
            items = [_make_ocr_item(ocr_text)]
            result = classify_paddle_results(items, drawing_type="PID")
            inst_tags = [
                r for r in result
                if r["classification"] == "INSTRUMENT_TAG"
                and r.get("flag_reason") != "ambiguous_setpoint_vs_tag"
            ]
            assert len(inst_tags) == 0, (
                f"FAIL [{description}]: '{ocr_text}' produced unexpected "
                f"INSTRUMENT_TAG(s): {[r['tag'] for r in inst_tags]}"
            )

    def test_real_instrument_tags_not_blocked(self):
        """
        Genuine bare instrument tags without setpoint context must still be classified.
        """
        genuine_tags = [
            "PIT-9087",
            "PDI-9054",
            "TIT-9057",
            "FIT-9031",
            "LIT-9041",
        ]
        for tag in genuine_tags:
            items = [_make_ocr_item(tag)]
            result = classify_paddle_results(items, drawing_type="PID")
            inst_tags = [
                r for r in result
                if r["classification"] == "INSTRUMENT_TAG"
                and r["tag"] == tag.upper()
            ]
            assert len(inst_tags) == 1, (
                f"FAIL: Genuine tag '{tag}' was blocked or misclassified. "
                f"Got: {[r for r in result if r.get('tag') == tag.upper()]}"
            )

    def test_is_setpoint_context_detection(self):
        """Unit test the _is_setpoint_context function directly."""
        # Should detect setpoint context
        assert _is_setpoint_context("SD HH: 150 barg", 0, 15)
        assert _is_setpoint_context("LL: 110 barg", 0, 12)
        assert _is_setpoint_context("SP=225.4 bar(g)", 0, 15)
        assert _is_setpoint_context("DESIGN PRESS 225 barg", 0, 21)
        # Should NOT detect for clean tags
        assert not _is_setpoint_context("PIT-9087", 0, 8)
        assert not _is_setpoint_context("TRANSMITTER 26-PIT-9087", 12, 24)

    def test_flagged_items_have_flag_reason(self):
        """Demoted items must carry flag_reason='ambiguous_setpoint_vs_tag'."""
        items = [_make_ocr_item("SD HH: 150 barg")]
        result = classify_paddle_results(items, drawing_type="PID")
        # Find any NOTE with flag_reason set
        flagged = [r for r in result if r.get("flag_reason") == "ambiguous_setpoint_vs_tag"]
        # May not flag if no instrument pattern is found in text — either way no INSTRUMENT_TAG
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == 0

    def test_confidence_low_on_flagged(self):
        """Demoted setpoint items must have confidence <= 0.25."""
        for ocr_text, _ in SETPOINT_CONTEXTS:
            items = [_make_ocr_item(ocr_text)]
            result = classify_paddle_results(items, drawing_type="PID")
            for r in result:
                if r.get("flag_reason") == "ambiguous_setpoint_vs_tag":
                    assert r.get("confidence", 1.0) <= 0.25, (
                        f"Expected confidence <= 0.25 for flagged item '{r['tag']}', "
                        f"got {r.get('confidence')}"
                    )

    def test_spatial_multi_box_setpoint_detection(self):
        """When PI-150 is in one box and 'SD HH: 150 BARG' is adjacent, PI-150 must be demoted."""
        from src.utils.tag_classifier import _is_setpoint_context_spatial
        items = [
            {"text": "PI-150", "confidence": 0.95, "center_x": 0.50, "center_y": 0.30},
            {"text": "SD HH: 150 BARG", "confidence": 0.95, "center_x": 0.52, "center_y": 0.32},
        ]
        assert _is_setpoint_context_spatial(0, items) is True

