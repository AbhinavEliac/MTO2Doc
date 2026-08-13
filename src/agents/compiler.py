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

        # ── Defect 1 Fix: Provenance filter — drop cross-document contamination ──
        ocr_token_set = state.get("ocr_token_set", set())
        if ocr_token_set:
            from src.utils.provenance import filter_relationships_by_provenance
            all_relations, dropped = filter_relationships_by_provenance(
                all_relations, ocr_token_set
            )
            if dropped:
                examples = [f"{d.get('source_tag')}->{d.get('target_tag')}" for d in dropped[:3]]
                logger.warning(
                    f"Provenance: dropped {len(dropped)} cross-document relationship(s). "
                    f"Examples: {examples}"
                )
        else:
            logger.info("Provenance: no OCR token set in state; skipping contamination filter.")

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

        # Always compile annotations (notes, elevations, ratings)
        graph.annotations = self._compile_annotations(text_elements)

        # Defect 2 Fix: Build master tag alias lookup map across all compiled entities
        from src.utils.tag_classifier import canonicalize_tag
        tag_alias_map: Dict[str, str] = {}

        def _register(tag_str: str, aliases: Optional[List[str]] = None):
            if not tag_str:
                return
            t_up = tag_str.upper()
            c_up = canonicalize_tag(tag_str)
            tag_alias_map[t_up] = tag_str
            tag_alias_map[c_up] = tag_str
            if aliases:
                for a in aliases:
                    tag_alias_map[a.upper()] = tag_str
                    tag_alias_map[canonicalize_tag(a)] = tag_str

        for e in graph.equipment:
            _register(e.tag, getattr(e, 'aliases', None))
        for inst in graph.instruments:
            _register(inst.tag, getattr(inst, 'aliases', None))
        for v in graph.valves:
            _register(v.tag, getattr(v, 'aliases', None))
        for l in graph.lines:
            _register(l.tag, getattr(l, 'aliases', None))
        for psv in graph.safety_relief_valves:
            _register(psv.tag, getattr(psv, 'aliases', None))

        # Always compile relationships (cross-type) using master tag alias lookup
        graph.relationships = self._compile_relationships(all_relations, tag_alias_map)

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

    # ISA equipment type descriptions (CFIHOS / ISO 15926)
    _ISA_EQUIP_DESC = {
        'KA': 'Compressor', 'KB': 'Blower', 'KC': 'Compressor', 'KT': 'Turbine',
        'CP': 'Compressor', 'CM': 'Compressor', 'KZ': 'Package/Skid Unit',
        'HA': 'Heat Exchanger', 'HB': 'Heat Exchanger', 'HX': 'Heat Exchanger',
        'HE': 'Heat Exchanger', 'EA': 'Air Cooler', 'EB': 'Boiler',
        'VA': 'Vessel', 'VB': 'Vessel', 'VC': 'Vessel',
        'TK': 'Storage Tank', 'DA': 'Drum', 'DB': 'Drum',
        'CA': 'Column', 'CB': 'Column', 'R': 'Reactor',
        'PA': 'Pump', 'PB': 'Pump', 'PC': 'Pump', 'PM': 'Pump', 'PU': 'Pump',
        'GA': 'Pump', 'GB': 'Pump',
        'FA': 'Filter', 'FB': 'Filter', 'ST': 'Strainer', 'CX': 'Separator',
        'SK': 'Skid', 'PK': 'Package',
        'MA': 'Machinery', 'MB': 'Machinery', 'ME': 'Mechanical Equipment',
    }

    def _compile_equipment(self, texts: List[Dict], symbols: List[Dict]) -> List[EquipmentItem]:
        compiled = []
        seen_equip: dict = {}  # canonical key → EquipmentItem (deduplication)
        eq_tags = [t for t in texts if t["classification"] == "EQUIPMENT_TAG"]

        for eq in eq_tags:
            tag = eq["tag"]

            # Deduplicate by canonical key (strip project prefix AND trailing unit suffix)
            canon_key = re.sub(r'^\d{2,3}-', '', tag.upper())
            canon_key = re.sub(r'-[A-Z][A-Z0-9]{0,3}$', '', canon_key)

            if canon_key in seen_equip:
                if len(tag) > len(seen_equip[canon_key].tag):
                    seen_equip[canon_key].tag = tag
                continue

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            code_match = re.search(r'([A-Z]{1,3})(?=-?\d)', tag, re.IGNORECASE)
            eq_code = code_match.group(1).upper() if code_match else ""
            eq_type = self._ISA_EQUIP_DESC.get(eq_code, "Generic Equipment")
            for sym in symbols:
                if sym.get("inferred_tag") == tag and sym.get("symbol_type"):
                    eq_type = sym["symbol_type"]
                    break

            # ── Defect 5 Fix: populate datasheet fields from injected attributes ──
            attrs = eq.get("attributes") or {}
            aliases = eq.get("aliases") or []

            # Calculate dynamic completeness-based confidence
            datasheet_keys = ["design_pressure", "design_temperature", "flow_rate", "duty", "material", "vendor", "quantity"]
            populated_count = sum(1 for k in datasheet_keys if attrs.get(k))
            if populated_count > 0:
                confidence = round(0.60 + 0.40 * (populated_count / 7.0), 2)
            else:
                confidence = 0.60

            item_obj = EquipmentItem(
                tag=tag,
                name=eq["value"],
                type=attrs.get("type") or eq_type,
                description=attrs.get("service") or eq["value"],
                design_pressure=attrs.get("design_pressure"),
                design_temperature=attrs.get("design_temperature"),
                flow_rate=attrs.get("flow_rate"),
                duty=attrs.get("duty") or eq.get("rating"),
                material=attrs.get("material"),
                vendor=attrs.get("vendor"),
                quantity=attrs.get("quantity"),
                location=attrs.get("location"),
                coordinates=coords,
                aliases=aliases if aliases else None,
                confidence=confidence,
            )
            compiled.append(item_obj)
            seen_equip[canon_key] = item_obj

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

            # Calculate line center position for spatial association
            line_y, line_x = -1.0, -1.0
            if path_coords and len(path_coords) >= 1:
                try:
                    line_y = sum(float(pt[1]) for pt in path_coords if len(pt) >= 2) / float(len(path_coords))
                    line_x = sum(float(pt[0]) for pt in path_coords if len(pt) >= 2) / float(len(path_coords))
                except (ValueError, TypeError, ZeroDivisionError):
                    line_y, line_x = -1.0, -1.0
            if line_y < 0:
                for t in texts:
                    if t.get("tag") == tag or t.get("value") == tag:
                        attrs = t.get("attributes") or {}
                        line_y = float(attrs.get("pos_y", -1)) if attrs.get("pos_y") else -1.0
                        line_x = float(attrs.get("pos_x", -1)) if attrs.get("pos_x") else -1.0
                        break

            # Item 8 Fix: Parse off-page destination callouts (TO LP FLARE, TO CLOSED DRAIN) with SPATIAL PROXIMITY
            if not to_node:
                best_to_dest = None
                best_to_dist = 0.15
                for t in texts:
                    val = t.get("value") or ""
                    m_to = re.search(r'\bTO\s+([A-Z0-9\s-]+(?:FLARE|DRAIN|HEADER|UNIT|SYSTEM|ATMOSPHERE)?)\b', val, re.I)
                    if m_to:
                        dest = m_to.group(1).strip()
                        if len(dest) >= 3 and dest.upper() not in ("BE", "THE", "SUCTION", "A", "AN"):
                            attrs = t.get("attributes") or {}
                            t_y = float(attrs.get("pos_y", -1)) if attrs.get("pos_y") else -1.0
                            t_x = float(attrs.get("pos_x", -1)) if attrs.get("pos_x") else -1.0
                            if line_y >= 0 and line_x >= 0 and t_y >= 0 and t_x >= 0:
                                dist = ((line_y - t_y) ** 2 + (line_x - t_x) ** 2) ** 0.5
                                if dist < best_to_dist:
                                    best_to_dist = dist
                                    best_to_dest = dest
                if best_to_dest:
                    to_node = f"{best_to_dest} (off-page)"

            if not from_node:
                best_from_src = None
                best_from_dist = 0.15
                for t in texts:
                    val = t.get("value") or ""
                    m_from = re.search(r'\bFROM\s+([A-Z0-9\s-]+(?:FLARE|DRAIN|HEADER|UNIT|SYSTEM|VESSEL)?)\b', val, re.I)
                    if m_from:
                        src_callout = m_from.group(1).strip()
                        if len(src_callout) >= 3 and src_callout.upper() not in ("BE", "THE", "SUCTION", "A", "AN"):
                            attrs = t.get("attributes") or {}
                            t_y = float(attrs.get("pos_y", -1)) if attrs.get("pos_y") else -1.0
                            t_x = float(attrs.get("pos_x", -1)) if attrs.get("pos_x") else -1.0
                            if line_y >= 0 and line_x >= 0 and t_y >= 0 and t_x >= 0:
                                dist = ((line_y - t_y) ** 2 + (line_x - t_x) ** 2) ** 0.5
                                if dist < best_from_dist:
                                    best_from_dist = dist
                                    best_from_src = src_callout
                if best_from_src:
                    from_node = f"{best_from_src} (off-page)"

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

    # ISA 5.1 instrument type descriptions lookup
    _ISA_TYPE_DESC = {
        'PIT': 'Pressure Indicating Transmitter', 'PDT': 'Differential Pressure Transmitter',
        'PDIT': 'Differential Pressure Indicating Transmitter', 'PT': 'Pressure Transmitter',
        'PI': 'Pressure Indicator', 'PIC': 'Pressure Indicating Controller',
        'PSV': 'Pressure Safety Valve', 'PRV': 'Pressure Relief Valve',
        'PDI': 'Differential Pressure Indicator', 'PCV': 'Pressure Control Valve',
        'TIT': 'Temperature Indicating Transmitter', 'TT': 'Temperature Transmitter',
        'TI': 'Temperature Indicator', 'TIC': 'Temperature Indicating Controller',
        'TE': 'Temperature Element', 'TW': 'Thermowell', 'TCV': 'Temperature Control Valve',
        'FIT': 'Flow Indicating Transmitter', 'FT': 'Flow Transmitter',
        'FI': 'Flow Indicator', 'FE': 'Flow Element', 'FCV': 'Flow Control Valve',
        'FIC': 'Flow Indicating Controller', 'FO': 'Flow Orifice',
        'LIT': 'Level Indicating Transmitter', 'LT': 'Level Transmitter',
        'LI': 'Level Indicator', 'LG': 'Level Glass', 'LCV': 'Level Control Valve',
        'AIT': 'Analytical Indicating Transmitter', 'AT': 'Analytical Transmitter',
        'VIT': 'Vibration Indicating Transmitter', 'VT': 'Vibration Transmitter',
        'HV': 'Hand Operated Valve', 'XV': 'On-Off Valve',
        'FV': 'Flow Valve', 'PY': 'Pressure Relay/Converter', 'TY': 'Temperature Relay',
    }

    @staticmethod
    def _canonical_inst_key(tag: str) -> str:
        """Strip project prefix digits to get canonical key: 26-PIT-9077 → PIT-9077."""
        return re.sub(r'^\d{2,3}-', '', tag.upper())

    def _compile_instruments(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem]
    ) -> List[InstrumentItem]:
        compiled = []
        seen_canonical: dict = {}   # Fix 2: canonical key → InstrumentItem for deduplication
        inst_tags = [t for t in texts if t["classification"] == "INSTRUMENT_TAG"]

        for inst in inst_tags:
            tag = inst["tag"]

            # Fix 2: Deduplicate by canonical key — prefer longer (project-prefixed) tag
            canon_key = self._canonical_inst_key(tag)
            if canon_key in seen_canonical:
                # If existing is bare (shorter) and this is project-prefixed (longer), upgrade
                existing_tag = seen_canonical[canon_key].tag
                if len(tag) > len(existing_tag):
                    seen_canonical[canon_key].tag = tag
                continue  # Skip duplicate regardless

            # ISA 5.1 instrument type from function code
            type_match = re.search(r'([A-Z]{2,5})(?=-?\d)', tag)
            if not type_match:
                type_match = re.search(r'([A-Z]+)', tag)
            inst_code = type_match.group(1) if type_match else "INST"
            inst_type = self._ISA_TYPE_DESC.get(inst_code, inst_code)

            # Find coordinates for symbol bubble
            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            # Fix 5: Expanded spatial proximity for loop_id (radius 0.10 + Y-band fallback)
            image_loop_id = None
            if coords:
                cy = (coords[0] + coords[2]) / 2.0
                cx = (coords[1] + coords[3]) / 2.0
                nearby_texts = []
                yband_texts = []
                for t in texts:
                    attrs = t.get("attributes") or {}
                    tx = float(attrs.get("pos_x", -1)) if attrs.get("pos_x") is not None else -1
                    ty = float(attrs.get("pos_y", -1)) if attrs.get("pos_y") is not None else -1
                    if tx >= 0 and ty >= 0:
                        dist = math.hypot(cx - tx, cy - ty)
                        if dist < 0.10:                          # Fix 5: expanded from 0.06
                            nearby_texts.append(t.get("value", ""))
                        elif abs(ty - cy) < 0.015:               # Fix 5: same Y-band fallback
                            yband_texts.append(t.get("value", ""))

                # Search nearby first, then Y-band
                for txt in (nearby_texts + yband_texts):
                    num_match = re.search(r'(\d{3,5}[A-Z]?)', txt)
                    if num_match:
                        image_loop_id = num_match.group(1)
                        break

            if not image_loop_id:
                loop_match = re.search(r'(\d{3,5}[A-Z]?)', tag)
                image_loop_id = loop_match.group(1) if loop_match else "0000"

            loop_id = image_loop_id

            # Find associated line / equipment from relations
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

            item_obj = InstrumentItem(
                tag=tag,
                type=inst_type,
                service=service_fluid,
                location="Field",
                loop_id=loop_id,
                coordinates=coords,
            )
            compiled.append(item_obj)
            seen_canonical[canon_key] = item_obj  # register for deduplication

        return compiled


    def _compile_valves(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem]
    ) -> List[ValveItem]:
        compiled = []
        seen_canonical: dict = {}  # ── Defect 2 Fix: deduplicate by canonical key
        valve_tags = [t for t in texts if t["classification"] == "VALVE_TAG"]

        for v in valve_tags:
            tag = v["tag"]
            tag_upper = tag.upper()

            # Deduplicate — prefer the longer (project-prefixed) form
            canon_key = re.sub(r'^\d{2,3}-?', '', tag_upper)
            if canon_key in seen_canonical:
                existing_tag = seen_canonical[canon_key].tag
                if len(tag) > len(existing_tag):
                    seen_canonical[canon_key].tag = tag
                    # Merge alias
                    als = seen_canonical[canon_key].aliases or []
                    if existing_tag not in als:
                        als.append(existing_tag)
                    seen_canonical[canon_key].aliases = als
                else:
                    als = seen_canonical[canon_key].aliases or []
                    if tag not in als:
                        als.append(tag)
                    seen_canonical[canon_key].aliases = als
                continue  # skip duplicate

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

            derived_size = None
            if associated_line:
                for line in lines:
                    if line.tag == associated_line:
                        derived_size = line.size
                        break

            attrs = v.get("attributes") or {}
            rating = v.get("rating") or attrs.get("rating") or attrs.get("pressure_class")
            normal_state = attrs.get("normal_state")

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            item_obj = ValveItem(
                tag=tag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=rating,
                normal_state=normal_state,
                coordinates=coords,
                type_source="inferred_from_prefix",  # ── Defect 6 Fix
                confidence=float(v.get("confidence", 1.0)),
                aliases=v.get("aliases") or None,
            )
            compiled.append(item_obj)
            seen_canonical[canon_key] = item_obj

        return compiled

    def _compile_safety_relief_valves(self, texts: List[Dict], symbols: List[Dict]) -> List[SafetyReliefValveItem]:
        compiled = []
        psv_tags = [t for t in texts if t["classification"] == "PSV_TAG"]

        for psv in psv_tags:
            tag = psv["tag"]
            attrs = psv.get("attributes") or {}

            unit_match = re.match(r'^(\d{2})-', tag)
            unit = unit_match.group(1) if unit_match else ""

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            # ── Defect 5 Fix: use parsed set_pressure from datasheet_parser (injected into attrs)
            set_pressure = (
                attrs.get("set_pressure")
                or psv.get("rating")
                or "N/A"
            )

            compiled.append(SafetyReliefValveItem(
                tag=tag,
                type=attrs.get("valve_type", "PSV"),
                service=psv["value"],
                unit=unit,
                set_pressure=set_pressure,
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
            tag_upper = tag.upper()
            attrs = item.get("attributes") or {}

            fitting_type = "Lighting Fitting"
            if "FLOODLIGHT" in tag_upper or "FL" in tag_upper:
                fitting_type = "Floodlight"
            elif "WELLGLASS" in tag_upper or "WG" in tag_upper or "WGL" in tag_upper:
                fitting_type = "Wellglass Fitting"
            elif "HIGH" in tag_upper and "BAY" in tag_upper:
                fitting_type = "High Bay Luminaire"
            elif "EMERGENCY" in tag_upper or "EL" in tag_upper or "EML" in tag_upper:
                fitting_type = "Emergency Light"
            elif "LED" in tag_upper:
                fitting_type = "LED Fitting"
            elif "TL" in tag_upper:
                fitting_type = "Tube Light Fitting"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    if sym.get("symbol_type"):
                        fitting_type = sym["symbol_type"]
                    break

            wattage = attrs.get("wattage")
            if not wattage:
                w_match = re.search(r'(\d{2,3}\s*W\b)', tag_upper)
                if w_match:
                    wattage = w_match.group(1)

            compiled.append(LuminaireItem(
                tag=tag,
                fitting_type=attrs.get("fitting_type", fitting_type),
                wattage=wattage or "70W / 2x36W (Typ.)",
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
            panel_type = "Distribution Board"
            for prefix in ('EMDB', 'MVDB', 'LVDB', 'SMDB', 'LPDB', 'EPDB', 'MDB', 'LDB', 'MSB', 'SDB', 'PDB', 'MLP', 'ELP', 'SLP', 'MCC', 'PCC'):
                if prefix in tag_upper:
                    panel_type = prefix
                    break
            if "LIGHTING" in tag_upper:
                panel_type = "Lighting Panel"
            elif "EARTHING" in tag_upper:
                panel_type = "Earthing Main Panel"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(PanelItem(
                tag=tag,
                panel_type=attrs.get("panel_type", panel_type),
                voltage=attrs.get("voltage", "415V / 230V 3-Phase"),
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
                cable_type=attrs.get("cable_type", "XLPE/PVC Armoured"),
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
            tag_upper = tag.upper()
            attrs = item.get("attributes") or {}

            ctype = type_map.get(item["classification"], "EARTHING_COMPONENT")

            # Infer component type & material details
            material = attrs.get("material")
            size = attrs.get("size")
            resistance = attrs.get("resistance")

            if ctype == "EARTH_BAR":
                if not material:
                    material = "Tinned Copper Flat Bar" if "COPPER" in tag_upper or "CU" in tag_upper else "Tinned Copper / GI Bar"
                if not size:
                    sz_match = re.search(r'(\d{2,3}\s*[xX]\s*\d{1,2})', tag_upper)
                    size = sz_match.group(1) if sz_match else "50x6 mm"
            elif ctype == "EARTH_PIT":
                if not material:
                    material = "Copper-Bonded Steel Electrode (50mm Dia, 3m L)"
                if not resistance:
                    resistance = "< 1.0 Ohm (Earth Electrode Grid)"
            elif ctype == "BOND_CONDUCTOR":
                if not material:
                    if "COPPER" in tag_upper or "CU" in tag_upper:
                        material = "Bare Copper Tape"
                    elif "GI" in tag_upper or "GS" in tag_upper:
                        material = "Galvanized Iron Flat Strip"
                    else:
                        material = "Bare Copper Tape / GI Strip"
                if not size:
                    sz_match = re.search(r'(\d{2,3}\s*[xX]\s*\d{1,2}|\d{2,3}\s*SQMM)', tag_upper)
                    size = sz_match.group(1) if sz_match else "25x3 mm"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(EarthingItem(
                tag=tag,
                component_type=ctype,
                material=material,
                size=size,
                connected_to=attrs.get("connected_to"),
                location=attrs.get("location"),
                elevation=attrs.get("elevation"),
                resistance=resistance,
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

    def _compile_relationships(
        self, relations: List[Dict], tag_alias_map: Optional[Dict[str, str]] = None
    ) -> List[Relationship]:
        """Compile relationships with canonical tag mapping and self-loop edge filtering."""
        from src.utils.tag_classifier import canonicalize_tag
        tag_alias_map = tag_alias_map or {}
        seen_edges: set = set()
        result: List[Relationship] = []

        for r in relations:
            raw_src = r.get("source_tag") or r.get("source") or ""
            raw_tgt = r.get("target_tag") or r.get("target") or ""
            rtype = (r.get("rel_type") or r.get("type") or "").lower()
            flag = r.get("flag_reason")

            if not raw_src or not raw_tgt:
                continue

            # Defect 2 Fix: Resolve source & target to master canonical tags
            src = tag_alias_map.get(raw_src.upper()) or tag_alias_map.get(canonicalize_tag(raw_src)) or raw_src
            tgt = tag_alias_map.get(raw_tgt.upper()) or tag_alias_map.get(canonicalize_tag(raw_tgt)) or raw_tgt

            # Drop self-loop edges (e.g. 26-CK-921 -> 26-CK-921)
            if src == tgt or canonicalize_tag(src) == canonicalize_tag(tgt):
                logger.debug(f"Relationships: dropped self-loop edge '{src}' -> '{tgt}'")
                continue

            canon_edge = (canonicalize_tag(src), canonicalize_tag(tgt), rtype)
            if canon_edge in seen_edges:
                continue
            seen_edges.add(canon_edge)

            result.append(Relationship(
                source=src,
                target=tgt,
                type=rtype,
                confidence=float(r.get("confidence", 1.0)),
                attributes=r.get("attributes") or {},
                flag_reason=flag,
            ))

        return result
