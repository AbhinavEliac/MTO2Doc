"""
Universal Engineering Object Compiler.

Compiles raw parallel extractions (text, symbols, paths, relationships)
into a structured master UniversalEngineeringGraph.

Drawing-type-aware dispatch:
  - PID / PFD / ISOMETRIC  → compile lines, instruments, valves, PSVs, equipment
  - ELECTRICAL_LAYOUT       → compile luminaires, panels, cables, equipment, annotations
  - EARTHING_LAYOUT         → compile earthing components, equipment, annotations
  - SLD                     → compile panels, circuits, equipment, annotations
  - HVAC_LAYOUT             → compile equipment, annotations
  - STRUCTURAL_LAYOUT       → compile equipment, annotations
  - CABLE_SCHEDULE          → compile cables, panels, annotations
  - GENERIC                 → compile generic components and annotations

All hardcoded tag-number lookups and project-specific logic have been removed.
Properties are derived purely from extracted attributes or sensible generic defaults.
"""
import re
import math
import logging
from typing import Dict, Any, List, Optional
from src.agents.base import BaseAgent
from src.models import (
    UniversalEngineeringGraph,
    EquipmentItem, LineItem, InstrumentItem, ValveItem, SafetyReliefValveItem,
    LuminaireItem, PanelItem, CableItem, EarthingItem,
    GenericComponentItem, AnnotationItem, Relationship,
)
from src.state import GraphState

logger = logging.getLogger(__name__)

# Classification sets per category
_ELECTRICAL_CLASSIFICATIONS = {'PANEL_TAG', 'LUMINAIRE_TAG', 'CIRCUIT_TAG'}
_EARTHING_CLASSIFICATIONS = {'EARTH_BAR_TAG', 'EARTH_PIT_TAG', 'BOND_CONDUCTOR_TAG'}
_ANNOTATION_CLASSIFICATIONS = {'NOTE', 'ELEVATION_TAG', 'RATING'}
_PID_VALVE_KEYWORDS = ('GB', 'CB', 'HV', 'XV', 'CV', 'FV', 'PCV', 'FCV',
                        'TCV', 'LCV', 'MOV', 'SDV', 'BDV', 'EV', 'BV')


class CompilerAgent(BaseAgent):
    """
    Agent responsible for compiling raw parallel extractions into a structured
    master UniversalEngineeringGraph.
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Universal Engineering Object Compiler...")

        entities = state.get("extracted_entities", {})
        text_elements = entities.get("text_elements", [])
        symbols = entities.get("symbols", [])
        relations = entities.get("relations", [])
        geometry = entities.get("geometry", {})
        metadata = state.get("metadata", {})

        drawing_type = metadata.get("drawing_type", "GENERIC").upper()
        discipline = metadata.get("discipline", "Unknown")

        logger.info(f"Compiling for drawing_type='{drawing_type}', discipline='{discipline}'")
        logger.info(
            f"Input: {len(text_elements)} text elements, "
            f"{len(symbols)} symbols, {len(relations)} relations"
        )

        # Build the universal graph
        graph = UniversalEngineeringGraph(
            drawing_type=drawing_type,
            discipline=discipline,
        )

        # Run spatial line tracer & relationship harvester on complete merged entities
        from src.utils.line_tracer import trace_lines_and_connections
        raw_documents = state.get("raw_documents", [])
        pages = metadata.get("rasterized_pages", raw_documents)
        raw_image = pages[0] if pages else None

        cv_res = trace_lines_and_connections(
            image_path=raw_image,
            text_elements=text_elements,
            symbols=symbols,
            drawing_type=drawing_type,
        )

        # Merge relations & line traces
        all_relations = list(relations)
        existing_rel_keys = {(r.get("source_tag"), r.get("target_tag"), r.get("rel_type")) for r in all_relations}
        for cr in cv_res.get("relations", []):
            key = (cr.get("source_tag"), cr.get("target_tag"), cr.get("rel_type"))
            if key not in existing_rel_keys:
                existing_rel_keys.add(key)
                all_relations.append(cr)

        # Always compile relationships (cross-type)
        graph.relationships = self._compile_relationships(all_relations)

        # Always compile annotations (notes, elevations, ratings)
        graph.annotations = self._compile_annotations(text_elements)

        # Universal compilation across all detected entity types
        graph.equipment = self._compile_equipment(text_elements, symbols)
        graph.lines = self._compile_lines(text_elements, geometry, all_relations)
        graph.instruments = self._compile_instruments(text_elements, symbols, all_relations, graph.lines)
        graph.valves = self._compile_valves(text_elements, symbols, all_relations, graph.lines)
        graph.safety_relief_valves = self._compile_safety_relief_valves(text_elements, symbols)
        graph.luminaires = self._compile_luminaires(text_elements, symbols)
        graph.panels = self._compile_panels(text_elements, symbols)
        graph.cables = self._compile_cables(text_elements, symbols, relations)
        graph.earthing_components = self._compile_earthing(text_elements, symbols)
        graph.generic_components = self._compile_generic(text_elements, symbols)

        total = graph.total_items
        logger.info(
            f"Compiler produced {total} total items across all entity types. "
            f"drawing_type={drawing_type}"
        )

        return {
            "engineering_graph": graph,
            "revision_history": state.get("revision_history", []) + [{
                "action": f"Compiled {total} engineering entities into UniversalEngineeringGraph",
                "drawing_type": drawing_type,
                "items_count": total,
            }],
        }

    # ── P&ID Compilers ─────────────────────────────────────────────────────────

    def _compile_equipment(self, texts: List[Dict], symbols: List[Dict]) -> List[EquipmentItem]:
        compiled = []
        eq_tags = [t for t in texts if t["classification"] == "EQUIPMENT_TAG"]

        for eq in eq_tags:
            tag = eq["tag"]
            coords = None
            eq_type = "Generic Equipment"
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    eq_type = sym["symbol_type"]
                    break

            attrs = eq.get("attributes") or {}
            compiled.append(EquipmentItem(
                tag=tag,
                name=eq["value"],
                type=eq_type,
                description=eq["value"],
                design_pressure=attrs.get("design_pressure"),
                design_temperature=attrs.get("design_temperature"),
                flow_rate=attrs.get("flow_rate"),
                duty=attrs.get("duty") or eq.get("rating"),
                material=attrs.get("material"),
                coordinates=coords,
            ))
        return compiled

    def _compile_lines(self, texts: List[Dict], geom: Dict, relations: List[Dict]) -> List[LineItem]:
        compiled = []
        line_tags = [t for t in texts if t["classification"] == "LINE_TAG"]

        for lt in line_tags:
            tag = lt["tag"]
            # Intelligently split tag and detect whether size prefix is present
            parts = [p.strip() for p in tag.split('-') if p.strip()]

            is_size = False
            if parts:
                p0 = parts[0]
                if re.match(r'^\d', p0) or '"' in p0 or "'" in p0 or 'IN' in p0.upper() or 'MM' in p0.upper() or 'DN' in p0.upper():
                    is_size = True

            if is_size and len(parts) >= 2:
                size = parts[0]
                rem = parts[1:]
            else:
                size = ""
                rem = parts

            service = rem[0] if len(rem) > 0 else "UNK"
            system = None
            sequence = "0000"
            spec = "UNSPEC"
            insulation = None

            if len(rem) == 2:
                sequence = rem[1]
            elif len(rem) == 3:
                sequence = rem[1]
                spec = rem[2]
            elif len(rem) == 4:
                if rem[1].isdigit() and len(rem[1]) <= 3:
                    system = rem[1]
                    sequence = rem[2]
                    spec = rem[3]
                else:
                    sequence = rem[1]
                    spec = rem[2]
                    insulation = rem[3]
            elif len(rem) >= 5:
                system = rem[1]
                sequence = rem[2]
                spec = rem[3]
                insulation = rem[4]

            path_coords = None
            for trace in geom.get("traces", []):
                if trace["tag"] == tag:
                    path_coords = trace["grid_path"]
                    break

            from_node = None
            to_node = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                if rtype in ("CONNECTS_TO", "FEEDS", "INSTALLED_ON"):
                    if stag == tag:
                        to_node = ttag
                    elif ttag == tag:
                        from_node = stag

            compiled.append(LineItem(
                tag=tag,
                size=size,
                service=service,
                spec=spec,
                sequence_number=sequence,
                insulation=insulation,
                from_node=from_node,
                to_node=to_node,
                coordinates=path_coords,
            ))
        return compiled

    def _compile_instruments(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem]
    ) -> List[InstrumentItem]:
        compiled = []
        inst_tags = [t for t in texts if t["classification"] == "INSTRUMENT_TAG"]

        for inst in inst_tags:
            tag = inst["tag"]
            type_match = re.search(r'([A-Z]+)', tag)
            inst_type = type_match.group(1) if type_match else "INST"

            # Find coordinates for symbol bubble
            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            # Spatial image text assembly for loop_id:
            # Check OCR text elements positioned inside/near the instrument bubble coordinates
            image_loop_id = None
            if coords:
                cy = (coords[0] + coords[2]) / 2.0
                cx = (coords[1] + coords[3]) / 2.0
                nearby_texts = []
                for t in texts:
                    attrs = t.get("attributes") or {}
                    tx = float(attrs.get("pos_x", -1)) if attrs.get("pos_x") is not None else -1
                    ty = float(attrs.get("pos_y", -1)) if attrs.get("pos_y") is not None else -1
                    if tx >= 0 and ty >= 0:
                        dist = math.hypot(cx - tx, cy - ty)
                        if dist < 0.06:
                            nearby_texts.append(t.get("value", ""))

                for txt in nearby_texts:
                    num_match = re.search(r'(\d{3,5}[A-Z]?)', txt)
                    if num_match:
                        image_loop_id = num_match.group(1)
                        break

            if not image_loop_id:
                loop_match = re.search(r'(\d{3,5}[A-Z]?)', tag)
                image_loop_id = loop_match.group(1) if loop_match else "0000"

            loop_id = image_loop_id

            # Case-insensitive relation check for host line or equipment
            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                if stag == tag and rtype in ("MONITORS", "INSTALLED_ON"):
                    associated_line = ttag
                    break
                elif ttag == tag and rtype in ("MONITORS", "INSTALLED_ON"):
                    associated_line = stag
                    break

            service_fluid = None
            if associated_line:
                for line in lines:
                    if line.tag == associated_line:
                        service_fluid = f"{line.service} ({line.tag})"
                        break
                if not service_fluid:
                    service_fluid = associated_line

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(InstrumentItem(
                tag=tag,
                type=inst_type,
                service=service_fluid,
                location="Field",
                loop_id=loop_id,
                coordinates=coords,
            ))
        return compiled

    def _compile_valves(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem]
    ) -> List[ValveItem]:
        compiled = []
        valve_tags = [t for t in texts if t["classification"] == "VALVE_TAG"]

        for v in valve_tags:
            tag = v["tag"]
            tag_upper = tag.upper()

            v_type = "Valve"
            if "GB" in tag_upper or "GATE" in tag_upper:
                v_type = "Gate Valve"
            elif "CB" in tag_upper or "CHECK" in tag_upper:
                v_type = "Check Valve"
            elif "BALL" in tag_upper or "BV" in tag_upper:
                v_type = "Ball Valve"
            elif "GLOBE" in tag_upper or "GLV" in tag_upper:
                v_type = "Globe Valve"
            elif "NEEDLE" in tag_upper or "NV" in tag_upper:
                v_type = "Needle Valve"
            elif "BUTTERFLY" in tag_upper or "BFV" in tag_upper:
                v_type = "Butterfly Valve"
            elif tag_upper.startswith(('HV', 'XV', 'CV', 'FCV', 'PCV', 'TCV', 'LCV')):
                v_type = "Control Valve"
            elif tag_upper.startswith(('MOV', 'SDV', 'BDV', 'EV')):
                v_type = "On-Off Valve"

            # Case-insensitive relation check for host line
            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                if stag == tag and rtype in ("INSTALLED_ON", "CONNECTS_TO", "MONITORS"):
                    associated_line = ttag
                    break
                elif ttag == tag and rtype in ("INSTALLED_ON", "CONNECTS_TO", "MONITORS"):
                    associated_line = stag
                    break

            # Derive size from the associated line
            derived_size = None
            if associated_line:
                for line in lines:
                    if line.tag == associated_line:
                        derived_size = line.size
                        break
            if not derived_size:
                derived_size = None  # Unknown — don't fabricate

            # Rating from attrs
            attrs = v.get("attributes") or {}
            rating = v.get("rating") or attrs.get("rating") or attrs.get("pressure_class")

            # Normal state from attrs
            normal_state = attrs.get("normal_state")

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(ValveItem(
                tag=tag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=rating,
                normal_state=normal_state,
                coordinates=coords,
            ))
        return compiled

    def _compile_safety_relief_valves(self, texts: List[Dict], symbols: List[Dict]) -> List[SafetyReliefValveItem]:
        compiled = []
        psv_tags = [t for t in texts if t["classification"] == "PSV_TAG"]

        for psv in psv_tags:
            tag = psv["tag"]
            attrs = psv.get("attributes") or {}

            # Infer unit prefix from tag (e.g. "26" from "26-PSV-9066A")
            unit_match = re.match(r'^(\d{2})-', tag)
            unit = unit_match.group(1) if unit_match else ""

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(SafetyReliefValveItem(
                tag=tag,
                type=attrs.get("valve_type", "PSV"),
                service=psv["value"],
                unit=unit,
                set_pressure=psv.get("rating") or attrs.get("set_pressure", "N/A"),
                inlet_size=attrs.get("inlet_size", "N/A"),
                outlet_size=attrs.get("outlet_size", "N/A"),
                inlet_spec=attrs.get("inlet_spec", "N/A"),
                relief_destination=attrs.get("relief_destination", "N/A"),
                remarks=attrs.get("remarks"),
                coordinates=coords,
            ))
        return compiled

    # ── Electrical Layout Compilers ────────────────────────────────────────────

    def _compile_luminaires(self, texts: List[Dict], symbols: List[Dict]) -> List[LuminaireItem]:
        compiled = []
        items = [t for t in texts if t["classification"] == "LUMINAIRE_TAG"]

        for item in items:
            tag = item["tag"]
            attrs = item.get("attributes") or {}

            coords = None
            fitting_type = "Luminaire"
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    fitting_type = sym.get("symbol_type", "Luminaire")
                    break

            compiled.append(LuminaireItem(
                tag=tag,
                fitting_type=attrs.get("fitting_type", fitting_type),
                wattage=attrs.get("wattage"),
                circuit=attrs.get("circuit"),
                panel=attrs.get("panel"),
                elevation=attrs.get("elevation"),
                location=attrs.get("location"),
                coordinates=coords,
            ))
        return compiled

    def _compile_panels(self, texts: List[Dict], symbols: List[Dict]) -> List[PanelItem]:
        compiled = []
        items = [t for t in texts if t["classification"] == "PANEL_TAG"]

        for item in items:
            tag = item["tag"]
            attrs = item.get("attributes") or {}

            # Infer panel type from tag
            tag_upper = tag.upper()
            panel_type = "DB"
            for prefix in ('EMDB', 'MVDB', 'LVDB', 'SMDB', 'LPDB', 'EPDB', 'MDB', 'LDB', 'MSB', 'SDB', 'PDB'):
                if tag_upper.startswith(prefix):
                    panel_type = prefix
                    break

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(PanelItem(
                tag=tag,
                panel_type=attrs.get("panel_type", panel_type),
                voltage=attrs.get("voltage"),
                capacity_kva=attrs.get("capacity_kva"),
                feeder_from=attrs.get("feeder_from"),
                location=attrs.get("location"),
                description=item["value"],
                coordinates=coords,
            ))
        return compiled

    def _compile_cables(
        self, texts: List[Dict], symbols: List[Dict], relations: List[Dict]
    ) -> List[CableItem]:
        compiled = []
        items = [t for t in texts if t["classification"] in ("CIRCUIT_TAG", "CABLE_TAG")]

        for item in items:
            tag = item["tag"]
            attrs = item.get("attributes") or {}

            # Look up relationships for from/to
            from_panel = None
            to_equip = None
            for rel in relations:
                if rel["source_tag"] == tag and rel["rel_type"] in ("FEEDS", "CONNECTS_TO"):
                    to_equip = rel["target_tag"]
                elif rel["target_tag"] == tag and rel["rel_type"] in ("FEEDS", "CONNECTS_TO"):
                    from_panel = rel["source_tag"]

            compiled.append(CableItem(
                tag=tag,
                cable_type=attrs.get("cable_type"),
                size_mm2=attrs.get("size_mm2"),
                cores=attrs.get("cores"),
                from_panel=from_panel or attrs.get("from_panel"),
                to_equipment=to_equip or attrs.get("to_equipment"),
                length_m=attrs.get("length_m"),
                route=attrs.get("route"),
            ))
        return compiled

    # ── Earthing Layout Compilers ──────────────────────────────────────────────

    def _compile_earthing(self, texts: List[Dict], symbols: List[Dict]) -> List[EarthingItem]:
        compiled = []
        earth_items = [
            t for t in texts
            if t["classification"] in ('EARTH_BAR_TAG', 'EARTH_PIT_TAG', 'BOND_CONDUCTOR_TAG')
        ]

        type_map = {
            'EARTH_BAR_TAG': 'EARTH_BAR',
            'EARTH_PIT_TAG': 'EARTH_PIT',
            'BOND_CONDUCTOR_TAG': 'BOND_CONDUCTOR',
        }

        for item in earth_items:
            tag = item["tag"]
            attrs = item.get("attributes") or {}

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(EarthingItem(
                tag=tag,
                component_type=type_map.get(item["classification"], "EARTHING_COMPONENT"),
                material=attrs.get("material"),
                size=attrs.get("size"),
                connected_to=attrs.get("connected_to"),
                location=attrs.get("location"),
                elevation=attrs.get("elevation"),
                resistance=attrs.get("resistance"),
                coordinates=coords,
            ))
        return compiled

    # ── Generic / Annotation Compilers ────────────────────────────────────────

    def _compile_generic(self, texts: List[Dict], symbols: List[Dict]) -> List[GenericComponentItem]:
        compiled = []
        # Anything with a tag that isn't already handled by a specific compiler
        generic_items = [
            t for t in texts
            if t["classification"] in ('EQUIPMENT_TAG', 'GENERIC_TAG')
        ]

        for item in generic_items:
            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == item["tag"]:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(GenericComponentItem(
                tag=item["tag"],
                classification=item["classification"],
                description=item.get("value"),
                attributes=item.get("attributes"),
                coordinates=coords,
            ))
        return compiled

    def _compile_annotations(self, texts: List[Dict]) -> List[AnnotationItem]:
        compiled = []
        ann_items = [t for t in texts if t["classification"] in _ANNOTATION_CLASSIFICATIONS]

        type_map = {
            'NOTE': 'NOTE',
            'ELEVATION_TAG': 'ELEVATION',
            'RATING': 'RATING',
        }

        for item in ann_items:
            attrs = item.get("attributes") or {}
            compiled.append(AnnotationItem(
                text=item["value"],
                annotation_type=type_map.get(item["classification"], "NOTE"),
                position_x=float(attrs.get("pos_x", 0)) if attrs.get("pos_x") else None,
                position_y=float(attrs.get("pos_y", 0)) if attrs.get("pos_y") else None,
            ))
        return compiled

    def _compile_relationships(self, relations: List[Dict]) -> List[Relationship]:
        return [
            Relationship(
                source=r["source_tag"],
                target=r["target_tag"],
                type=r["rel_type"].lower(),
                attributes={},
            )
            for r in relations
        ]
