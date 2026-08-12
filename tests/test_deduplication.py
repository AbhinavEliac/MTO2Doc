"""
Regression tests for Defect 2: Tag deduplication / canonicalization.

Ensures that short and prefixed forms of the same tag collapse to ONE entity
with the longer form as canonical and the short form as an alias.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.utils.tag_classifier import classify_paddle_results, canonicalize_tag


def _make_ocr_item(text: str, conf: float = 0.95) -> dict:
    return {
        "text": text,
        "confidence": conf,
        "center_x": 0.5,
        "center_y": 0.5,
        "box": [0.4, 0.4, 0.6, 0.6],
    }


class TestTagCanonicalization:

    def test_canonical_strips_area_prefix(self):
        assert canonicalize_tag("26-PIT-9087") == "PIT-9087"
        assert canonicalize_tag("43-PDI-9015") == "PDI-9015"
        assert canonicalize_tag("PIT-9087") == "PIT-9087"
        assert canonicalize_tag("26-PSV-9066A") == "PSV-9066A"

    def test_prefixed_and_bare_merge_to_one_instrument(self):
        """26-PIT-9087 and PIT-9087 must produce exactly one INSTRUMENT_TAG."""
        items = [
            _make_ocr_item("26-PIT-9087"),
            _make_ocr_item("PIT-9087"),
        ]
        result = classify_paddle_results(items, drawing_type="PID")
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == 1, (
            f"Expected 1 INSTRUMENT_TAG, got {len(inst_tags)}: "
            f"{[r['tag'] for r in inst_tags]}"
        )

    def test_winner_is_longer_tag(self):
        """The canonical winner should be the project-prefixed (longer) form."""
        items = [
            _make_ocr_item("PIT-9087"),
            _make_ocr_item("26-PIT-9087"),
        ]
        result = classify_paddle_results(items, drawing_type="PID")
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == 1
        assert inst_tags[0]["tag"] == "26-PIT-9087", (
            f"Expected winner '26-PIT-9087', got '{inst_tags[0]['tag']}'"
        )

    def test_alias_recorded(self):
        """Short form should appear in aliases of the winning item."""
        items = [
            _make_ocr_item("26-PIT-9087"),
            _make_ocr_item("PIT-9087"),
        ]
        result = classify_paddle_results(items, drawing_type="PID")
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == 1
        aliases = inst_tags[0].get("aliases") or []
        assert "PIT-9087" in aliases, f"Expected 'PIT-9087' in aliases, got {aliases}"

    def test_multiple_pairs_all_deduped(self):
        """Multiple prefixed/bare pairs all collapse correctly."""
        pairs = [
            ("26-PIT-9087", "PIT-9087"),
            ("26-PDI-9015", "PDI-9015"),
            ("26-TIT-9030", "TIT-9030"),
        ]
        items = []
        for prefixed, bare in pairs:
            items.append(_make_ocr_item(prefixed))
            items.append(_make_ocr_item(bare))

        result = classify_paddle_results(items, drawing_type="PID")
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == len(pairs), (
            f"Expected {len(pairs)} unique INSTRUMENT_TAGs, got {len(inst_tags)}: "
            f"{[r['tag'] for r in inst_tags]}"
        )

    def test_genuinely_different_tags_not_merged(self):
        """Tags with different loop numbers must NOT be merged."""
        items = [
            _make_ocr_item("26-PIT-9087"),
            _make_ocr_item("26-PIT-9088"),
        ]
        result = classify_paddle_results(items, drawing_type="PID")
        inst_tags = [r for r in result if r["classification"] == "INSTRUMENT_TAG"]
        assert len(inst_tags) == 2, (
            f"Expected 2 distinct INSTRUMENT_TAGs, got {len(inst_tags)}"
        )
