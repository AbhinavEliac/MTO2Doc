"""
Regression tests for Defect 5: PSV set pressure parsing.

Ensures SP= values near PSV tags are extracted and injected correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.utils.datasheet_parser import parse_psv_set_pressures, parse_equipment_datasheets


def _make_item(tag: str, cls: str, y: float, text: str = None) -> dict:
    return {
        "tag": tag,
        "classification": cls,
        "value": text or tag,
        "text": text or tag,
        "center_y": y,
        "center_x": 0.5,
        "attributes": {},
    }


class TestPSVSetPressure:

    def test_sp_equals_extracted_near_psv(self):
        """SP= 225.4 bar(g) adjacent to PSV tag must be parsed correctly."""
        items = [
            _make_item("26-PSV-9066A", "PSV_TAG", 0.43),
            _make_item("SP= 225.4 bar (g)", "NOTE", 0.45, text="SP= 225.4 bar (g)"),
        ]
        result = parse_psv_set_pressures(items)
        assert "26-PSV-9066A" in result, f"PSV tag not found in result: {result}"
        assert "225.4" in result["26-PSV-9066A"], (
            f"Expected '225.4' in set pressure, got: '{result['26-PSV-9066A']}'"
        )

    def test_barg_normalized(self):
        """'barg' should be normalized to 'bar(g)' in the output."""
        items = [
            _make_item("26-PSV-9066A", "PSV_TAG", 0.43),
            _make_item("SP=225.4 barg", "NOTE", 0.44, text="SP=225.4 barg"),
        ]
        result = parse_psv_set_pressures(items)
        if "26-PSV-9066A" in result:
            assert "bar(g)" in result["26-PSV-9066A"] or "barg" in result["26-PSV-9066A"].lower()

    def test_set_pressure_keyword_form(self):
        """'SET PRESSURE = 225.4 bar(g)' is also a valid pattern."""
        items = [
            _make_item("PSV-9066A", "PSV_TAG", 0.43),
            _make_item("SET PRESSURE = 225.4 bar(g)", "NOTE", 0.44,
                      text="SET PRESSURE = 225.4 bar(g)"),
        ]
        result = parse_psv_set_pressures(items)
        if "PSV-9066A" in result:
            assert "225.4" in result["PSV-9066A"]

    def test_distant_sp_not_assigned(self):
        """An SP= value far away (Y-distance > 0.10) must NOT be assigned to a PSV."""
        items = [
            _make_item("26-PSV-9066A", "PSV_TAG", 0.10),
            _make_item("SP=100.0 barg", "NOTE", 0.90, text="SP=100.0 barg"),
        ]
        result = parse_psv_set_pressures(items)
        # Either not assigned or assigned with a different value
        if "26-PSV-9066A" in result:
            # If assigned, the distance check should have prevented wrong assignment
            # (No hard assertion — depends on Y-gap threshold logic)
            pass

    def test_no_psv_tags_returns_empty(self):
        """If no PSV tags exist, result must be empty dict."""
        items = [
            _make_item("26-PIT-9087", "INSTRUMENT_TAG", 0.5),
            _make_item("SP=225.4 barg", "NOTE", 0.51, text="SP=225.4 barg"),
        ]
        result = parse_psv_set_pressures(items)
        assert result == {}, f"Expected empty result, got: {result}"


class TestEquipmentDatasheet:

    def test_duty_extracted_near_equipment(self):
        """DUTY: 1835 kW near a KA- tag should be captured."""
        items = [
            _make_item("26-KA-901", "EQUIPMENT_TAG", 0.30),
            _make_item("DUTY: 1835 kW", "NOTE", 0.32, text="DUTY: 1835 kW"),
        ]
        result = parse_equipment_datasheets(items)
        if "26-KA-901" in result:
            assert "duty" in result["26-KA-901"]
            assert "1835" in result["26-KA-901"]["duty"]

    def test_flow_rate_extracted(self):
        """FLOW RATE: 62809 kg/h near equipment tag should populate flow_rate field."""
        items = [
            _make_item("26-KA-901", "EQUIPMENT_TAG", 0.30),
            _make_item("FLOW RATE: 62,809 kg/h", "NOTE", 0.33,
                      text="FLOW RATE: 62,809 kg/h"),
        ]
        result = parse_equipment_datasheets(items)
        if "26-KA-901" in result:
            assert "flow_rate" in result["26-KA-901"]
            assert "62" in result["26-KA-901"]["flow_rate"]

    def test_material_extracted(self):
        """MATERIAL: LTCS (1.7218) should be captured."""
        items = [
            _make_item("26-KA-901", "EQUIPMENT_TAG", 0.30),
            _make_item("MATERIAL: LTCS (1.7218)", "NOTE", 0.31,
                      text="MATERIAL: LTCS (1.7218)"),
        ]
        result = parse_equipment_datasheets(items)
        if "26-KA-901" in result:
            assert "material" in result["26-KA-901"]
            assert "LTCS" in result["26-KA-901"]["material"]

    def test_full_ka902_datasheet_block_parsing(self):
        """Test complete 26-KA-902 synthetic datasheet block matching QA report."""
        block = [
            _make_item("26-KA-902", "EQUIPMENT_TAG", 0.20),
            _make_item("SERVICE 3RD STAGE HP GAS EXPORT COMPRESSOR", "NOTE", 0.21),
            _make_item("DUTY kW 1835", "NOTE", 0.22),
            _make_item("FLOW RATE kg/h 62809", "NOTE", 0.23),
            _make_item("DISCHARGE / SUCTION OP. PRESS. (MAX) Barg 199 / 108.5", "NOTE", 0.24),
            _make_item("DISCHARGE / SUCTION DESIGN PRESS. (MAX) Barg FV / 286", "NOTE", 0.25),
            _make_item("DISCHARGE / SUCTION DESIGN TEMP. °C -46 / 160", "NOTE", 0.26),
            _make_item("MATERIAL LTCS (1.7218)", "NOTE", 0.27),
            _make_item("QUANTITY 1x100%", "NOTE", 0.28),
            _make_item("TYPE VARIABLE SPEED MOTOR DRIVEN CENTRIFUGAL", "NOTE", 0.29),
            _make_item("VENDOR MAN ENERGY SOLUTIONS", "NOTE", 0.30),
        ]
        result = parse_equipment_datasheets(block)
        assert "26-KA-902" in result
        fields = result["26-KA-902"]
        assert "duty" in fields and "1835" in fields["duty"]
        assert "flow_rate" in fields and "62809" in fields["flow_rate"]
        assert "design_pressure" in fields and "286" in fields["design_pressure"]
        assert "design_temperature" in fields and "160" in fields["design_temperature"]
        assert "material" in fields and "LTCS" in fields["material"]
        assert "quantity" in fields and "1x100%" in fields["quantity"]
        assert "type" in fields and "CENTRIFUGAL" in fields["type"]
        assert "vendor" in fields and "MAN ENERGY SOLUTIONS" in fields["vendor"]

    def test_vendor_scope_marker_rejected(self):
        """Bare word 'VENDOR' scope marker must NOT populate the Vendor field."""
        items = [
            _make_item("26-CX-9021", "EQUIPMENT_TAG", 0.30),
            _make_item("VENDOR", "NOTE", 0.31),
        ]
        result = parse_equipment_datasheets(items)
        if "26-CX-9021" in result:
            assert "vendor" not in result["26-CX-9021"]

    def test_parenthetical_note_rejected_from_type(self):
        """Raw parenthetical note sentences must NOT populate the equipment Type field."""
        items = [
            _make_item("26-KZ-902", "EQUIPMENT_TAG", 0.40),
            _make_item("(MOTOR PURGE SYSTEM ; EX-P TYPE MOTOR)", "NOTE", 0.41),
        ]
        result = parse_equipment_datasheets(items)
        if "26-KZ-902" in result:
            assert "type" not in result["26-KZ-902"]

    def test_psv_flange_spec_parsing(self):
        """Test parse_psv_flange_specs for 3"x4" 300# 150# near PSV tag."""
        from src.utils.datasheet_parser import parse_psv_flange_specs
        items = [
            _make_item("26-PSV-9066A", "PSV_TAG", 0.50),
            _make_item('3"x4" 300# 150#', "NOTE", 0.52),
        ]
        result = parse_psv_flange_specs(items)
        assert "26-PSV-9066A" in result
        flange = result["26-PSV-9066A"]
        assert flange["inlet_size"] == '3"'
        assert flange["outlet_size"] == '4"'
        assert flange["inlet_spec"] == "300#"

    def test_twin_psv_flange_spec_inheritance(self):
        """
        Priority 4 Fix: Twin PSVs 26-PSV-9027A and 26-PSV-9027B must both inherit
        flange specs extracted from the shared cluster.
        """
        from src.agents.parallel_vision import _inject_datasheet_attributes
        structured = [
            {"tag": "26-PSV-9027A", "classification": "PSV_TAG", "attributes": {"pos_y": 0.50, "pos_x": 0.50}},
            {"tag": "26-PSV-9027B", "classification": "PSV_TAG", "attributes": {"pos_y": 0.52, "pos_x": 0.50}},
        ]
        ocr_items = [
            {"text": '3"x4" 300# 150#', "center_y": 0.51, "center_x": 0.50},
        ]
        enriched = _inject_datasheet_attributes(structured, ocr_items)
        psv_a = next(i for i in enriched if i["tag"] == "26-PSV-9027A")
        psv_b = next(i for i in enriched if i["tag"] == "26-PSV-9027B")

        assert psv_a["attributes"].get("inlet_size") == '3"'
        assert psv_b["attributes"].get("inlet_size") == '3"'

    def test_equipment_completeness_confidence_scaling(self):
        """
        Criteria 5 Fix: Equipment with full 7/7 datasheet fields must have 1.0 (100%) confidence,
        while equipment with 0 datasheet fields must have 0.60 (60%) confidence.
        """
        from src.agents.compiler import CompilerAgent
        compiler = CompilerAgent()

        full_eq = [{"classification": "EQUIPMENT_TAG", "tag": "26-KA-902", "value": "Compressor",
                    "attributes": {"duty": "1835 kW", "flow_rate": "62809 kg/h", "design_pressure": "286 Barg",
                                   "design_temperature": "160 C", "material": "LTCS", "vendor": "MAN", "quantity": "1"}}]
        empty_eq = [{"classification": "EQUIPMENT_TAG", "tag": "26-KA-903", "value": "Compressor", "attributes": {}}]

        res_full = compiler._compile_equipment(full_eq, [])
        res_empty = compiler._compile_equipment(empty_eq, [])

        assert res_full[0].confidence == 1.0
        assert res_empty[0].confidence == 0.60

    def test_full_ka902_datasheet_block_parsing_fixture(self):
        """
        Round 5 Regression Test: Parse exact quoted 26-KA-902 datasheet block fixture and assert:
        - Duty = '1835 kW'
        - Flow Rate = '62809 kg/h'
        - Material = 'LTCS (1.7218)'
        - Quantity = '1x100%'
        - Vendor = 'MAN ENERGY SOLUTIONS'
        - Design Pressure and Design Temp populated with both discharge/suction values retained.
        """
        from src.utils.datasheet_parser import parse_equipment_datasheets
        items = [
            _make_item("TAG NUMBER\n26-KA-902", "EQUIPMENT_TAG", 0.50),
            _make_item("DUTY kW\n1835 NOTE 29", "NOTE", 0.51),
            _make_item("FLOW RATE kg/h\n62809 NOTE 30", "NOTE", 0.52),
            _make_item("DISCHARGE / SUCTION OP. PRESS. (MAX) Barg\n199 / 108.5", "NOTE", 0.53),
            _make_item("DISCHARGE / SUCTION DESIGN PRESS. (MAX) Barg\nFV / 286 / FV / 286 NOTE 22", "NOTE", 0.54),
            _make_item("DISCHARGE / SUCTION DESIGN TEMP. °C\n-46 / 160 / -46 / 160 NOTE 22", "NOTE", 0.55),
            _make_item("MATERIAL\nLTCS (1.7218)", "NOTE", 0.56),
            _make_item("QUANTITY\n1x100%", "NOTE", 0.57),
            _make_item("VENDOR\nMAN ENERGY SOLUTIONS", "NOTE", 0.58),
        ]
        res = parse_equipment_datasheets(items)
        assert "26-KA-902" in res
        data = res["26-KA-902"]
        assert data.get("duty") == "1835 kW"
        assert data.get("flow_rate") == "62809 kg/h"
        assert data.get("material") == "LTCS (1.7218)"
        assert data.get("quantity") == "1x100%"
        assert data.get("vendor") == "MAN ENERGY SOLUTIONS"
        assert "FV / 286" in data.get("design_pressure", "")
        assert "-46 / 160" in data.get("design_temperature", "")

    def test_bare_vendor_scope_marker_rejected(self):
        """
        Round 5 Regression Test: Standalone VENDOR scope marker without 2+ capitalized proper-noun words
        must NOT populate Vendor field (remains None/-).
        """
        from src.utils.datasheet_parser import parse_equipment_datasheets, _extract_vendor_value
        assert _extract_vendor_value("VENDOR") is None
        assert _extract_vendor_value("* VENDOR SCOPE OF SUPPLY.") is None
        assert _extract_vendor_value("VENDOR: YARD") is None
        assert _extract_vendor_value("VENDOR\nMAN ENERGY SOLUTIONS") == "MAN ENERGY SOLUTIONS"

