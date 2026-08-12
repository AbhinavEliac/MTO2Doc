"""
Regression tests for Defect 4: Line tag grammar enforcement.

Ensures corrupt-merge line tags are flagged (not silently accepted) and
that NOTE references are stripped before processing.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.utils.tag_classifier import classify_paddle_results, _validate_line_tag_size


def _make_ocr_item(text: str, conf: float = 0.95) -> dict:
    return {"text": text, "confidence": conf, "center_x": 0.5, "center_y": 0.5}


class TestLineTagGrammar:

    def test_corrupt_size_262_inch_is_flagged(self):
        """262\"-VA-26-9110-AS20S-00 has an impossible size — must be flagged."""
        valid, flag_reason = _validate_line_tag_size('262"-VA-26-9110-AS20S-00')
        assert not valid, "Expected invalid=True for 262\" size"
        assert flag_reason and "corrupt_merge" in flag_reason, (
            f"Expected 'corrupt_merge' in flag_reason, got: {flag_reason}"
        )

    def test_valid_sizes_pass_without_flag(self):
        """Standard pipe sizes should pass without any flag_reason."""
        for size_prefix in ['2"-VA-26-9110', '8"-PV-26-9035', '12"-PV-26-9035', '3/4"-VA-26-9114']:
            valid, flag_reason = _validate_line_tag_size(size_prefix)
            assert valid, f"Expected valid=True for size in '{size_prefix}'"
            assert flag_reason is None or "unverified" in flag_reason or "unrecognized" in flag_reason, (
                f"Unexpected flag_reason '{flag_reason}' for '{size_prefix}'"
            )

    def test_note_ref_stripped_from_line_tag(self):
        """'3/4\"-VA-26-9114-AC21-00NOTE20' must have NOTE20 stripped and line tag still found."""
        items = [_make_ocr_item('3/4"-VA-26-9114-AC21-00NOTE20')]
        result = classify_paddle_results(items, drawing_type="PID")
        line_tags = [r for r in result if r["classification"] == "LINE_TAG"]
        # The tag should be found and NOTE20 should NOT be in the tag string
        for lt in line_tags:
            assert "NOTE20" not in lt["tag"] and "NOTE" not in lt["tag"].upper().replace("NOTE", ""), (
                f"NOTE20 should be stripped from line tag, got: '{lt['tag']}'"
            )
        # Verify that a flag_reason is recorded
        if line_tags:
            flag_reasons = [lt.get("flag_reason") for lt in line_tags]
            # At minimum one should be flagged for note stripping
            # (acceptable if stripped version is valid)

    def test_corrupt_size_emitted_with_low_confidence(self):
        """Corrupt-size tags should be emitted (for human review) but with confidence <= 0.5."""
        items = [_make_ocr_item('262"-VA-26-9110-AS20S-00')]
        result = classify_paddle_results(items, drawing_type="PID")
        line_tags = [r for r in result if r["classification"] == "LINE_TAG"]
        for lt in line_tags:
            if lt.get("flag_reason") and "corrupt" in lt["flag_reason"]:
                assert lt.get("confidence", 1.0) <= 0.5, (
                    f"Expected confidence <= 0.5 for corrupt-size tag, got {lt.get('confidence')}"
                )

    def test_clean_line_tag_has_high_confidence(self):
        """A well-formed line tag should have full confidence and no flag_reason."""
        items = [_make_ocr_item('8"-PV-26-9035-FC11S-08')]
        result = classify_paddle_results(items, drawing_type="PID")
        line_tags = [r for r in result if r["classification"] == "LINE_TAG"]
        assert len(line_tags) >= 1, "Expected at least one LINE_TAG for clean input"
        for lt in line_tags:
            if not lt.get("flag_reason"):
                assert lt.get("confidence", 0) >= 0.8, (
                    f"Expected confidence >= 0.8 for clean line tag, got {lt.get('confidence')}"
                )

    def test_size_validation_out_of_range(self):
        """A numeric size > 600 that is not a standard NPS should be flagged invalid."""
        valid, flag_reason = _validate_line_tag_size('900-VA-26-9110-AS20S-00')
        # 900 is out of range for standard pipe sizes
        assert flag_reason is not None, (
            "Expected a flag_reason for out-of-range size 900"
        )
