"""
Unit Tests for Phase 2 & Phase 3:
Canonical Observation, Candidate Models, Entity Taxonomy, and Tag Decomposition.

Validates:
1. Universal Engineering Entity Taxonomy coverage.
2. Candidate lifecycle states and roles.
3. Multi-dimensional ConfidenceVector calculation.
4. Deterministic tag decomposition:
   - Alarm suffix absorption (e.g. 26-PDI-9054-HH -> PDI-9054 + HH)
   - Control valve resolution (FV-9076 -> CONTROL_VALVE, is_valve=True, is_inst=False)
   - Motor driver sub-component separation (26-KA-901-M01 -> KA-901 + M01)
   - Equipment canonical base tags (26-KA-901 vs KA-901)
   - Line tags with explicit sizes vs area-prefixed instruments
5. CanonicalEntityRegistry multi-factor deduplication and merge provenance tracking.
6. Export adapter to UniversalEngineeringGraph maintaining backward compatibility.
"""

import pytest
from src.taxonomy import (
    EngineeringTaxonomy,
    EntityStatus,
    CandidateRole,
    DrawingRegion,
    decompose_engineering_tag,
)
from src.candidate_models import (
    ConfidenceVector,
    RawObservation,
    EntityAttribute,
    EngineeringCandidate,
    MergeProvenanceRecord,
    CanonicalEntityRegistry,
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Taxonomy & Decomposition Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_alarm_suffix_decomposition():
    """Verify alarm suffixes are absorbed as attributes rather than creating separate instruments."""
    d = decompose_engineering_tag("26-PDI-9054-HH")
    assert d.canonical_base_tag == "PDI-9054"
    assert d.area_prefix == "26"
    assert "HH" in d.alarms
    assert d.detected_taxonomy == EngineeringTaxonomy.PRESSURE_INSTRUMENT
    assert d.is_instrument is True
    assert d.is_valve is False


def test_control_valve_resolution():
    """Verify control valves are classified as valves with control function, NOT standalone instruments."""
    d = decompose_engineering_tag("26-FV-9076")
    assert d.canonical_base_tag == "FV-9076"
    assert d.detected_taxonomy == EngineeringTaxonomy.CONTROL_VALVE
    assert d.secondary_function == EngineeringTaxonomy.CONTROL_FUNCTION
    assert d.is_valve is True
    assert d.is_instrument is False


def test_psv_resolution():
    """Verify PSVs are classified as PSV valves, NOT generic instruments."""
    d = decompose_engineering_tag("26-PSV-9066A")
    assert d.canonical_base_tag == "PSV-9066A"
    assert d.detected_taxonomy == EngineeringTaxonomy.PSV
    assert d.is_valve is True
    assert d.is_instrument is False


def test_equipment_subcomponent_decomposition():
    """Verify motor drivers are decomposed as sub-components of the equipment."""
    d = decompose_engineering_tag("26-KA-901-M01")
    assert d.canonical_base_tag == "KA-901"
    assert d.sub_component == "M01"
    assert d.detected_taxonomy == EngineeringTaxonomy.MOTOR
    assert d.is_equipment is True


def test_line_tag_vs_instrument_tag():
    """Verify line tags require explicit pipe size or spec and are not confused with instruments."""
    line_tag = decompose_engineering_tag('8"-PV-26-9035-FC11S-08')
    assert line_tag.is_line is True
    assert line_tag.detected_taxonomy == EngineeringTaxonomy.LINE
    assert line_tag.sequence_number == "9035"

    inst_tag = decompose_engineering_tag("26-PIT-9077")
    assert inst_tag.is_line is False
    assert inst_tag.is_instrument is True
    assert inst_tag.canonical_base_tag == "PIT-9077"


def test_valve_classification_diversity():
    """Verify diversity of valve taxonomy: Check, Ball, Gate, Globe, Needle, Butterfly."""
    check_v = decompose_engineering_tag("26CB9131")
    assert check_v.detected_taxonomy == EngineeringTaxonomy.CHECK_VALVE
    assert check_v.is_valve is True

    gate_v = decompose_engineering_tag("26GB9178")
    assert gate_v.detected_taxonomy == EngineeringTaxonomy.GATE_VALVE
    assert gate_v.is_valve is True

    ball_v = decompose_engineering_tag("43BL9070")
    assert ball_v.detected_taxonomy == EngineeringTaxonomy.BALL_VALVE
    assert ball_v.is_valve is True


# ──────────────────────────────────────────────────────────────────────────────
# 2. ConfidenceVector & Models Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_confidence_vector_calculation():
    """Verify multi-dimensional confidence composite calculation."""
    cv = ConfidenceVector(
        detection_confidence=0.90,
        ocr_confidence=0.95,
        classification_confidence=0.85,
        entity_resolution_confidence=0.80,
    )
    # Composite: 0.90*0.15 + 0.95*0.15 + 0.85*0.30 + 0.80*0.40 = 0.135 + 0.1425 + 0.255 + 0.320 = 0.8525 -> 0.853
    assert 0.84 <= cv.composite_score <= 0.86


def test_entity_attribute_binding():
    """Verify EntityAttribute creation and non-promotion to entity."""
    attr = EntityAttribute(
        attribute_name="set_pressure",
        attribute_value="225.4 BARG",
        attribute_unit="BARG",
        confidence=0.98,
    )
    assert attr.attribute_name == "set_pressure"
    assert attr.attribute_value == "225.4 BARG"


# ──────────────────────────────────────────────────────────────────────────────
# 3. CanonicalEntityRegistry Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_registry_alarm_merging_and_provenance():
    """Verify observations of base tag and alarm suffix merge into single candidate with provenance."""
    reg = CanonicalEntityRegistry()

    # Pass 1: Base instrument
    c1 = reg.register_observation(
        source_agent="TextRecognitionAgent",
        raw_text="26-PDI-9054",
        confidence=0.95,
    )

    # Pass 2: Alarm suffix observation
    c2 = reg.register_observation(
        source_agent="TextRecognitionAgent",
        raw_text="26-PDI-9054-HH",
        confidence=0.90,
    )

    # Must resolve to the SAME candidate ID
    assert c1.candidate_id == c2.candidate_id
    assert len(reg.candidates) == 1
    
    # Must have absorbed the alarm
    primary = list(reg.candidates.values())[0]
    assert "HH" in primary.alarms
    assert "26-PDI-9054-HH" in primary.aliases

    # Must have generated an explainable merge provenance record
    assert len(reg.merge_records) == 1
    mrg = reg.merge_records[0]
    assert mrg.canonical_entity_id == primary.candidate_id
    assert mrg.canonical_tag == "26-PDI-9054"
    assert mrg.merged_tag == "26-PDI-9054-HH"
    assert mrg.merge_reason == "CANONICAL_BASE_TAG_MATCH"


def test_registry_duplicate_instrument_deduplication():
    """Verify identical base tag with and without area prefix merge into one."""
    reg = CanonicalEntityRegistry()

    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="PIT-9055")
    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="26-PIT-9055")

    assert len(reg.candidates) == 1
    primary = list(reg.candidates.values())[0]
    assert primary.canonical_base_tag == "PIT-9055"
    assert len(reg.merge_records) == 1


def test_registry_export_to_universal_graph():
    """Verify CanonicalEntityRegistry exports cleanly to UniversalEngineeringGraph."""
    reg = CanonicalEntityRegistry()

    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="26-KA-901")
    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="26-FV-9076")
    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="26-PIT-9055")
    reg.register_observation(source_agent="TextRecognitionAgent", raw_text="26-PSV-9066A")

    reg.resolve_all_candidates()
    graph = reg.to_universal_engineering_graph(drawing_type="PID", discipline="Process")

    assert len(graph.equipment) == 1
    assert graph.equipment[0].tag == "26-KA-901"

    assert len(graph.valves) == 1
    assert graph.valves[0].tag == "26-FV-9076"
    assert graph.valves[0].type == "Control Valve"

    assert len(graph.instruments) == 1
    assert graph.instruments[0].tag == "26-PIT-9055"

    assert len(graph.safety_relief_valves) == 1
    assert graph.safety_relief_valves[0].tag == "26-PSV-9066A"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Phase 4 - 8 Integration Tests (Classification, Fusion, Provenance)
# ──────────────────────────────────────────────────────────────────────────────

def test_classify_paddle_control_valve_and_alarms():
    """Verify classify_paddle_results isolates control valves and merges alarm variants."""
    from src.utils.tag_classifier import classify_paddle_results

    items = [
        {"text": "26-FV-9076", "confidence": 0.95, "center_x": 0.2, "center_y": 0.3},
        {"text": "26-PDI-9054", "confidence": 0.92, "center_x": 0.4, "center_y": 0.3},
        {"text": "26-PDI-9054-HH", "confidence": 0.90, "center_x": 0.42, "center_y": 0.31},
    ]

    res = classify_paddle_results(items, drawing_type="PID")
    res_by_tag = {r["tag"]: r for r in res}

    # 1. 26-FV-9076 classified as VALVE_TAG (not INSTRUMENT_TAG)
    assert "26-FV-9076" in res_by_tag
    assert res_by_tag["26-FV-9076"]["classification"] == "VALVE_TAG"

    # 2. 26-PDI-9054 and 26-PDI-9054-HH merged to single item with alarms
    assert "26-PDI-9054" in res_by_tag
    pdi_item = res_by_tag["26-PDI-9054"]
    assert "26-PDI-9054-HH" in pdi_item.get("aliases", [])
    assert "HH" in pdi_item.get("alarms", []) or "HH" in pdi_item.get("attributes", {}).get("alarms", "")
    assert "26-PDI-9054-HH" not in res_by_tag  # loser removed from primary found


def test_compiler_control_valve_sole_routing():
    """Verify CompilerAgent routes control valves solely to valves, never to instruments."""
    from src.agents.compiler import CompilerAgent

    ca = CompilerAgent()
    texts = [
        {"classification": "VALVE_TAG", "tag": "26-FV-9076", "value": "26-FV-9076", "attributes": {}},
        {"classification": "INSTRUMENT_TAG", "tag": "26-PIT-9055", "value": "26-PIT-9055", "attributes": {}},
    ]

    compiled_valves = ca._compile_valves(texts, [], [], [])
    compiled_insts = ca._compile_instruments(texts, [], [], [])

    # FV-9076 must be in valves as Control Valve
    v_tags = {v.tag: v for v in compiled_valves}
    assert "26-FV-9076" in v_tags
    assert v_tags["26-FV-9076"].type == "Control Valve"

    # FV-9076 must NOT be in instruments
    i_tags = {i.tag: i for i in compiled_insts}
    assert "26-FV-9076" not in i_tags
    assert "26-PIT-9055" in i_tags


def test_compiler_multi_observation_line_deduplication():
    """Verify CompilerAgent collapses multiple observations of the same line tag to 1 item."""
    from src.agents.compiler import CompilerAgent

    ca = CompilerAgent()
    texts = [
        {"classification": "LINE_TAG", "tag": '8"-PV-26-9035-FC11S-08', "value": '8"-PV-26-9035-FC11S-08', "attributes": {}},
        {"classification": "LINE_TAG", "tag": '8"-PV-26-9035-FC11S-08', "value": '8"-PV-26-9035-FC11S-08', "attributes": {}},
    ]

    compiled_lines = ca._compile_lines(texts, geom={}, relations=[])
    assert len(compiled_lines) == 1
    assert compiled_lines[0].tag == '8"-PV-26-9035-FC11S-08'
    assert compiled_lines[0].size == '8"'
    assert compiled_lines[0].spec == 'FC11S'

    # Check merge provenance record
    prov = [r for r in ca.merge_provenance if r["merge_reason"] == "MULTI_OBSERVATION_LINE_TAG"]
    assert len(prov) == 1
    assert prov[0]["entity_type"] == "LINE"


def test_compiler_provenance_json_export(tmp_path):
    """Verify CompilerAgent.run() exports MERGE_PROVENANCE.json with explainable provenance."""
    import os
    import json
    from src.agents.compiler import CompilerAgent

    ca = CompilerAgent()
    state = {
        "extracted_entities": {
            "text_elements": [
                {"classification": "EQUIPMENT_TAG", "tag": "26-KA-901", "value": "26-KA-901", "attributes": {}},
                {"classification": "EQUIPMENT_TAG", "tag": "KA-901", "value": "KA-901", "attributes": {}},
                {"classification": "VALVE_TAG", "tag": "26-CB-9131", "value": "26-CB-9131", "attributes": {}},
                {"classification": "LINE_TAG", "tag": '8"-PV-26-9035-FC11S-08', "value": '8"-PV-26-9035-FC11S-08', "attributes": {}},
                {"classification": "LINE_TAG", "tag": '8"-PV-26-9035-FC11S-08', "value": '8"-PV-26-9035-FC11S-08', "attributes": {}},
            ],
            "symbols": [
                {"symbol_type": "CHECK_VALVE", "inferred_tag": "26-CB-9131", "ymin": 0.2, "xmin": 0.2, "ymax": 0.25, "xmax": 0.25}
            ],
            "relations": [],
            "geometry": {},
        },
        "metadata": {"drawing_type": "PID", "discipline": "Piping"},
    }

    res = ca.run(state)
    assert "merge_provenance" in res
    assert len(res["merge_provenance"]) >= 2

    # Check exported MERGE_PROVENANCE.json
    prov_file = os.path.join("outputs", "MERGE_PROVENANCE.json")
    assert os.path.exists(prov_file)
    with open(prov_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    assert len(records) >= 2
    for r in records:
        assert "record_id" in r
        assert "canonical_tag" in r
        assert "merge_reason" in r

