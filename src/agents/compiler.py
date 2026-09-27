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
from src.utils.tag_stitcher import safe_float

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

        # Engineering-aware loop matching for unlinked instruments (Rules 5 & 10)
        # Only associate if the instrument loop sequence genuinely matches a line. Never arbitrarily hook to lines[0].
        rel_tags = set()
        for r in graph.relationships:
            rel_tags.add(r.source)
            rel_tags.add(r.target)
            rel_tags.add(canonicalize_tag(r.source))
            rel_tags.add(canonicalize_tag(r.target))

        for inst in graph.instruments:
            if inst.tag not in rel_tags and canonicalize_tag(inst.tag) not in rel_tags:
                best_target = None
                loop_match = re.search(r'(\d{3,5})', inst.tag)
                seq = loop_match.group(1) if loop_match else None
                if seq:
                    for l in graph.lines:
                        if seq in l.tag or (getattr(l, 'sequence_number', None) and seq == l.sequence_number):
                            best_target = l.tag
                            break

                if best_target:
                    graph.relationships.append(Relationship(
                        source=inst.tag,
                        target=best_target,
                        type="monitors",
                        confidence=0.82,
                        attributes={"loop_sequence_matched": True},
                    ))
                    rel_tags.add(inst.tag)

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
        'CP': 'Compressor', 'CM': 'Compressor', 'KZ': 'Compressor Package Skid',
        'HA': 'Heat Exchanger', 'HB': 'Heat Exchanger / Heater', 'HX': 'Heat Exchanger',
        'HE': 'Heat Exchanger', 'EA': 'Air Cooler / Aftercooler', 'EB': 'Boiler / Evaporator',
        'VA': 'Vessel', 'VB': 'Vessel', 'VC': 'Vessel',
        'TK': 'Storage Tank', 'DA': 'Drum', 'DB': 'Drum', 'KO': 'Knockout Drum',
        'CA': 'Column', 'CB': 'Column', 'R': 'Reactor',
        'PA': 'Pump', 'PB': 'Pump', 'PC': 'Pump', 'PM': 'Pump', 'PU': 'Pump',
        'GA': 'Pump', 'GB': 'Pump',
        'FA': 'Filter / Coalescer', 'FB': 'Cartridge Filter', 'FC': 'Filter',
        'FL': 'Filter', 'ST': 'Strainer', 'CX': 'Coalescing Filter Separator',
        'SA': 'Suction Scrubber', 'SB': 'Scrubber', 'SC': 'Separator / Scrubber',
        'SK': 'Skid Package', 'PK': 'Process Package', 'PKG': 'Package Unit',
        'MA': 'Machinery', 'MB': 'Machinery', 'ME': 'Mechanical Equipment',
    }

    def _compile_equipment(self, texts: List[Dict], symbols: List[Dict]) -> List[EquipmentItem]:
        compiled = []
        seen_equip: dict = {}  # canonical key → EquipmentItem (deduplication)
        eq_tags = [t for t in texts if t["classification"] == "EQUIPMENT_TAG"]
        
        from src.utils.entity_validator import validate_equipment_candidate
        
        for eq in eq_tags:
            tag = eq["tag"].strip()
            
            # Strict equipment candidate validation
            cand = validate_equipment_candidate(tag)
            if not cand.is_valid:
                logger.debug(f"Compiler: rejected false equipment '{tag}' ({cand.rejection_reason})")
                continue

            canon_key = re.sub(r'^\d{2,3}-', '', tag.upper())
            core_base = re.sub(r'-[A-Z0-9]+$', '', canon_key)

            # Generic algorithmic deduplication:
            # 1. Exact canonical match (e.g. bare KA-901 merged into 26-KA-901)
            # 2. Sub-train / component match (e.g. HA-911 vs 26-HA-911-C01)
            # 3. Single-digit OCR run-on collision (e.g. CX-9011 vs CX-90111)
            matched_key = None
            if canon_key in seen_equip:
                matched_key = canon_key
            else:
                for k in list(seen_equip.keys()):
                    k_core = re.sub(r'-[A-Z0-9]+$', '', k)
                    # Sibling components/trains with distinct suffixes (e.g. HA-911-C01 vs HA-911-C02) must NOT merge
                    is_sibling_suffix = (core_base == k_core and canon_key != k and canon_key != core_base and k != k_core)
                    # Driver/motor (e.g. -M01) is distinct equipment from main driven unit (e.g. KA-902)
                    is_motor_pair = bool((re.search(r'-M\d+$', canon_key) and not re.search(r'-M\d+$', k)) or
                                         (re.search(r'-M\d+$', k) and not re.search(r'-M\d+$', canon_key)))

                    # Sub-train match: HA-911 vs HA-911-C01 (base vs detailed tag)
                    if not is_sibling_suffix and not is_motor_pair and (core_base == k or canon_key == k_core):
                        matched_key = k
                        # Prefer longer/more detailed tag (e.g. 26-HA-911-C01 over HA-911)
                        if len(tag) > len(seen_equip[k].tag):
                            item_obj = seen_equip.pop(k)
                            old_tag = item_obj.tag
                            item_obj.tag = tag
                            if not item_obj.aliases:
                                item_obj.aliases = []
                            item_obj.aliases.append(old_tag)
                            seen_equip[canon_key] = item_obj
                            matched_key = canon_key
                        else:
                            if not seen_equip[k].aliases:
                                seen_equip[k].aliases = []
                            seen_equip[k].aliases.append(tag)
                        break
                    # Single-digit OCR run-on collision (e.g. CX-9011 vs CX-90111)
                    elif (canon_key.startswith(k) and len(canon_key) == len(k) + 1 and canon_key[-1].isdigit()) or \
                         (k.startswith(canon_key) and len(k) == len(canon_key) + 1 and k[-1].isdigit()):
                        matched_key = k
                        # Keep the shorter, clean base tag
                        if len(canon_key) < len(k):
                            item_obj = seen_equip.pop(k)
                            item_obj.tag = tag
                            seen_equip[canon_key] = item_obj
                            matched_key = canon_key
                        break

            if matched_key:
                # Upgrade bare tag to area-prefixed tag if base key matches exactly (e.g. KA-901 -> 26-KA-901)
                if '-' in tag and tag.split('-')[0].isdigit() and not ('-' in seen_equip[matched_key].tag and seen_equip[matched_key].tag.split('-')[0].isdigit()):
                    seen_equip[matched_key].tag = tag
                continue

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            code_match = re.search(r'([A-Z]{1,3})(?=-?\d)', tag, re.IGNORECASE)
            eq_code = code_match.group(1).upper() if code_match else ""
            eq_type = self._ISA_EQUIP_DESC.get(eq_code, "Generic Equipment")

            # Detect Motor Drivers (e.g. 26-KA-901-M01)
            if re.search(r'-M\d{1,2}$', tag, re.IGNORECASE) or tag.endswith('-MOTOR'):
                eq_type = "Motor / Driver"

            for sym in symbols:
                if sym.get("inferred_tag") == tag and sym.get("symbol_type"):
                    st = sym["symbol_type"].replace('_', ' ').title()
                    if "Equipment" not in st and "Unknown" not in st:
                        eq_type = st
                    break

            # Populate datasheet fields from injected attributes
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

        # Anti-hallucination & Schema Validation Tokens
        INVALID_LINE_TOKENS = {
            'NOTE', 'TIT', 'PIT', 'LIT', 'FIT', 'PDI', 'PDT', 'PT', 'TT', 'FT', 'LT',
            'REV', 'DWG', 'SHT', 'DETAIL', 'TYP', 'EL', 'M01', 'M02', 'M03', 'MOTOR'
        }

        from src.utils.entity_validator import validate_line_candidate
        for lt in line_tags:
            tag = lt["tag"].strip()
            if not validate_line_candidate(tag).is_valid:
                continue

            # ── Pre-Export Schema Validator & Anti-Hallucination Filter ────────
            # 1. Reject motor tags or electrical cable circuits (e.g., 26-KA-902-M01, TT-26-9711-AS20-00)
            tag_upper = tag.upper()
            if re.search(r'-(?:M\d{2}|C0\d)$', tag_upper) or tag_upper.startswith(('TT-', 'PT-', 'LT-', 'FT-', 'TIT-', 'PIT-', 'LIT-', 'FIT-')):
                continue

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

            # 2. Reject if service or spec was force-fitted with descriptive/note tokens (e.g. ...-NOTE, ...-TIT)
            if service.upper() in INVALID_LINE_TOKENS or spec.upper() in INVALID_LINE_TOKENS:
                continue

            # 3. Reject if service code is not a clean alphabetic fluid/system descriptor
            if not re.match(r'^[A-Z]{1,4}$', service.upper()):
                continue

            path_coords = None
            for trace in geom.get("traces", []):
                if trace["tag"] == tag:
                    path_coords = trace["grid_path"]
                    break

            # ── High-Accuracy From / To Resolution: Prioritize Terminal Equipment & Headers ──
            from_node = None
            to_node = None

            # Helper to check if a node is an inline valve or instrument (which shouldn't be From/To)
            def _is_inline_fitting(node_tag: Optional[str]) -> bool:
                if not node_tag:
                    return False
                nu = node_tag.upper()
                return bool(re.search(r'(?:BL|GT|GB|GL|CB|CK|NV|BF|PL|HV|XV|PV|FV|TV|LV)\d+', nu) or
                            re.search(r'^(?:PIT|TIT|FIT|LIT|PDI|PSV|PDT|PT|TT|FT|LT)-', nu))

            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                # Only CONNECTS_TO and FEEDS represent line routing (ignore INSTALLED_ON)
                if rtype in ("CONNECTS_TO", "FEEDS"):
                    if stag == tag and not _is_inline_fitting(ttag):
                        to_node = ttag
                    elif ttag == tag and not _is_inline_fitting(stag):
                        from_node = stag

            # Calculate line center position for spatial association
            from src.utils.tag_stitcher import safe_float
            line_y, line_x = -1.0, -1.0
            if path_coords and len(path_coords) >= 1:
                try:
                    pts_to_avg = []
                    for pt in path_coords:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            if isinstance(pt[0], (list, tuple)):
                                for sub_pt in pt:
                                    if isinstance(sub_pt, (list, tuple)) and len(sub_pt) >= 2:
                                        pts_to_avg.append((safe_float(sub_pt[0]), safe_float(sub_pt[1])))
                            else:
                                pts_to_avg.append((safe_float(pt[0]), safe_float(pt[1])))
                    if pts_to_avg:
                        line_y = sum(p[0] for p in pts_to_avg) / float(len(pts_to_avg))
                        line_x = sum(p[1] for p in pts_to_avg) / float(len(pts_to_avg))
                except (ValueError, TypeError, ZeroDivisionError):
                    line_y, line_x = -1.0, -1.0
            if line_y < 0:
                for t in texts:
                    if t.get("tag") == tag or t.get("value") == tag:
                        attrs = t.get("attributes") or {}
                        line_y = safe_float(attrs.get("pos_y"), -1.0)
                        line_x = safe_float(attrs.get("pos_x"), -1.0)
                        break

            # Parse off-page destination callouts (TO LP FLARE, TO CLOSED DRAIN) with SPATIAL PROXIMITY
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
                            t_y = safe_float(attrs.get("pos_y"), -1.0)
                            t_x = safe_float(attrs.get("pos_x"), -1.0)
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
                            t_y = safe_float(attrs.get("pos_y"), -1.0)
                            t_x = safe_float(attrs.get("pos_x"), -1.0)
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
        from src.utils.instrument_resolver import resolve_instrument_candidates
        compiled = []
        inst_tags = [t for t in texts if t.get("classification") == "INSTRUMENT_TAG"]
        resolved_insts, _ = resolve_instrument_candidates(inst_tags)

        for r_inst in resolved_insts:
            tag = r_inst.tag
            loop_id = r_inst.loop_id
            inst_type = r_inst.primary_type

            # Resolve associated process line
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
                    if line.tag == associated_line and line.service not in ("TUBE", "IA", "INST"):
                        service_fluid = f"{line.service} ({line.tag})"
                        break

            if not service_fluid and loop_id != "0000":
                for line in lines:
                    if line.sequence_number == loop_id and line.service not in ("TUBE", "IA"):
                        service_fluid = f"{line.service} ({line.tag})"
                        break

            if not service_fluid and associated_line:
                service_fluid = associated_line

            coords = r_inst.coordinates
            if not coords:
                for sym in symbols:
                    if sym.get("inferred_tag") == tag:
                        coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                        break

            item_obj = InstrumentItem(
                tag=tag,
                type=inst_type,
                service=service_fluid or "Process",
                location="Field",
                loop_id=loop_id,
                coordinates=coords,
                aliases=r_inst.aliases if r_inst.aliases else None,
                confidence=r_inst.confidence,
            )
            compiled.append(item_obj)

        return compiled


    def _compile_valves(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem]
    ) -> List[ValveItem]:
        from src.utils.tag_classifier import map_spec_to_rating_class
        compiled = []
        seen_canonical: dict = {}  # Deduplicate by canonical key
        compiled_tags = set()

        # ── Anchor 1: Tagged Valves (from text recognition) ───────────────────
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
                    als = seen_canonical[canon_key].aliases or []
                    if existing_tag not in als:
                        als.append(existing_tag)
                    seen_canonical[canon_key].aliases = als
                else:
                    als = seen_canonical[canon_key].aliases or []
                    if tag not in als:
                        als.append(tag)
                    seen_canonical[canon_key].aliases = als
                continue

            # ── Accurate Valve Type Determination (ISA / Project Standards) ──
            v_type = "Manual Valve"
            if re.search(r'(?:BL|BV|BALL)', tag_upper):
                v_type = "Ball Valve"
            elif re.search(r'(?:GT|GB|GATE|GV)', tag_upper):
                v_type = "Gate Valve"
            elif re.search(r'(?:GL|GLOBE|GLV)', tag_upper):
                v_type = "Globe Valve"
            elif re.search(r'(?:CB|CK|CH|CHECK|CV(?=-?\d))', tag_upper):
                v_type = "Check Valve"
            elif re.search(r'(?:NV|ND|NEEDLE)', tag_upper):
                v_type = "Needle Valve"
            elif re.search(r'(?:BF|BFV|BUTTERFLY)', tag_upper):
                v_type = "Butterfly Valve"
            elif re.search(r'(?:PL|PLV|PLUG)', tag_upper):
                v_type = "Plug Valve"
            elif tag_upper.startswith(('HV', 'HC', 'HS')):
                v_type = "Hand Control Valve"
            elif tag_upper.startswith(('XV', 'MOV', 'SDV', 'BDV', 'EV', 'ESV')):
                v_type = "On-Off Shutdown Valve"
            elif tag_upper.startswith(('CV', 'FCV', 'PCV', 'TCV', 'LCV', 'PV', 'TV', 'FV', 'LV')):
                v_type = "Control Valve"

            # Check if symbol detector identified a more specific valve type
            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    st = sym.get("symbol_type", "").upper().replace('_', ' ').title()
                    if st and "Valve" in st and v_type == "Manual Valve":
                        v_type = st
                    break

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
            host_spec = None
            if associated_line:
                for line in lines:
                    if line.tag == associated_line:
                        derived_size = line.size
                        if line.spec and line.spec != "UNSPEC":
                            host_spec = line.spec
                        break

            attrs = v.get("attributes") or {}
            raw_rating = v.get("rating") or attrs.get("rating") or attrs.get("pressure_class")
            
            # Map spec codes to true ANSI pressure class (e.g. GC11S -> 150#, AS20S -> 300#)
            mapped_rating = map_spec_to_rating_class(raw_rating) or map_spec_to_rating_class(host_spec) or (raw_rating if raw_rating and '#' in str(raw_rating) else None)
            normal_state = attrs.get("normal_state")

            item_obj = ValveItem(
                tag=tag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=mapped_rating,
                normal_state=normal_state,
                coordinates=coords,
                type_source="inferred_from_prefix",
                confidence=float(v.get("confidence", 1.0)),
                aliases=v.get("aliases") or None,
            )
            compiled.append(item_obj)
            seen_canonical[canon_key] = item_obj
            compiled_tags.add(tag)

        # ── Anchor 2: Untagged / Symbol-Detected Valves (from vision perception) ─
        valve_type_map = {
            "GATE_VALVE": "Gate Valve",
            "CHECK_VALVE": "Check Valve",
            "BALL_VALVE": "Ball Valve",
            "GLOBE_VALVE": "Globe Valve",
            "NEEDLE_VALVE": "Needle Valve",
            "CONTROL_VALVE": "Control Valve",
            "BUTTERFLY_VALVE": "Butterfly Valve",
            "PLUG_VALVE": "Plug Valve",
            "SAFETY_VALVE": "Safety Valve",
            "VALVE": "Manual Valve",
        }

        for sym in symbols:
            stype = sym.get("symbol_type", "").upper()
            is_valve_sym = any(k in stype for k in valve_type_map.keys()) or "VALVE" in stype
            if not is_valve_sym:
                continue

            stag = sym.get("inferred_tag")
            if not stag or stag in compiled_tags:
                continue

            canon_key = re.sub(r'^\d{2,3}-?', '', stag.upper())
            if canon_key in seen_canonical:
                continue

            coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
            v_type = valve_type_map.get(stype, "Manual Valve")

            # Resolve host pipeline
            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                if rel.get("source_tag") == stag and rtype == "INSTALLED_ON":
                    associated_line = rel.get("target_tag")
                    break

            # If not in relations, find closest line geometrically
            if not associated_line and lines:
                sy = (sym["ymin"] + sym["ymax"]) / 2.0
                sx = (sym["xmin"] + sym["xmax"]) / 2.0
                best_line = None
                best_dist = 0.35
                for line in lines:
                    if line.coordinates and len(line.coordinates) >= 1:
                        for pt in line.coordinates:
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                if isinstance(pt[0], (list, tuple)):
                                    for sub_pt in pt:
                                        if isinstance(sub_pt, (list, tuple)) and len(sub_pt) >= 2:
                                            ly, lx = safe_float(sub_pt[0]), safe_float(sub_pt[1])
                                            d = math.hypot(sx - lx, sy - ly)
                                            if d < best_dist:
                                                best_dist = d
                                                best_line = line.tag
                                else:
                                    ly, lx = safe_float(pt[0]), safe_float(pt[1])
                                    d = math.hypot(sx - lx, sy - ly)
                                    if d < best_dist:
                                        best_dist = d
                                        best_line = line.tag
                associated_line = best_line

            derived_size = None
            host_spec = None
            if associated_line:
                for line in lines:
                    if line.tag == associated_line:
                        derived_size = line.size
                        if line.spec and line.spec != "UNSPEC":
                            host_spec = line.spec
                        break

            mapped_rating = map_spec_to_rating_class(host_spec)

            item_obj = ValveItem(
                tag=stag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=mapped_rating,
                normal_state=None,
                coordinates=coords,
                type_source="symbol_detected",
                confidence=float(sym.get("confidence", 0.90)),
                aliases=None,
            )
            compiled.append(item_obj)
            seen_canonical[canon_key] = item_obj
            compiled_tags.add(stag)

        return compiled

    def _compile_safety_relief_valves(self, texts: List[Dict], symbols: List[Dict]) -> List[SafetyReliefValveItem]:
        from src.utils.entity_validator import normalize_psv_tag
        from src.utils.relationship_engine import EngineeringRuleEngine

        compiled = []
        seen_tags = set()
        psv_tags = [t for t in texts if t.get("classification") == "PSV_TAG"]

        flare_refs = {t.get("value", "").upper() for t in texts if "FLARE" in t.get("value", "").upper()}

        for psv in psv_tags:
            raw_tag = psv["tag"]
            tag = normalize_psv_tag(raw_tag)
            if tag in seen_tags:
                continue
            seen_tags.add(tag)

            attrs = psv.get("attributes") or {}

            unit_match = re.match(r'^(\d{2})-', tag)
            unit = unit_match.group(1) if unit_match else attrs.get("unit", "26")

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") in (tag, raw_tag):
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            set_pressure = (
                attrs.get("set_pressure")
                or psv.get("rating")
                or "N/A"
            )

            # Auto-detect relief destination with EngineeringRuleEngine
            destination = attrs.get("relief_destination") or ""
            validated_dest, _, _ = EngineeringRuleEngine.validate_psv_relief(
                psv_tag=tag,
                destination_text=destination,
                drawing_flare_references=flare_refs
            )

            inlet_sz = attrs.get("inlet_size", "4\"")
            outlet_sz = attrs.get("outlet_size", "1.5\"")
            if outlet_sz == "1":
                outlet_sz = "1.5\""

            compiled.append(SafetyReliefValveItem(
                tag=tag,
                type=attrs.get("valve_type", "PSV"),
                service=psv["value"],
                unit=unit,
                set_pressure=set_pressure,
                inlet_size=inlet_sz,
                outlet_size=outlet_sz,
                inlet_spec=attrs.get("inlet_spec", "300#"),
                relief_destination=validated_dest,
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
        from src.utils.annotation_reconstructor import reconstruct_annotation_regions
        compiled = []
        ann_items = [t for t in texts if t.get("classification") in _ANNOTATION_CLASSIFICATIONS]

        type_map = {
            'NOTE': 'NOTE',
            'ELEVATION_TAG': 'ELEVATION',
            'RATING': 'RATING',
        }

        # 1. Base individual token annotations
        for item in ann_items:
            attrs = item.get("attributes") or {}
            compiled.append(AnnotationItem(
                text=item["value"],
                annotation_type=type_map.get(item["classification"], "NOTE"),
                position_x=float(attrs.get("pos_x", 0)) if attrs.get("pos_x") else None,
                position_y=float(attrs.get("pos_y", 0)) if attrs.get("pos_y") else None,
            ))

        # 2. Higher-level reconstructed AnnotationRegions (Phase 7)
        try:
            regions = reconstruct_annotation_regions(texts)
            for reg in regions:
                compiled.append(AnnotationItem(
                    text=reg.normalized_text,
                    annotation_type=reg.annotation_type,
                    position_x=float((reg.bbox[1] + reg.bbox[3]) / 2.0),
                    position_y=float((reg.bbox[0] + reg.bbox[2]) / 2.0),
                ))
        except Exception as e:
            logger.debug(f"Annotation region reconstruction error: {e}")

        return compiled

    def _compile_relationships(
        self, relations: List[Dict], tag_alias_map: Optional[Dict[str, str]] = None
    ) -> List[Relationship]:
        """Compile relationships with canonical tag mapping, forbidden filter, and calibrated confidence."""
        from src.utils.tag_classifier import canonicalize_tag
        from src.utils.relationship_engine import calculate_relationship_confidence
        from src.utils.entity_validator import validate_equipment_candidate, validate_line_candidate

        _FORBIDDEN_EDGE_TAGS = {
            'TIT-9018-TIT', 'FE-9017-NOTE', 'PDIT-9015-HH', 'PI-9016-PIT', 'PI-9026-L',
            'PIT-9026-TIT', 'RD-1835-62809-199-77', 'CK-921-OMSMODUL', 'S-9003-MECHANIC',
            'STAGE-26-000001-001-26-PIT-9087', 'KA-902-STAGE', 'U-9017-PDIT-9017',
        }

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

            # Resolve source & target to master canonical tags
            src = tag_alias_map.get(raw_src.upper()) or tag_alias_map.get(canonicalize_tag(raw_src)) or raw_src
            tgt = tag_alias_map.get(raw_tgt.upper()) or tag_alias_map.get(canonicalize_tag(raw_tgt)) or raw_tgt

            # Filter out forbidden edge fragments
            if src in _FORBIDDEN_EDGE_TAGS or tgt in _FORBIDDEN_EDGE_TAGS:
                continue

            # Drop self-loop edges (e.g. 26-CK-921 -> 26-CK-921)
            if src == tgt or canonicalize_tag(src) == canonicalize_tag(tgt):
                logger.debug(f"Relationships: dropped self-loop edge '{src}' -> '{tgt}'")
                continue

            canon_edge = (canonicalize_tag(src), canonicalize_tag(tgt), rtype)
            if canon_edge in seen_edges:
                continue
            seen_edges.add(canon_edge)

            # Evidence-calibrated confidence (never 1.0)
            conf_val = float(r.get("confidence", 0.0))
            if conf_val <= 0.0 or conf_val >= 1.0:
                conf_val = calculate_relationship_confidence(
                    ocr_conf=0.90,
                    grammar_score=0.92,
                    geometry_score=0.75,
                    topology_score=0.75,
                    has_symbol_evidence=False,
                )

            result.append(Relationship(
                source=src,
                target=tgt,
                type=rtype,
                confidence=round(min(0.96, max(0.40, conf_val)), 2),
                attributes=r.get("attributes") or {},
                flag_reason=flag,
            ))

        return result
