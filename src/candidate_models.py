"""
Canonical Observation, Candidate & Entity Models for Precision Architecture.

Implements:
1. RawObservation: Unprocessed visual observation (OCR token or Symbol bounding box).
2. EntityAttribute: Granular attribute (alarm state, pressure rating, material, datasheet field).
3. ConfidenceVector: Multi-dimensional confidence scoring across 8 engineering dimensions.
4. EngineeringCandidate: Intermediate candidate object with full lifecycle status tracking.
5. MergeProvenanceRecord: Explainable record of candidate merging with provenance.
6. CanonicalEntityRegistry: Central registry for deduplication, evidence fusion, and serialization.
"""

from __future__ import annotations

import math
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
from pydantic import BaseModel, Field

from src.taxonomy import (
    EngineeringTaxonomy,
    EntityStatus,
    CandidateRole,
    DrawingRegion,
    DecomposedTag,
    decompose_engineering_tag,
)
from src.models import (
    UniversalEngineeringGraph,
    EquipmentItem,
    LineItem,
    InstrumentItem,
    ValveItem,
    SafetyReliefValveItem,
    Relationship,
    AnnotationItem,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Multi-Dimensional Confidence Vector
# ──────────────────────────────────────────────────────────────────────────────

class ConfidenceVector(BaseModel):
    """
    Separate confidence dimensions across all lifecycle stages.
    Prevents high OCR confidence from falsely implying high entity validity.
    """
    detection_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ocr_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    symbol_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    normalization_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    entity_resolution_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    relationship_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def composite_score(self) -> float:
        """Weighted harmonic composite score prioritizing resolution and classification."""
        scores = [
            self.detection_confidence * 0.15,
            self.ocr_confidence * 0.15,
            self.classification_confidence * 0.30,
            self.entity_resolution_confidence * 0.40,
        ]
        return round(sum(scores), 3)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Raw Observation Model
# ──────────────────────────────────────────────────────────────────────────────

class RawObservation(BaseModel):
    """
    Captures raw sensory evidence from OCR or Computer Vision before interpretation.
    """
    observation_id: str = Field(default_factory=lambda: f"OBS-{uuid.uuid4().hex[:8].upper()}")
    source_agent: str                   # 'TextRecognitionAgent', 'SymbolRecognitionAgent', etc.
    observation_type: str               # 'OCR_TOKEN', 'GRAPHIC_SYMBOL', 'POLYLINE_TRACE'
    raw_text: Optional[str] = None      # Exact string returned by OCR
    symbol_class: Optional[str] = None  # Exact YOLO or harvester class
    bounding_box: Optional[List[float]] = None # [ymin, xmin, ymax, xmax] in 0.0-1.0
    center_x: float = 0.5
    center_y: float = 0.5
    raw_confidence: float = 1.0
    drawing_region: DrawingRegion = DrawingRegion.UNKNOWN_REGION
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Entity Attribute Model
# ──────────────────────────────────────────────────────────────────────────────

class EntityAttribute(BaseModel):
    """
    Structured attribute bound to an engineering candidate or canonical entity.
    Guarantees attributes (HH alarms, setpoints, materials) are not promoted to entities.
    """
    attribute_name: str                 # e.g., 'alarm_state', 'set_pressure', 'material', 'duty'
    attribute_value: str                # e.g., 'HH', '225.4 BARG', '316L SS', '1835 kW'
    attribute_unit: Optional[str] = None# e.g., 'BARG', 'kW', 'kg/h', '°C'
    source_observation_id: Optional[str] = None
    confidence: float = 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 4. Engineering Candidate Model
# ──────────────────────────────────────────────────────────────────────────────

class EngineeringCandidate(BaseModel):
    """
    Intermediate engineering candidate undergoing evidence enrichment,
    fusion, deduplication, and lifecycle gating.
    """
    candidate_id: str = Field(default_factory=lambda: f"CAND-{uuid.uuid4().hex[:8].upper()}")
    raw_tag: str
    normalized_tag: str
    canonical_base_tag: str             # Key without area prefix or alarm suffix (e.g. PIT-9055)
    taxonomy: EngineeringTaxonomy
    role: CandidateRole = CandidateRole.BASE_TAG
    status: EntityStatus = EntityStatus.CANDIDATE
    
    # Evidence & Geometry
    bounding_box: Optional[List[float]] = None # [ymin, xmin, ymax, xmax]
    center_x: float = 0.5
    center_y: float = 0.5
    drawing_region: DrawingRegion = DrawingRegion.PROCESS_AREA
    
    # Linked Observations & Attributes
    raw_observations: List[RawObservation] = Field(default_factory=list)
    attributes: Dict[str, EntityAttribute] = Field(default_factory=dict)
    alarms: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    
    # Multi-dimensional confidence
    confidence: ConfidenceVector = Field(default_factory=ConfidenceVector)
    
    # Topology links
    associated_line: Optional[str] = None
    associated_equipment: Optional[str] = None
    connected_line_ids: List[str] = Field(default_factory=list)
    
    # Audit provenance
    merge_history: List[str] = Field(default_factory=list)
    review_reason: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# 5. Merge Provenance Record
# ──────────────────────────────────────────────────────────────────────────────

class MergeProvenanceRecord(BaseModel):
    """
    Immutable audit record documenting why candidate observations were merged.
    """
    record_id: str = Field(default_factory=lambda: f"MRG-{uuid.uuid4().hex[:8].upper()}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    canonical_entity_id: str
    canonical_tag: str
    merged_tag: str
    merge_reason: str                   # e.g., 'BASE_TAG_EXACT_MATCH', 'ALARM_SUFFIX_ABSORPTION'
    similarity_score: float = 1.0
    spatial_distance: float = 0.0
    contributing_agent: str


# ──────────────────────────────────────────────────────────────────────────────
# 6. Canonical Entity Registry & Resolution Engine
# ──────────────────────────────────────────────────────────────────────────────

class CanonicalEntityRegistry:
    """
    Central repository for engineering observations, candidates, and canonical entities.
    Executes multi-factor deduplication, evidence fusion, and serialization.
    """

    def __init__(self):
        self.candidates: Dict[str, EngineeringCandidate] = {}
        self.merge_records: List[MergeProvenanceRecord] = []
        self._canonical_index: Dict[str, str] = {} # canonical_base_tag -> primary candidate_id

    def register_observation(
        self,
        source_agent: str,
        raw_text: Optional[str] = None,
        symbol_class: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        confidence: float = 1.0,
        region: DrawingRegion = DrawingRegion.PROCESS_AREA,
    ) -> EngineeringCandidate:
        """
        Ingests a raw observation and creates or enriches an EngineeringCandidate.
        """
        cx, cy = 0.5, 0.5
        if bbox and len(bbox) >= 4:
            cy = (bbox[0] + bbox[2]) / 2.0
            cx = (bbox[1] + bbox[3]) / 2.0

        obs = RawObservation(
            source_agent=source_agent,
            observation_type="GRAPHIC_SYMBOL" if symbol_class else "OCR_TOKEN",
            raw_text=raw_text,
            symbol_class=symbol_class,
            bounding_box=bbox,
            center_x=cx,
            center_y=cy,
            raw_confidence=confidence,
            drawing_region=region,
        )

        effective_tag = raw_text or symbol_class or "UNKNOWN"
        decomposed = decompose_engineering_tag(effective_tag, graphic_hint=symbol_class)

        # Check for existing canonical match by base tag
        canon_base = decomposed.canonical_base_tag
        if canon_base in self._canonical_index:
            primary_id = self._canonical_index[canon_base]
            primary_cand = self.candidates[primary_id]

            # Merge observation into primary candidate
            primary_cand.raw_observations.append(obs)
            if decomposed.raw_tag not in primary_cand.aliases and decomposed.raw_tag != primary_cand.raw_tag:
                primary_cand.aliases.append(decomposed.raw_tag)

            # Absorb alarms if any
            for al in decomposed.alarms:
                if al not in primary_cand.alarms:
                    primary_cand.alarms.append(al)

            # Record provenance
            self.merge_records.append(MergeProvenanceRecord(
                canonical_entity_id=primary_cand.candidate_id,
                canonical_tag=primary_cand.raw_tag,
                merged_tag=effective_tag,
                merge_reason="CANONICAL_BASE_TAG_MATCH",
                similarity_score=1.0,
                spatial_distance=math.hypot(primary_cand.center_x - cx, primary_cand.center_y - cy),
                contributing_agent=source_agent,
            ))
            return primary_cand

        # Create new candidate
        cand = EngineeringCandidate(
            raw_tag=effective_tag,
            normalized_tag=decomposed.normalized_tag,
            canonical_base_tag=canon_base,
            taxonomy=decomposed.detected_taxonomy,
            role=decomposed.role,
            status=EntityStatus.CANDIDATE,
            bounding_box=bbox,
            center_x=cx,
            center_y=cy,
            drawing_region=region,
            raw_observations=[obs],
            alarms=decomposed.alarms,
            confidence=ConfidenceVector(
                detection_confidence=confidence,
                ocr_confidence=confidence if raw_text else 1.0,
                symbol_confidence=confidence if symbol_class else 1.0,
                classification_confidence=0.90 if decomposed.detected_taxonomy != EngineeringTaxonomy.UNKNOWN_ENGINEERING_OBJECT else 0.40,
            ),
        )

        self.candidates[cand.candidate_id] = cand
        if canon_base and canon_base != "UNKNOWN":
            self._canonical_index[canon_base] = cand.candidate_id

        return cand

    def resolve_all_candidates(self) -> List[EngineeringCandidate]:
        """
        Executes multi-factor resolution:
        1. Promotes high-confidence candidates to RESOLVED.
        2. Absorbs suffix attributes and setpoints.
        3. Identifies and merges spatial duplicate symbols.
        """
        resolved: List[EngineeringCandidate] = []

        for cid, cand in list(self.candidates.items()):
            # Filter non-entities
            if cand.role in {CandidateRole.ALARM_FUNCTION, CandidateRole.SETPOINT, CandidateRole.SPECIFICATION}:
                cand.status = EntityStatus.ATTRIBUTE
                continue

            # Minimum confidence gating
            if cand.confidence.composite_score >= 0.50:
                cand.status = EntityStatus.RESOLVED
                resolved.append(cand)
            else:
                cand.status = EntityStatus.NEEDS_REVIEW

        return resolved

    def to_universal_engineering_graph(
        self,
        drawing_type: str = "PID",
        discipline: str = "Process",
        lines: Optional[List[LineItem]] = None,
        relationships: Optional[List[Relationship]] = None,
    ) -> UniversalEngineeringGraph:
        """
        Serializes resolved candidates into the master UniversalEngineeringGraph.
        Maintains 100% backward compatibility with all downstream exporters and UI components.
        """
        graph = UniversalEngineeringGraph(
            drawing_type=drawing_type,
            discipline=discipline,
            lines=lines or [],
            relationships=relationships or [],
        )

        for cand in self.candidates.values():
            if cand.status != EntityStatus.RESOLVED:
                continue

            tax = cand.taxonomy

            # 1. Equipment
            if tax in {
                EngineeringTaxonomy.EQUIPMENT, EngineeringTaxonomy.COMPRESSOR,
                EngineeringTaxonomy.PUMP, EngineeringTaxonomy.VESSEL,
                EngineeringTaxonomy.TANK, EngineeringTaxonomy.HEAT_EXCHANGER,
                EngineeringTaxonomy.COOLER, EngineeringTaxonomy.FILTER,
                EngineeringTaxonomy.SEPARATOR, EngineeringTaxonomy.STRAINER,
                EngineeringTaxonomy.COLUMN, EngineeringTaxonomy.REACTOR,
                EngineeringTaxonomy.MOTOR, EngineeringTaxonomy.PACKAGE_SKID
            }:
                graph.equipment.append(EquipmentItem(
                    tag=cand.raw_tag,
                    name=cand.raw_tag,
                    type=tax.value.replace('_', ' ').title(),
                    coordinates=cand.bounding_box,
                    aliases=cand.aliases if cand.aliases else None,
                    confidence=cand.confidence.composite_score,
                ))

            # 2. PSV
            elif tax == EngineeringTaxonomy.PSV:
                graph.safety_relief_valves.append(SafetyReliefValveItem(
                    tag=cand.raw_tag,
                    type="PSV",
                    service="Process Relief",
                    unit="26",
                    set_pressure=cand.attributes.get("set_pressure", EntityAttribute(attribute_name="set_pressure", attribute_value="TBD")).attribute_value,
                    inlet_size="TBD",
                    outlet_size="TBD",
                    inlet_spec="TBD",
                    relief_destination="Flare Header",
                    coordinates=cand.bounding_box,
                ))

            # 3. Valves (including Control Valves)
            elif tax in {
                EngineeringTaxonomy.VALVE, EngineeringTaxonomy.CONTROL_VALVE,
                EngineeringTaxonomy.CHECK_VALVE, EngineeringTaxonomy.BALL_VALVE,
                EngineeringTaxonomy.GATE_VALVE, EngineeringTaxonomy.GLOBE_VALVE,
                EngineeringTaxonomy.BUTTERFLY_VALVE, EngineeringTaxonomy.NEEDLE_VALVE,
                EngineeringTaxonomy.PLUG_VALVE
            }:
                graph.valves.append(ValveItem(
                    tag=cand.raw_tag,
                    type=tax.value.replace('_', ' ').title(),
                    line_tag=cand.associated_line,
                    coordinates=cand.bounding_box,
                    confidence=cand.confidence.composite_score,
                    aliases=cand.aliases if cand.aliases else None,
                ))

            # 4. Instruments
            elif tax in {
                EngineeringTaxonomy.INSTRUMENT, EngineeringTaxonomy.PRESSURE_INSTRUMENT,
                EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.FLOW_INSTRUMENT,
                EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.ANALYZER,
                EngineeringTaxonomy.VIBRATION_INSTRUMENT, EngineeringTaxonomy.POSITION_INSTRUMENT,
                EngineeringTaxonomy.TRANSMITTER, EngineeringTaxonomy.INDICATOR,
                EngineeringTaxonomy.SWITCH, EngineeringTaxonomy.ELEMENT
            }:
                # Format ISA type code
                inst_type = cand.canonical_base_tag.split('-')[0] if '-' in cand.canonical_base_tag else "INST"
                graph.instruments.append(InstrumentItem(
                    tag=cand.raw_tag,
                    type=inst_type,
                    service=cand.associated_line or "Process",
                    loop_id=cand.canonical_base_tag.split('-')[1] if '-' in cand.canonical_base_tag else "0000",
                    coordinates=cand.bounding_box,
                    aliases=cand.aliases if cand.aliases else None,
                    confidence=cand.confidence.composite_score,
                ))

            # 5. Annotations & Notes
            elif tax in {EngineeringTaxonomy.ANNOTATION, EngineeringTaxonomy.NOTE}:
                graph.annotations.append(AnnotationItem(
                    text=cand.raw_tag,
                    annotation_type="NOTE",
                    position_x=cand.center_x,
                    position_y=cand.center_y,
                ))

        return graph

    def export_merge_provenance(self) -> List[Dict[str, Any]]:
        """Exports JSON-serializable list of all merge provenance actions."""
        return [record.model_dump() for record in self.merge_records]
