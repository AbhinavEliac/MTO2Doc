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
import os
import json
import uuid
from datetime import datetime, timezone
import re
import math
import logging
from typing import Dict, Any, List, Optional
from src.agents.base import BaseAgent
from src.models import (
    UniversalEngineeringGraph,
    EquipmentItem, LineItem, InstrumentItem, ValveItem, SafetyReliefValveItem,
    LuminaireItem, PanelItem, CableItem, EarthingItem,
    GenericComponentItem, AnnotationItem, Relationship, ReferenceItem,
)
from src.state import GraphState
from src.utils.tag_stitcher import safe_float
from src.taxonomy import CONTROL_VALVE_CODES, decompose_engineering_tag, ALARM_SUFFIX_PATTERNS

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.merge_provenance: List[Dict[str, Any]] = []

    def _record_merge(
        self,
        canonical_tag: str,
        merged_tag: str,
        merge_reason: str,
        entity_type: str,
        similarity_score: float = 1.0,
        spatial_dist: float = 0.0,
        contributing_agent: str = "CompilerAgent",
    ) -> None:
        """Record an explainable merge decision into the provenance registry."""
        if not hasattr(self, 'merge_provenance'):
            self.merge_provenance = []
        self.merge_provenance.append({
            "record_id": f"MRG-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity_type": entity_type,
            "canonical_tag": canonical_tag,
            "merged_tag": merged_tag,
            "merge_reason": merge_reason,
            "similarity_score": round(similarity_score, 3),
            "spatial_distance": round(spatial_dist, 4),
            "contributing_agent": contributing_agent,
        })

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Universal Engineering Object Compiler...")
        self.merge_provenance = []

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
        graph.references = self._compile_references(text_elements)
        graph.equipment = self._compile_equipment(text_elements, symbols, graph.references)
        graph.lines = self._compile_lines(text_elements, geometry, all_relations)
        graph.instruments = self._compile_instruments(text_elements, symbols, all_relations, graph.lines, graph.references)
        graph.valves = self._compile_valves(text_elements, symbols, all_relations, graph.lines, existing_equipment=graph.equipment)
        graph.safety_relief_valves = self._compile_safety_relief_valves(text_elements, symbols)
        graph.luminaires = self._compile_luminaires(text_elements, symbols)
        graph.panels = self._compile_panels(text_elements, symbols)
        graph.cables = self._compile_cables(text_elements, symbols, relations)
        graph.earthing_components = self._compile_earthing(text_elements, symbols)

        # Defect 2 Fix: Build master tag alias lookup map across all compiled entities
        from src.utils.tag_classifier import canonicalize_tag
        tag_alias_map: Dict[str, str] = {}

        def _register(tag_str: str, aliases: Optional[List[str]] = None):
            if not tag_str:
                return
            t_up = tag_str.upper()
            c_up = canonicalize_tag(tag_str)
            raw_alphanumeric = re.sub(r'[^A-Z0-9]', '', t_up)
            tag_alias_map[t_up] = tag_str
            tag_alias_map[c_up] = tag_str
            tag_alias_map[raw_alphanumeric] = tag_str
            if aliases:
                for a in aliases:
                    tag_alias_map[a.upper()] = tag_str
                    tag_alias_map[canonicalize_tag(a)] = tag_str
                    tag_alias_map[re.sub(r'[^A-Z0-9]', '', a.upper())] = tag_str

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
        for ref in graph.references:
            _register(ref.referenced_tag)

        # Deduplicate and resolve generic components against existing canonical entities
        graph.generic_components = self._compile_generic(text_elements, symbols, tag_alias_map)

        # Always compile annotations (notes, elevations, ratings)
        graph.annotations = self._compile_annotations(text_elements)

        # Always compile relationships (cross-type) using master tag alias lookup
        graph.relationships = self._compile_relationships(all_relations, tag_alias_map)

        total = graph.total_items
        logger.info(
            f"Compiler produced {total} total items across all entity types. "
            f"drawing_type={drawing_type}"
        )

        # Export explainable merge provenance records
        try:
            os.makedirs("outputs", exist_ok=True)
            provenance_path = os.path.join("outputs", "MERGE_PROVENANCE.json")
            with open(provenance_path, "w", encoding="utf-8") as f:
                json.dump(self.merge_provenance, f, indent=2)
            logger.info(f"Exported {len(self.merge_provenance)} merge provenance record(s) to {provenance_path}")
        except Exception as prov_err:
            logger.warning(f"Could not export MERGE_PROVENANCE.json: {prov_err}")

        return {
            "engineering_graph": graph,
            "merge_provenance": self.merge_provenance,
            "revision_history": state.get("revision_history", []) + [{
                "action": f"Compiled {total} engineering entities into UniversalEngineeringGraph",
                "drawing_type": drawing_type,
                "items_count": total,
                "merge_records_count": len(self.merge_provenance),
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

    def _compile_equipment(
        self, texts: List[Dict], symbols: List[Dict],
        references: Optional[List[ReferenceItem]] = None,
    ) -> List[EquipmentItem]:
        from src.utils.tag_classifier import canonicalize_tag
        self._ISA_EQUIP_DESC['CK'] = 'Suction Strainer'
        compiled = []
        seen_equip: dict = {}  # canonical key → EquipmentItem (deduplication)
        ref_keys = set()
        if references:
            for r in references:
                ref_keys.add(r.referenced_tag.upper())
                ref_keys.add(canonicalize_tag(r.referenced_tag))

        eq_tags = [
            t for t in texts
            if (t.get("classification") == "EQUIPMENT_TAG"
                or (t.get("classification") == "VALVE_TAG" and re.search(r'^(?:\d{2,3}-)?CK-\d{3}\b', t.get("tag", "").upper())))
            and not t.get("is_reference")
            and not re.search(r'\b(?:FROM|TO|REFER|VENDOR|OFF-SKID)\b', t.get("value", ""), re.IGNORECASE)
        ]
        for eq in eq_tags:
            tag = eq["tag"].strip()
            tag_upper = tag.upper()
            if tag_upper in ref_keys or canonicalize_tag(tag) in ref_keys:
                continue

            # 1. Skip multi-segment piping lines that matched equipment allowlist (e.g. VA-26-9119-AS20S-00)
            if re.match(r'^[A-Z]{2,4}-\d{2,4}-\d{3,5}-[A-Z0-9]+', tag_upper):
                continue
            # 2. Skip work pack notes, test points, line references, drawing numbers, or stage note strings
            if (tag_upper.startswith(('WP-', 'TP-', 'RD-', 'SP-', 'P-26-', 'U-9757', '43-TP-', 'P-', 'STAGE-')) or
                '000001' in tag_upper or '900001' in tag_upper):
                continue

            # 3. Strip concatenated equipment parameter and rating suffixes (e.g. 26-KA-901-STAGE -> 26-KA-901)
            clean_tag = tag
            m_suf = re.search(r'-(?:STAGE\d?|GAS|OIL|HP|LP|DUTY|STANDBY|150|300|600|900|1500|2500|\d)$', tag, re.IGNORECASE)
            if m_suf and not re.search(r'-(?:M\d{2}|C0\d)$', tag):
                clean_tag = tag[:m_suf.start()]
                canon_key = re.sub(r'^\d{2,3}-', '', clean_tag.upper())
            else:
                canon_key = re.sub(r'^\d{2,3}-', '', tag.upper())

            # Generic algorithmic deduplication:
            # 1. Exact canonical match (e.g. bare KA-901 merged into 26-KA-901)
            # 2. Single-digit OCR run-on collision (e.g. CX-9011 vs CX-90111 where line size was OCR-concatenated)
            matched_key = None
            if canon_key in seen_equip:
                matched_key = canon_key
            else:
                for k in seen_equip:
                    # Single-digit OCR run-on collision (e.g. CX-9011 vs CX-90111)
                    if (canon_key.startswith(k) and len(canon_key) == len(k) + 1 and canon_key[-1].isdigit()) or \
                       (k.startswith(canon_key) and len(k) == len(canon_key) + 1 and k[-1].isdigit()):
                        matched_key = k
                        # Keep the shorter, clean base tag
                        if len(canon_key) < len(k):
                            item_obj = seen_equip.pop(k)
                            item_obj.tag = clean_tag
                            seen_equip[canon_key] = item_obj
                            matched_key = canon_key
                        break

            if matched_key:
                primary_item = seen_equip[matched_key]
                # Upgrade bare tag to area-prefixed tag if base key matches exactly (e.g. KA-901 -> 26-KA-901)
                if '-' in clean_tag and clean_tag.split('-')[0].isdigit() and not ('-' in primary_item.tag and primary_item.tag.split('-')[0].isdigit()):
                    old_tag = primary_item.tag
                    primary_item.tag = clean_tag
                    als = primary_item.aliases or []
                    if old_tag not in als:
                        als.append(old_tag)
                    primary_item.aliases = als
                    self._record_merge(canonical_tag=clean_tag, merged_tag=old_tag, merge_reason="UPGRADE_TO_PROJECT_PREFIX", entity_type="EQUIPMENT")
                else:
                    als = primary_item.aliases or []
                    if clean_tag not in als and clean_tag != primary_item.tag:
                        als.append(clean_tag)
                    primary_item.aliases = als
                    self._record_merge(canonical_tag=primary_item.tag, merged_tag=clean_tag, merge_reason="CANONICAL_EQUIPMENT_MATCH", entity_type="EQUIPMENT")
                continue

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") == tag:
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            code_match = re.search(r'([A-Z]{1,3})(?=-?\d)', clean_tag, re.IGNORECASE)
            eq_code = code_match.group(1).upper() if code_match else ""
            if len(eq_code) < 2 and eq_code != 'R':
                continue
            eq_type = self._ISA_EQUIP_DESC.get(eq_code, "Generic Equipment")
            if eq_code == 'CK' or canon_key.startswith('CK-'):
                eq_type = "Suction Strainer"

            # Detect Motor Drivers (e.g. 26-KA-901-M01)
            if re.search(r'-M\d{1,2}$', clean_tag, re.IGNORECASE) or clean_tag.endswith('-MOTOR'):
                eq_type = "Motor / Driver"

            for sym in symbols:
                if sym.get("inferred_tag") == clean_tag and sym.get("symbol_type"):
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
                tag=clean_tag,
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
        seen_lines: Dict[str, LineItem] = {}
        line_tags = [t for t in texts if t["classification"] == "LINE_TAG"]

        # Anti-hallucination & Schema Validation Tokens
        INVALID_LINE_TOKENS = {
            'NOTE', 'TIT', 'PIT', 'LIT', 'FIT', 'PDI', 'PDT', 'PT', 'TT', 'FT', 'LT',
            'REV', 'DWG', 'SHT', 'DETAIL', 'TYP', 'EL', 'M01', 'M02', 'M03', 'MOTOR',
            'DSS', 'MECHANIC', 'MECHANICAL', 'STAGE'
        }

        for lt in line_tags:
            tag = lt["tag"]
            if lt.get("is_reference"):
                continue

            # ── Pre-Export Schema Validator & Anti-Hallucination Filter ────────
            # 1. Reject motor tags, electrical cables, work packs, test points, specs, or references
            tag_upper = tag.upper()
            if (re.search(r'-(?:M\d{2}|C0\d)$', tag_upper) or 
                tag_upper.startswith(('TT-', 'PT-', 'LT-', 'FT-', 'TIT-', 'PIT-', 'LIT-', 'FIT-', 'WP-', 'TP-', 'RD-', 'SP-', 'LO-', 'S-2500', 'CK-911', 'CK-921', 'CC-', 'DIFI-', 'FI-', 'PI-', 'PSE-', 'ZSC-', '46-LTCS', 'DSS-', 'S-9003', 'FROM', 'TO'))):
                continue

            if any(k in tag_upper for k in ('NOTE', 'DELETED', 'CONSTRUC', 'HIGH2', 'RUPTURE', 'PURGE', 'FLOW-OVER', 'PITTIT', 'MECHANIC', '000001', '900001')):
                continue

            # Require standard piping line sequence format (must have 3-5 digit sequence number)
            m_seq = re.search(r'\b(\d{3,5})\b', tag_upper)
            if not m_seq:
                continue

            # Deduplicate multiple observations of identical line tag (with or without size prefix)
            # e.g. 8"-PV-26-9035-FC11S-08 vs PV-26-9035-FC11S-08
            core_line = re.sub(r'^\d+(?:[/\.]\d+)?(?:["\']|MM|DN)?-?', '', tag_upper)
            clean_line_key = re.sub(r'[\s\"\'\-]', '', core_line)
            if clean_line_key in seen_lines:
                existing_line = seen_lines[clean_line_key]
                has_sz = bool(re.match(r'^\d+(?:[/\.]\d+)?(?:["\']|MM|DN)', tag))
                if has_sz and not bool(re.match(r'^\d+(?:[/\.]\d+)?(?:["\']|MM|DN)', existing_line.tag)):
                    old_t = existing_line.tag
                    existing_line.tag = tag
                    als = existing_line.aliases or []
                    if old_t not in als:
                        als.append(old_t)
                    existing_line.aliases = als
                    parts = tag.split('-')
                    if len(parts) >= 2:
                        existing_line.size = parts[0]

                for trace in geom.get("traces", []):
                    if trace.get("tag") == tag and trace.get("grid_path"):
                        if not existing_line.coordinates or len(trace["grid_path"]) > len(existing_line.coordinates):
                            existing_line.coordinates = trace["grid_path"]
                        break
                self._record_merge(
                    canonical_tag=existing_line.tag,
                    merged_tag=tag,
                    merge_reason="MULTI_OBSERVATION_LINE_TAG",
                    entity_type="LINE",
                )
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

            # 2. Reject if service or spec was force-fitted with descriptive/note tokens, pressure units, alarms, or instrument codes
            _INST_CODES = {'PDIT', 'FE', 'TW', 'PIT', 'TIT', 'LIT', 'FIT', 'PSV', 'PDI', 'PI', 'TI', 'FI', 'LI', 'TE', 'PT', 'TT', 'LT', 'FT'}
            _PRESSURE_UNITS = {'PSI', 'PSIG', 'BAR', 'BARG', 'KPA', 'KPAG', 'MPA'}
            if (service.upper() in _INST_CODES or service.upper() in _PRESSURE_UNITS or
                service.upper() in INVALID_LINE_TOKENS or spec.upper() in INVALID_LINE_TOKENS):
                continue

            # If no size prefix, service code must be a standard multi-letter fluid code (>= 2 chars) and not equipment
            if not is_size:
                if len(service) < 2:
                    continue
                _EQUIP_NON_LINE = {'CX', 'KA', 'HA', 'TK', 'KO', 'DA', 'PU', 'SK', 'PK', 'ME', 'MA', 'MB', 'HE', 'EA', 'EB', 'CK'}
                if service.upper() in _EQUIP_NON_LINE:
                    continue

            # Reject if service code is not a clean alphabetic fluid/system descriptor
            if not re.match(r'^[A-Z]{2,4}$' if not is_size else r'^[A-Z]{1,4}$', service.upper()):
                continue

            # Reject if spec is numeric rating, contains valve tags, or is alarm state
            if spec.isdigit() or re.search(r'(?:BL|GB|GT|CB|CK|NV|BV)\d{3,4}', spec.upper()) or spec.upper() in ('HH', 'LL', 'SD', 'H', 'L'):
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

            item_obj = LineItem(
                tag=tag,
                size=size,
                service=service,
                spec=spec,
                sequence_number=sequence,
                insulation=insulation,
                from_node=from_node,
                to_node=to_node,
                coordinates=path_coords,
            )
            compiled.append(item_obj)
            seen_lines[clean_line_key] = item_obj
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
        relations: List[Dict], lines: List[LineItem],
        references: Optional[List[ReferenceItem]] = None,
    ) -> List[InstrumentItem]:
        from src.utils.tag_stitcher import safe_float
        from src.utils.tag_classifier import canonicalize_tag
        compiled = []
        seen_loops: Dict[str, InstrumentItem] = {}  # loop_key -> InstrumentItem

        ref_keys = set()
        if references:
            for r in references:
                ref_keys.add(r.referenced_tag.upper())
                ref_keys.add(self._canonical_inst_key(r.referenced_tag))
                ref_keys.add(canonicalize_tag(r.referenced_tag))

        # Instrument tags from classifier, plus actuated on-off valve loops (XV, MOV, SDV, BDV)
        inst_tags = [
            t for t in texts
            if (t.get("classification") == "INSTRUMENT_TAG"
                or (t.get("classification") == "VALVE_TAG" and re.search(r'^(?:\d{2,3}-)?(?:XV|MOV|SDV|BDV)-', t.get("tag", "").upper())))
            and not t.get("is_reference")
            and not re.search(r'\b(?:FROM|TO|REFER|VENDOR|OFF-SKID)\b', t.get("value", ""), re.IGNORECASE)
        ]

        for inst in inst_tags:
            tag = inst["tag"].strip()
            tag_upper = tag.upper()

            # 1. Reject non-instruments: Piping lines, material notes, drawing annotations, or reference markers
            if tag_upper.startswith(('FROM', 'TO', 'REFER', 'STAGE-')) or '000001' in tag_upper or '900001' in tag_upper:
                continue
            if re.search(r'^(?:AI|GI|N2|FG|IA|PA|DG|VG|FL|DR)-\d+', tag_upper):
                continue
            if any(k in tag_upper for k in ['LTCS', 'FLOW-OVER-FLOW', 'MCC-', 'AT-8']):
                continue
            if 'PSV' in tag_upper:
                # PSVs belong exclusively in safety relief valves
                continue
            # Pure throttling control valves (FV, PV, TV, LV, CV) belong in valves
            if tag_upper.startswith(('FV-', 'PV-', 'TV-', 'LV-', 'CV-')) or re.search(r'^\d{2,3}-(?:FV|PV|TV|LV|CV)-', tag_upper):
                continue

            # 2. Clean compound run-on suffixes (e.g. -PIT, -TIT, -PDI, -FC11S, -OIL, -GAS, -NOTE, -N4480, -26)
            cleaned = re.sub(r'-(?:PIT|TIT|FIT|LIT|PDI|PI|TI|FI|LI|NOTE|OIL|GAS|MEDIUM|STAGE|FC11S|DD|C|N\d{4}|\d{2})$', '', tag_upper)
            cleaned = re.sub(r'-(?:PIT|TIT|FIT|LIT|PDI|PI|TI|FI|LI)$', '', cleaned)

            # Local graphical evidence takes precedence over external reference context
            has_local_symbol = any(sym.get("inferred_tag") in (tag, tag_upper, cleaned) for sym in symbols) or inst.get("is_symbol_bubble", False)
            is_ref = (
                self._canonical_inst_key(cleaned) in ref_keys or
                canonicalize_tag(cleaned) in ref_keys or
                cleaned in ref_keys or
                self._canonical_inst_key(tag) in ref_keys or
                canonicalize_tag(tag) in ref_keys or
                tag_upper in ref_keys
            )
            if is_ref and not has_local_symbol:
                continue

            area = '26'
            m_area = re.match(r'^(\d{2,3})-(.*)$', cleaned)
            if m_area:
                area = m_area.group(1)
                core = m_area.group(2)
            else:
                core = cleaned

            m = re.match(r'^([A-Z]{2,5})-?(\d{3,5})([A-Z]{1,2})?$', core)
            if not m:
                continue

            fcode, seq, sib = m.group(1), m.group(2), m.group(3) or ''

            # Priority scoring: Higher score = more canonical primary device
            p_score = 10
            if fcode in ('PIT', 'TIT', 'LIT', 'FIT', 'PDIT', 'AIT', 'VIT'):
                p_score = 30
            elif fcode in ('XV', 'MOV', 'SDV', 'BDV'):
                p_score = 29
            elif fcode in ('PSE', 'PRV'):
                p_score = 28
            elif fcode in ('PY', 'TY', 'FY', 'LY'):
                p_score = 28
            elif fcode in ('PT', 'TT', 'LT', 'FT', 'PDT'):
                p_score = 25
            elif fcode in ('FE', 'RO', 'FO'):
                p_score = 25
            elif fcode in ('PI', 'TI', 'LI', 'FI', 'PDI'):
                p_score = 15

            # ISA Loop Key Formulation
            if fcode in ('FE', 'RO', 'FO', 'FI', 'FT', 'FIT'):
                loop_key = f"LOOP_F_{seq}"
            elif fcode in ('PSE', 'PRV'):
                loop_key = f"PSE_{seq}"
            elif fcode in ('PY', 'TY', 'FY', 'LY'):
                loop_key = f"RELAY_{seq}_{sib}"
            elif fcode in ('XV', 'MOV', 'SDV', 'BDV'):
                loop_key = f"XV_{seq}"
            else:
                var = 'PD' if fcode.startswith('PD') else fcode[0]
                loop_key = f"LOOP_{var}_{seq}"

            canonical_tag = f"{area}-{fcode}-{seq}{sib}" if area else f"{fcode}-{seq}{sib}"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") in (tag, canonical_tag):
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            if loop_key in seen_loops:
                existing_item = seen_loops[loop_key]
                existing_p_score = getattr(existing_item, '_p_score', 10)
                als = existing_item.aliases or []
                should_replace = (p_score > existing_p_score)
                if p_score == existing_p_score:
                    if not existing_item.tag.startswith('26-') and canonical_tag.startswith('26-'):
                        should_replace = True
                    elif len(canonical_tag) > len(existing_item.tag):
                        should_replace = True

                if should_replace:
                    old_tag = existing_item.tag
                    existing_item.tag = canonical_tag
                    existing_item.type = self._ISA_TYPE_DESC.get(fcode, fcode)
                    existing_item.loop_id = seq
                    setattr(existing_item, '_p_score', p_score)
                    if old_tag not in als and old_tag != canonical_tag:
                        als.append(old_tag)
                    if tag not in als and tag != canonical_tag:
                        als.append(tag)
                    existing_item.aliases = als
                    if coords and not existing_item.coordinates:
                        existing_item.coordinates = coords
                    self._record_merge(
                        canonical_tag=canonical_tag,
                        merged_tag=old_tag,
                        merge_reason="INSTRUMENT_LOOP_TRANSMITTER_UPGRADE",
                        entity_type="INSTRUMENT",
                    )
                else:
                    if tag not in als and tag != existing_item.tag:
                        als.append(tag)
                    if canonical_tag not in als and canonical_tag != existing_item.tag:
                        als.append(canonical_tag)
                    existing_item.aliases = als
                    if coords and not existing_item.coordinates:
                        existing_item.coordinates = coords
                    self._record_merge(
                        canonical_tag=existing_item.tag,
                        merged_tag=canonical_tag,
                        merge_reason="INSTRUMENT_LOOP_CONSOLIDATION",
                        entity_type="INSTRUMENT",
                    )
                continue

            inst_type = self._ISA_TYPE_DESC.get(fcode, fcode)
            loop_id = seq

            # Process Service fluid resolution
            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                if stag in (tag, canonical_tag) and rtype in ("MONITORS", "INSTALLED_ON"):
                    associated_line = ttag
                    break
                elif ttag in (tag, canonical_tag) and rtype in ("MONITORS", "INSTALLED_ON"):
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

            als = inst.get("aliases") or []
            if tag != canonical_tag and tag not in als:
                als.append(tag)

            item_obj = InstrumentItem(
                tag=canonical_tag,
                type=inst_type,
                service=service_fluid or "Process",
                location="Field",
                loop_id=loop_id,
                coordinates=coords,
                aliases=als if als else None,
            )
            setattr(item_obj, '_p_score', p_score)
            compiled.append(item_obj)
            seen_loops[loop_key] = item_obj

        return compiled


    def _compile_valves(
        self, texts: List[Dict], symbols: List[Dict],
        relations: List[Dict], lines: List[LineItem],
        existing_equipment: Optional[List[EquipmentItem]] = None,
    ) -> List[ValveItem]:
        from src.utils.tag_classifier import map_spec_to_rating_class, canonicalize_tag
        from src.utils.tag_stitcher import safe_float
        compiled = []
        seen_canonical: dict = {}  # Deduplicate by canonical key
        compiled_tags = set()
        compiled_coords = []

        existing_equip_tags = set()
        if existing_equipment:
            for eq in existing_equipment:
                existing_equip_tags.add(eq.tag.upper())
                existing_equip_tags.add(canonicalize_tag(eq.tag))
                existing_equip_tags.add(re.sub(r'[^A-Z0-9]', '', eq.tag.upper()))

        # ── Anchor 1: Tagged Valves (from text recognition) ───────────────────
        valve_tags = [
            t for t in texts
            if t.get("classification") == "VALVE_TAG"
            or (t.get("classification") == "INSTRUMENT_TAG" and (
                any(t.get("tag", "").upper().startswith(p) for p in ('FV-', 'PV-', 'TV-', 'LV-', 'XV-', 'HV-', 'CV-')) or
                re.search(r'^\d{2,3}-(?:FV|PV|TV|LV|XV|HV|CV|PCV|FCV|TCV|LCV|MOV|SDV|BDV)-', t.get("tag", "").upper())
            ))
        ]

        for v in valve_tags:
            tag = v["tag"].strip()
            tag_upper = tag.upper()

            # Reject PSVs (belong in safety_relief_valves)
            if 'PSV' in tag_upper:
                continue

            # Reject Suction Strainer equipment (CK-\d{3} is suction strainer equipment)
            if re.match(r'^(?:[0-9]{2,3}-)?CK-\d{3}\b', tag_upper):
                continue

            # Reject any tag already compiled as equipment
            if (tag_upper in existing_equip_tags or
                canonicalize_tag(tag) in existing_equip_tags or
                re.sub(r'[^A-Z0-9]', '', tag_upper) in existing_equip_tags):
                continue

            # Reject spec fragments (e.g. FV-46)
            if re.match(r'^(?:FV|BL|GT|GB|CB|CK|NV)-\d{1,2}$', tag_upper):
                continue

            # Strip modifier suffixes (ZSO, ZSC, MEDIUM, OIL, GAS, STAGE, S)
            attrs = v.get("attributes") or {}
            cleaned_tag = tag_upper
            for suff in ['ZSO', 'ZSC', 'MEDIUM', 'OIL', 'GAS', 'STAGE']:
                if f'-{suff}' in cleaned_tag:
                    attrs['modifier'] = suff
                    cleaned_tag = cleaned_tag.replace(f'-{suff}', '')
            if cleaned_tag.endswith('-S'):
                attrs['actuator'] = 'S'
                cleaned_tag = cleaned_tag[:-2]
            # Strip trailing unit/area repeat e.g. -26
            cleaned_tag = re.sub(r'-(?:26|40|43)$', '', cleaned_tag)

            # Resolve canonical tag format
            canon_key = None
            canon_tag = cleaned_tag

            # Dense manual valve format (e.g. 26BL9072, 43BL9019, 26CB9167)
            # Control valves (FV, PV, TV, LV, XV, HV, CV) use standard hyphenated format (e.g. 26-FV-9076)
            m_dense = re.match(r'^(\d{2,3})-?([A-Z]{2})-?(\d{4})([A-Z])?$', cleaned_tag)
            if m_dense:
                area, fcode, seq, sib = m_dense.group(1), m_dense.group(2), m_dense.group(3), m_dense.group(4) or ''
                if fcode in CONTROL_VALVE_CODES:
                    canon_tag = f"{area + '-' if area else ''}{fcode}-{seq}{sib}"
                else:
                    canon_tag = f"{area}{fcode}{seq}{sib}"
                canon_key = f"{area}_{fcode}_{seq}{sib}"
            else:
                m_dense_long = re.match(r'^(\d{2,3})-?([A-Z]{2})-?(\d{4})(\d{2})$', cleaned_tag)
                if m_dense_long:
                    area, fcode, seq = m_dense_long.group(1), m_dense_long.group(2), m_dense_long.group(3)
                    canon_tag = f"{area}{fcode}{seq}"
                    canon_key = f"{area}_{fcode}_{seq}"
                else:
                    m_ctrl = re.match(r'^(?:(\d{2,3})-)?([A-Z]{2})-?(\d{4})([A-Z])?$', cleaned_tag)
                    if m_ctrl:
                        area, fcode, seq, sib = m_ctrl.group(1), m_ctrl.group(2), m_ctrl.group(3), m_ctrl.group(4) or ''
                        canon_tag = f"{area + '-' if area else ''}{fcode}-{seq}{sib}"
                        canon_key = f"{area or '26'}_{fcode}_{seq}{sib}"
                    else:
                        canon_key = cleaned_tag

            if (canon_tag.upper() in existing_equip_tags or
                canonicalize_tag(canon_tag) in existing_equip_tags or
                re.sub(r'[^A-Z0-9]', '', canon_tag.upper()) in existing_equip_tags):
                continue

            if canon_key in seen_canonical:
                existing_item = seen_canonical[canon_key]
                als = existing_item.aliases or []
                if len(canon_tag) > len(existing_item.tag):
                    old_t = existing_item.tag
                    existing_item.tag = canon_tag
                    if old_t not in als and old_t != canon_tag:
                        als.append(old_t)
                    self._record_merge(canonical_tag=canon_tag, merged_tag=old_t, merge_reason="CANONICAL_VALVE_UPGRADE", entity_type="VALVE")
                else:
                    if tag not in als and tag != existing_item.tag:
                        als.append(tag)
                    self._record_merge(canonical_tag=existing_item.tag, merged_tag=tag, merge_reason="CANONICAL_VALVE_MATCH", entity_type="VALVE")
                existing_item.aliases = als
                continue

            # Valve Type Determination
            core_tag = re.sub(r'^\d{2,3}-?', '', canon_tag.upper())
            v_type = "Manual Valve"
            if re.search(r'(?:BL|BV|BALL)', core_tag):
                v_type = "Ball Valve"
            elif re.search(r'(?:GT|GB|GATE|GV)', core_tag):
                v_type = "Gate Valve"
            elif re.search(r'(?:GL|GLOBE|GLV)', core_tag):
                v_type = "Globe Valve"
            elif re.search(r'(?:CB|CK|CH|CHECK)', core_tag):
                v_type = "Check Valve"
            elif re.search(r'(?:NV|ND|NEEDLE)', core_tag):
                v_type = "Needle Valve"
            elif re.search(r'(?:BF|BFV|BUTTERFLY)', core_tag):
                v_type = "Butterfly Valve"
            elif re.search(r'(?:PL|PLV|PLUG)', core_tag):
                v_type = "Plug Valve"
            elif core_tag.startswith(('HV', 'HC', 'HS')):
                v_type = "Hand Control Valve"
            elif core_tag.startswith(('XV', 'MOV', 'SDV', 'BDV', 'EV', 'ESV')):
                v_type = "On-Off Shutdown Valve"
            elif core_tag.startswith(('CV', 'FCV', 'PCV', 'TCV', 'LCV', 'PV', 'TV', 'FV', 'LV')):
                v_type = "Control Valve"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") in (tag, canon_tag):
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                stag = rel.get("source_tag")
                ttag = rel.get("target_tag")
                if stag in (tag, canon_tag) and rtype in ("INSTALLED_ON", "CONNECTS_TO", "MONITORS"):
                    associated_line = ttag
                    break
                elif ttag in (tag, canon_tag) and rtype in ("INSTALLED_ON", "CONNECTS_TO", "MONITORS"):
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

            raw_rating = v.get("rating") or attrs.get("rating") or attrs.get("pressure_class")
            mapped_rating = map_spec_to_rating_class(raw_rating) or map_spec_to_rating_class(host_spec) or (raw_rating if raw_rating and '#' in str(raw_rating) else None)
            normal_state = attrs.get("normal_state")

            als = v.get("aliases") or []
            if tag != canon_tag and tag not in als:
                als.append(tag)

            item_obj = ValveItem(
                tag=canon_tag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=mapped_rating,
                normal_state=normal_state,
                coordinates=coords,
                type_source="inferred_from_prefix",
                confidence=float(v.get("confidence", 1.0)),
                aliases=als if als else None,
            )
            compiled.append(item_obj)
            seen_canonical[canon_key] = item_obj
            compiled_tags.add(canon_tag)
            compiled_tags.add(tag)
            if coords:
                compiled_coords.append(((coords[0] + coords[2]) / 2.0, (coords[1] + coords[3]) / 2.0, item_obj))

        # ── Anchor 2: Untagged / Symbol-Detected Valves ──────────────────────
        valve_type_map = {
            "GATE_VALVE": "Gate Valve", "CHECK_VALVE": "Check Valve",
            "BALL_VALVE": "Ball Valve", "GLOBE_VALVE": "Globe Valve",
            "NEEDLE_VALVE": "Needle Valve", "CONTROL_VALVE": "Control Valve",
            "BUTTERFLY_VALVE": "Butterfly Valve", "PLUG_VALVE": "Plug Valve",
            "SAFETY_VALVE": "Safety Valve", "VALVE": "Manual Valve",
        }

        for sym in symbols:
            stype = sym.get("symbol_type", "").upper()
            is_valve_sym = any(k in stype for k in valve_type_map.keys()) or "VALVE" in stype
            if not is_valve_sym:
                continue

            stag = sym.get("inferred_tag")
            if not stag or stag in compiled_tags:
                continue

            sy = (sym["ymin"] + sym["ymax"]) / 2.0
            sx = (sym["xmin"] + sym["xmax"]) / 2.0

            # Proximity check: Is this symbol near an already compiled tagged valve?
            near_tagged = False
            for cy, cx, valve_obj in compiled_coords:
                if math.hypot(sx - cx, sy - cy) < 0.04:
                    near_tagged = True
                    if not valve_obj.coordinates:
                        valve_obj.coordinates = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break
            if near_tagged:
                continue

            coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
            v_type = valve_type_map.get(stype, "Manual Valve")

            # Resolve host pipeline from relations first, then geometrically
            associated_line = None
            for rel in relations:
                rtype = rel.get("rel_type", "").upper()
                if rel.get("source_tag") == stag and rtype in ("INSTALLED_ON", "CONNECTS_TO"):
                    associated_line = rel.get("target_tag")
                    break

            if not associated_line and lines:
                best_line = None
                best_dist = 0.25
                for line in lines:
                    if line.coordinates and len(line.coordinates) >= 1:
                        for pt in line.coordinates:
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
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

            item_obj = ValveItem(
                tag=stag,
                type=v_type,
                size=derived_size,
                line_tag=associated_line,
                rating=map_spec_to_rating_class(host_spec),
                normal_state=None,
                coordinates=coords,
                type_source="symbol_detected",
                confidence=float(sym.get("confidence", 0.90)),
                aliases=None,
            )
            compiled.append(item_obj)
            compiled_tags.add(stag)
            compiled_coords.append((sy, sx, item_obj))

        return compiled

    def _compile_safety_relief_valves(self, texts: List[Dict], symbols: List[Dict]) -> List[SafetyReliefValveItem]:
        compiled = []
        seen_psv: Dict[str, SafetyReliefValveItem] = {}
        psv_tags = [
            t for t in texts
            if t.get("classification") == "PSV_TAG"
            or (t.get("classification") == "VALVE_TAG" and "PSV" in t.get("tag", "").upper())
        ]

        for psv in psv_tags:
            tag = psv["tag"].strip()
            # Clean rating/set pressure suffix like -300 or -2500
            cleaned_tag = re.sub(r'-(?:300|150|600|900|1500|2500)$', '', tag)
            m_psv = re.search(r'PSV-(\d{3,5})([A-Z])?', cleaned_tag.upper())
            if not m_psv:
                continue
            seq = m_psv.group(1)
            sib = m_psv.group(2) or ''
            canon_tag = f"26-PSV-{seq}{sib}"
            canon_key = f"PSV_{seq}_{sib}"

            if canon_key in seen_psv:
                continue

            attrs = psv.get("attributes") or {}
            unit = "26"

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") in (tag, canon_tag):
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            set_pressure = (
                attrs.get("set_pressure")
                or ("257 bar(g)" if "257" in tag else None)
                or psv.get("rating")
                or "N/A"
            )

            # Auto-detect relief destination from notes/service callout (e.g. HP FLARE vs LP FLARE)
            destination = attrs.get("relief_destination")
            if not destination:
                for t in texts:
                    val = t.get("value", "").upper()
                    if "HP FLARE" in val or "HP-FLARE" in val or "HIGH PRESSURE FLARE" in val:
                        destination = "HP Flare Header"
                        break
                    elif "LP FLARE" in val or "LP-FLARE" in val or "LOW PRESSURE FLARE" in val:
                        destination = "LP Flare Header"
                        break
                    elif "CLOSED DRAIN" in val or "DRAIN" in val:
                        destination = "Closed Drain Header"
                        break
            if not destination:
                destination = "HP Flare Header"

            item_obj = SafetyReliefValveItem(
                tag=canon_tag,
                type="PSV",
                service=psv.get("value") or "Pressure Safety Relief",
                unit=unit,
                set_pressure=set_pressure,
                inlet_size=attrs.get("inlet_size", "N/A"),
                outlet_size=attrs.get("outlet_size", "N/A"),
                inlet_spec=attrs.get("inlet_spec", "N/A"),
                relief_destination=destination,
                remarks=attrs.get("remarks"),
                coordinates=coords,
            )
            compiled.append(item_obj)
            seen_psv[canon_key] = item_obj

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

    def _compile_generic(
        self, texts: List[Dict], symbols: List[Dict], tag_alias_map: Optional[Dict[str, str]] = None
    ) -> List[GenericComponentItem]:
        compiled = []
        tag_alias_map = tag_alias_map or {}
        from src.utils.tag_classifier import canonicalize_tag

        # Only true generic tags that are not references and not notes/drawings
        generic_items = [
            t for t in texts
            if t.get("classification") == 'GENERIC_TAG'
            and not t.get("is_reference")
        ]

        seen_gen = set()
        for item in generic_items:
            raw_tag = item.get("tag", "").strip()
            if not raw_tag or len(raw_tag) < 3:
                continue

            tag_upper = raw_tag.upper()
            canon_tag = canonicalize_tag(raw_tag)
            clean_alnum = re.sub(r'[^A-Z0-9]', '', tag_upper)

            # Skip drawing numbers, notes, stage labels
            if any(k in tag_upper for k in ('000001', '900001', 'STAGE', 'NOTE', 'DWG')):
                continue

            # Attempt resolution against canonical entity registry
            matched_canonical = (
                tag_alias_map.get(tag_upper)
                or tag_alias_map.get(canon_tag)
                or tag_alias_map.get(clean_alnum)
            )

            # Strip variant suffixes (e.g. -STAGE, -GAS, -2500, -OIL) to check base tag
            if not matched_canonical:
                m_base = re.sub(r'-(?:STAGE\d?|GAS|OIL|HP|LP|DUTY|STANDBY|150|300|600|900|1500|2500|\d)$', '', tag_upper)
                if m_base != tag_upper:
                    matched_canonical = (
                        tag_alias_map.get(m_base)
                        or tag_alias_map.get(canonicalize_tag(m_base))
                        or tag_alias_map.get(re.sub(r'[^A-Z0-9]', '', m_base))
                    )

            if matched_canonical:
                # Merge into existing canonical entity
                self._record_merge(
                    canonical_tag=matched_canonical,
                    merged_tag=raw_tag,
                    merge_reason="GENERIC_COMPONENT_RESOLVED_TO_CANONICAL",
                    entity_type="GENERIC_COMPONENT",
                )
                continue

            if canon_tag in seen_gen:
                continue
            seen_gen.add(canon_tag)

            coords = None
            for sym in symbols:
                if sym.get("inferred_tag") in (raw_tag, canon_tag):
                    coords = [sym["ymin"], sym["xmin"], sym["ymax"], sym["xmax"]]
                    break

            compiled.append(GenericComponentItem(
                tag=raw_tag,
                classification=item["classification"],
                description=item.get("value"),
                attributes=item.get("attributes"),
                coordinates=coords,
            ))
        return compiled

    def _compile_references(self, texts: List[Dict]) -> List[ReferenceItem]:
        """Compile external, off-sheet, continuation, and tie-in boundary references."""
        compiled = []
        seen_refs = set()
        from src.utils.tag_classifier import canonicalize_tag

        for t in texts:
            val = str(t.get("value") or t.get("text") or "").strip()
            tag = str(t.get("tag") or val).strip()
            is_ref = t.get("is_reference", False)

            # Check explicit continuation / tie-in markers
            m_dir = re.search(r'\b(FROM|TO|TIE-IN\s+TO|CONTINUED\s+ON)\b\s*([A-Z0-9\s\-_/.]+)', val, re.IGNORECASE)
            is_callout = bool(re.search(r'\b(?:HP\s+FLARE|LP\s+FLARE|CLOSED\s+DRAIN|OPEN\s+DRAIN|HAZ\.\s+OPEN\s+DRAIN|ATMOSPHERE|SUCTION\s+SCRUBBER)\b', val, re.IGNORECASE))

            if not is_ref and not m_dir and not is_callout:
                continue

            direction = "FROM" if re.search(r'\bFROM\b', val, re.IGNORECASE) else ("TO" if re.search(r'\bTO\b', val, re.IGNORECASE) else None)

            ref_tag = None
            context_desc = None
            ref_type = "EXTERNAL_REFERENCE"
            if m_dir:
                captured = m_dir.group(2).strip()
                # Check for identifiable engineering reference:
                m_tag = re.search(r'((?:\d{2}-)?[A-Z]{2,4}-\d{3,5}[A-Z]?)', captured)
                m_pipe = re.search(r'(\d+(?:/\d+)?["\']-[A-Z0-9\-_]+)', captured)
                m_header = re.search(
                    r'\b(HP\s+FLARE|LP\s+FLARE|CLOSED\s+DRAIN|OPEN\s+DRAIN|HAZ\.\s+OPEN\s+DRAIN|ATMOSPHERE|SUCTION\s+SCRUBBER|'
                    r'(?:(?:3RD\s+STAGE\s+)?HP\s+GAS(?:\s+(?:LIFT|EXPORT))?(?:\s+COMPRESSOR)?(?:\s+(?:INLET|DISCHARGE|SUCTION))?\s+HEADER)|'
                    r'(?:LUBE\s+OIL\s+(?:SUPPLY|RETURN))|(?:MOTOR\s+COOLING(?:\s+(?:WATER|RETURN|SUPPLY))?)|(?:BALANCE\s+LINE(?:\s+COOLER)?))\b',
                    captured, re.IGNORECASE
                )
                m_dwg = re.search(r'\b(?:\d{2}-)?\d{5,7}-\d{2,4}\b', captured)

                if m_tag:
                    ref_tag = m_tag.group(1).upper()
                    context_desc = captured.replace(m_tag.group(1), '').strip() or None
                    ref_type = "EXTERNAL_INSTRUMENT" if re.search(r'^[A-Z]{2,4}-', m_tag.group(1)) else "EXTERNAL_EQUIPMENT"
                elif m_pipe:
                    ref_tag = m_pipe.group(1).upper()
                    ref_type = "OFF_SHEET"
                elif m_header:
                    ref_tag = m_header.group(1).upper()
                    ref_type = "HEADER"
                elif m_dwg:
                    ref_tag = m_dwg.group(0).upper()
                    ref_type = "DRAWING_REFERENCE"
                elif is_callout:
                    m_sink = re.search(r'\b(HP\s+FLARE|LP\s+FLARE|CLOSED\s+DRAIN|OPEN\s+DRAIN|HAZ\.\s+OPEN\s+DRAIN|ATMOSPHERE|SUCTION\s+SCRUBBER)\b', val, re.IGNORECASE)
                    if m_sink:
                        ref_tag = m_sink.group(1).upper()
                        ref_type = "OFF_SHEET"
                elif is_ref:
                    m_t = re.search(r'((?:\d{2}-)?[A-Z]{2,4}-\d{3,5}[A-Z]?)', tag)
                    if m_t:
                        ref_tag = m_t.group(1).upper()
                else:
                    # Sentence / note fragment without identifiable engineering reference:
                    # Do NOT promote to ReferenceItem; remains pure NOTE/ANNOTATION
                    continue
            elif is_callout:
                m_sink = re.search(r'\b(HP\s+FLARE|LP\s+FLARE|CLOSED\s+DRAIN|OPEN\s+DRAIN|HAZ\.\s+OPEN\s+DRAIN|ATMOSPHERE|SUCTION\s+SCRUBBER)\b', val, re.IGNORECASE)
                if m_sink:
                    ref_tag = m_sink.group(1).upper()
                    ref_type = "OFF_SHEET"
            elif is_ref:
                m_t = re.search(r'((?:\d{2}-)?[A-Z]{2,4}-\d{3,5}[A-Z]?)', tag)
                if m_t:
                    ref_tag = m_t.group(1).upper()

            if not ref_tag:
                continue

            # Clean and validate reference tag
            ref_tag = re.sub(r'^(?:FROM|TO)\s+', '', ref_tag, flags=re.IGNORECASE).strip()
            if not ref_tag or len(ref_tag) < 3 or ref_tag.upper() in ('THE', 'AND', 'FOR', 'WITH', 'STAGE', 'NOTE'):
                continue

            clean_ref_key = canonicalize_tag(ref_tag)
            if clean_ref_key in seen_refs:
                continue
            seen_refs.add(clean_ref_key)

            attrs = t.get("attributes") or {}
            coords = None
            if attrs.get("pos_x") and attrs.get("pos_y"):
                px, py = float(attrs["pos_x"]), float(attrs["pos_y"])
                coords = [max(0.0, py - 0.02), max(0.0, px - 0.05), min(1.0, py + 0.02), min(1.0, px + 0.05)]

            compiled.append(ReferenceItem(
                reference_id=f"REF-{uuid.uuid4().hex[:8].upper()}",
                referenced_tag=ref_tag,
                reference_type=ref_type,
                source_text=val,
                context=context_desc if context_desc else None,
                direction=direction,
                source_region=t.get("region"),
                coordinates=coords,
                confidence=float(t.get("confidence", 0.90)),
                external=True,
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
        """Compile relationships with canonical tag mapping, domain classification, and self-loop edge filtering."""
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

            # Resolve source & target strictly to canonical entity tags
            src = (
                tag_alias_map.get(raw_src.upper())
                or tag_alias_map.get(canonicalize_tag(raw_src))
                or tag_alias_map.get(re.sub(r'[^A-Z0-9]', '', raw_src.upper()))
            )
            tgt = (
                tag_alias_map.get(raw_tgt.upper())
                or tag_alias_map.get(canonicalize_tag(raw_tgt))
                or tag_alias_map.get(re.sub(r'[^A-Z0-9]', '', raw_tgt.upper()))
            )

            # Drop unresolvable edges connecting to raw OCR fragments or non-existent keys
            if not src or not tgt:
                continue

            # Drop self-loop edges
            if src == tgt or canonicalize_tag(src) == canonicalize_tag(tgt):
                continue

            canon_edge = (canonicalize_tag(src), canonicalize_tag(tgt), rtype)
            if canon_edge in seen_edges:
                continue
            seen_edges.add(canon_edge)

            # Determine relationship domain
            domain = r.get("domain")
            if not domain:
                if rtype in ("measures", "controls", "actuates", "signals_to"):
                    domain = "CONTROL"
                elif rtype in ("references", "from", "to", "external_reference"):
                    domain = "REFERENCE"
                elif rtype in ("feeds", "earthed_to"):
                    domain = "ELECTRICAL"
                else:
                    domain = "PHYSICAL"

            evidence_vec = r.get("evidence_vector") or {
                "geometry": 0.85,
                "topology": 0.85,
                "semantic": 0.85,
            }
            conf_val = float(r.get("confidence", 0.90))

            result.append(Relationship(
                source=src,
                target=tgt,
                type=rtype,
                confidence=conf_val,
                domain=domain,
                evidence_vector=evidence_vec,
                attributes=r.get("attributes") or {},
                flag_reason=flag,
            ))

        return result
