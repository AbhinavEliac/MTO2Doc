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

    def test_relationship_ck921_canonicalized_and_self_loop_dropped(self):
        """
        Test that CompilerAgent resolves bare tag CK-921 to master tag 26-CK-921
        and drops self-loop edges (CK-921 -> 26-CK-921).
        """
        from src.agents.compiler import CompilerAgent
        from src.models import EquipmentItem, UniversalEngineeringGraph

        compiler = CompilerAgent()
        graph = UniversalEngineeringGraph(drawing_type="PID", discipline="Piping")
        graph.equipment = [
            EquipmentItem(tag="26-CK-921", type="Check Valve", name="Check Valve", aliases=["CK-921"])
        ]

        raw_relations = [
            {"source_tag": "CK-921", "target_tag": "26-CK-921", "rel_type": "connects_to"},
            {"source_tag": "LP FLARE", "target_tag": "CK-921", "rel_type": "feeds"},
        ]

        tag_alias_map = {"26-CK-921": "26-CK-921", "CK-921": "26-CK-921", "LP FLARE": "LP FLARE"}
        compiled_rels = compiler._compile_relationships(raw_relations, tag_alias_map)

        # 1. Self-loop edge CK-921 -> 26-CK-921 must be dropped
        # 2. LP FLARE -> CK-921 must be resolved to target "26-CK-921"
        assert len(compiled_rels) == 1
        assert compiled_rels[0].source == "LP FLARE"
        assert compiled_rels[0].target == "26-CK-921"

