"""
Universal Engineering Drawing Data Models.

Contains both the original P&ID-specific models (backward-compatible)
and new discipline-specific models for Electrical, Earthing, HVAC, etc.

The top-level container is UniversalEngineeringGraph which carries a
drawing_type field and all relevant entity lists.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# P&ID / Process — original models (unchanged for backward compatibility)
# ──────────────────────────────────────────────────────────────────────────────

class EquipmentItem(BaseModel):
    """Represents an equipment component extracted from the drawing (Pumps, Vessels, Compressors, etc.)."""
    tag: str = Field(description="Unique identifier tag of the equipment (e.g., 26-KA-901, TK-101)")
    name: str = Field(description="Name or standard designation of the equipment")
    type: str = Field(description="Type classification (e.g., Centrifugal Compressor, Vessel, Heat Exchanger)")
    description: Optional[str] = Field(default=None, description="Detailed description or service detail")
    design_pressure: Optional[str] = Field(default=None, description="Design pressure (e.g., FV / 286 Barg)")
    design_temperature: Optional[str] = Field(default=None, description="Design temperature (e.g., -46 / 160 °C)")
    flow_rate: Optional[str] = Field(default=None, description="Flow rate (e.g., 62809 kg/h)")
    duty: Optional[str] = Field(default=None, description="Duty rating (e.g., 1835 kW)")
    material: Optional[str] = Field(default=None, description="Material of construction")
    location: Optional[str] = Field(default=None, description="Physical location or footprint grid reference")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class LineItem(BaseModel):
    """Represents a piping line trace."""
    tag: str = Field(description="Complete line identifier/tag (e.g., 8\"-PV-26-9035-FC11S-08)")
    size: str = Field(description="Nominal size derived from the line tag (e.g., 8\")")
    service: str = Field(description="Service fluid code (e.g., PV, DC, WC, AI, GI)")
    spec: str = Field(description="Piping specification code (e.g., FC11S, AC21, GS20)")
    sequence_number: str = Field(description="Sequential identifier number (e.g., 9035)")
    insulation: Optional[str] = Field(default=None, description="Insulation type or specification code")
    from_node: Optional[str] = Field(default=None, description="Source tag where the line originates")
    to_node: Optional[str] = Field(default=None, description="Destination tag where the line terminates")
    coordinates: Optional[List[List[float]]] = Field(default=None, description="Polyline path coordinates")


class InstrumentItem(BaseModel):
    """Represents an instrument bubble/sensor."""
    tag: str = Field(description="Unique instrument identifier tag (e.g., PIT-9055 or 26-PIT-9055)")
    type: str = Field(description="Instrument function type code (e.g., PIT, TIT, FE, PSV, PDIT, FI)")
    service: Optional[str] = Field(default=None, description="Service classification or associated line tag")
    location: Optional[str] = Field(default="Field", description="Physical location (e.g., Field, UCP, Control Room)")
    loop_id: Optional[str] = Field(default=None, description="Instrument loop identifier number (e.g., 9055)")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class ValveItem(BaseModel):
    """Represents a piping valve, typically manual."""
    tag: str = Field(description="Unique valve tag identifier (e.g., 26GB9178, HV-101)")
    type: str = Field(description="Valve type (e.g., Gate Valve, Globe Valve, Ball Valve, Check Valve)")
    size: Optional[str] = Field(default=None, description="Size of the valve (derived from host line)")
    line_tag: Optional[str] = Field(default=None, description="Tag of the line on which this valve is installed")
    rating: Optional[str] = Field(default=None, description="Pressure rating class (e.g., 150#, 300#, 2500#)")
    normal_state: Optional[str] = Field(default=None, description="Normal operation state (e.g., CSO, LO, N)")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class SafetyReliefValveItem(BaseModel):
    """Represents a Pressure Safety / Relief Valve (PSV) with process safety details."""
    tag: str = Field(description="PSV Tag (e.g. 26-PSV-9066A)")
    type: str = Field(default="PSV", description="Type (e.g. PSV, PRV, PVRV)")
    service: str = Field(description="Service / Description")
    unit: str = Field(default="", description="Unit or area identifier")
    set_pressure: str = Field(description="Set Pressure (barg)")
    inlet_size: str = Field(description="Inlet Size")
    outlet_size: str = Field(description="Outlet Size")
    inlet_spec: str = Field(description="Inlet Spec")
    relief_destination: str = Field(description="Relief Destination")
    remarks: Optional[str] = Field(default=None, description="Remarks")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class Relationship(BaseModel):
    """Represents a directional relationship between two components."""
    source: str = Field(description="Source component tag identifier")
    target: str = Field(description="Target component tag identifier")
    type: str = Field(description="Type of connection (e.g., 'connects_to', 'measures', 'controls', 'mounted_on')")
    confidence: float = Field(default=1.0, description="Extraction confidence level")
    attributes: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata for the connection")

    @property
    def source_tag(self) -> str:
        return self.source

    @property
    def target_tag(self) -> str:
        return self.target

    @property
    def rel_type(self) -> str:
        return self.type.upper()


# ──────────────────────────────────────────────────────────────────────────────
# Electrical Layout Models
# ──────────────────────────────────────────────────────────────────────────────

class LuminaireItem(BaseModel):
    """Represents a light fitting / luminaire in an electrical layout drawing."""
    tag: str = Field(description="Luminaire tag (e.g., L-01, LS-201, TL-101)")
    fitting_type: Optional[str] = Field(default=None, description="Type of fitting (e.g., LED Batten, Floodlight, Downlight)")
    wattage: Optional[str] = Field(default=None, description="Wattage or power rating (e.g., 36W, 2x36W)")
    circuit: Optional[str] = Field(default=None, description="Electrical circuit reference (e.g., C-01, MCB-3)")
    panel: Optional[str] = Field(default=None, description="Distribution board / panel it is fed from")
    elevation: Optional[str] = Field(default=None, description="Installation elevation label (e.g., EL.101.445)")
    location: Optional[str] = Field(default=None, description="Location or area description")
    quantity: Optional[int] = Field(default=1, description="Quantity if multiple fittings shown")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class PanelItem(BaseModel):
    """Represents a distribution board, MDB, LDB, SMDB or switchgear panel."""
    tag: str = Field(description="Panel / DB tag (e.g., DB-01, MDB-A, LDB-3, SMDB)")
    panel_type: Optional[str] = Field(default=None, description="Type (e.g., MDB, LDB, EMDB, MSB)")
    voltage: Optional[str] = Field(default=None, description="Voltage level (e.g., 415V, 11kV)")
    capacity_kva: Optional[str] = Field(default=None, description="Capacity in kVA")
    feeder_from: Optional[str] = Field(default=None, description="Upstream source panel or transformer")
    location: Optional[str] = Field(default=None, description="Physical location or room")
    description: Optional[str] = Field(default=None, description="Description or service")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class CableItem(BaseModel):
    """Represents an electrical cable or wiring run."""
    tag: str = Field(description="Cable tag or circuit reference (e.g., CB-01, C-101, MCB-3)")
    cable_type: Optional[str] = Field(default=None, description="Cable type (e.g., XLPE/SWA/PVC, NYY)")
    size_mm2: Optional[str] = Field(default=None, description="Cross-sectional area (e.g., 2.5mm², 16mm²)")
    cores: Optional[str] = Field(default=None, description="Number of cores (e.g., 3C+E, 4C)")
    from_panel: Optional[str] = Field(default=None, description="Source panel or DB")
    to_equipment: Optional[str] = Field(default=None, description="Destination equipment or panel")
    length_m: Optional[str] = Field(default=None, description="Approximate cable length in metres")
    route: Optional[str] = Field(default=None, description="Cable routing description or tray reference")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


# ──────────────────────────────────────────────────────────────────────────────
# Earthing Layout Models
# ──────────────────────────────────────────────────────────────────────────────

class EarthingItem(BaseModel):
    """Represents an earthing / grounding component (earth bar, earth pit, conductor)."""
    tag: str = Field(description="Earthing component tag (e.g., EB-01, EP-01, BC-01)")
    component_type: str = Field(description="Component type: EARTH_BAR, EARTH_PIT, BOND_CONDUCTOR, EARTH_ELECTRODE")
    material: Optional[str] = Field(default=None, description="Material (e.g., 50x6mm Copper Tape, 95mm² Green/Yellow)")
    size: Optional[str] = Field(default=None, description="Size or cross-section")
    connected_to: Optional[str] = Field(default=None, description="Connected equipment or structure tag")
    location: Optional[str] = Field(default=None, description="Physical location or area")
    elevation: Optional[str] = Field(default=None, description="Elevation reference label")
    resistance: Optional[str] = Field(default=None, description="Measured or design resistance (e.g., <1 Ohm)")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


# ──────────────────────────────────────────────────────────────────────────────
# Generic / Fallback Models
# ──────────────────────────────────────────────────────────────────────────────

class GenericComponentItem(BaseModel):
    """Generic engineering component for any drawing type not covered by specific models."""
    tag: str = Field(description="Component tag or identifier")
    classification: str = Field(description="OCR classification (e.g., EQUIPMENT_TAG, PANEL_TAG, NOTE)")
    description: Optional[str] = Field(default=None, description="Description or label from drawing")
    attributes: Optional[Dict[str, Any]] = Field(default=None, description="Any additional extracted attributes")
    coordinates: Optional[List[float]] = Field(default=None, description="Bounding box [ymin, xmin, ymax, xmax]")


class AnnotationItem(BaseModel):
    """Text annotation, elevation label, note, or reference extracted from any drawing."""
    text: str = Field(description="The annotation text content")
    annotation_type: str = Field(description="Type: NOTE, ELEVATION, GRID_REF, TITLE, LEGEND, DIMENSION")
    position_x: Optional[float] = Field(default=None, description="Normalized X position on drawing [0-1]")
    position_y: Optional[float] = Field(default=None, description="Normalized Y position on drawing [0-1]")


# ──────────────────────────────────────────────────────────────────────────────
# Legacy P&ID Graph (backward-compatible)
# ──────────────────────────────────────────────────────────────────────────────

class EngineeringGraph(BaseModel):
    """
    P&ID-specific master structure (kept for backward compatibility).
    For universal drawing support, use UniversalEngineeringGraph.
    """
    equipment: List[EquipmentItem] = Field(default_factory=list)
    lines: List[LineItem] = Field(default_factory=list)
    instruments: List[InstrumentItem] = Field(default_factory=list)
    valves: List[ValveItem] = Field(default_factory=list)
    safety_relief_valves: List[SafetyReliefValveItem] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Universal Engineering Graph — top-level output container
# ──────────────────────────────────────────────────────────────────────────────

class UniversalEngineeringGraph(BaseModel):
    """
    Universal master structure for ANY engineering drawing type.
    Extends the P&ID-specific EngineeringGraph with electrical, earthing,
    and generic entity lists. The drawing_type field drives how the UI
    and output generators render and export results.
    """
    # Drawing identity
    drawing_type: str = Field(
        default="GENERIC",
        description="Detected drawing type (PID, ELECTRICAL_LAYOUT, EARTHING_LAYOUT, SLD, etc.)"
    )
    discipline: str = Field(
        default="Unknown",
        description="Engineering discipline (Process, Electrical, Civil/Structural, etc.)"
    )

    # ── P&ID / Process ──────────────────────────────────────────────────────
    equipment: List[EquipmentItem] = Field(
        default_factory=list,
        description="Equipment items (compressors, vessels, pumps, tanks, etc.)"
    )
    lines: List[LineItem] = Field(
        default_factory=list,
        description="Piping line items (P&ID / isometric)"
    )
    instruments: List[InstrumentItem] = Field(
        default_factory=list,
        description="Instrument bubbles and sensors"
    )
    valves: List[ValveItem] = Field(
        default_factory=list,
        description="Piping valves (manual, control, check, etc.)"
    )
    safety_relief_valves: List[SafetyReliefValveItem] = Field(
        default_factory=list,
        description="Pressure safety / relief valves"
    )

    # ── Electrical Layout ────────────────────────────────────────────────────
    luminaires: List[LuminaireItem] = Field(
        default_factory=list,
        description="Light fittings / luminaires (Electrical Layout)"
    )
    panels: List[PanelItem] = Field(
        default_factory=list,
        description="Distribution boards, MDBs, LDBs, switchgear panels (Electrical / SLD)"
    )
    cables: List[CableItem] = Field(
        default_factory=list,
        description="Cable and wiring runs (Electrical Layout / Cable Schedule)"
    )

    # ── Earthing Layout ──────────────────────────────────────────────────────
    earthing_components: List[EarthingItem] = Field(
        default_factory=list,
        description="Earthing bars, earth pits, bonding conductors (Earthing Layout)"
    )

    # ── Generic / Annotations ────────────────────────────────────────────────
    generic_components: List[GenericComponentItem] = Field(
        default_factory=list,
        description="Generic components for drawing types without specific models"
    )
    annotations: List[AnnotationItem] = Field(
        default_factory=list,
        description="Text annotations, elevation labels, notes from any drawing type"
    )

    # ── Cross-drawing Relationships ──────────────────────────────────────────
    relationships: List[Relationship] = Field(
        default_factory=list,
        description="Connectivity mapping across all component types"
    )

    def to_engineering_graph(self) -> EngineeringGraph:
        """Downcast to the legacy EngineeringGraph for backward-compatible export functions."""
        return EngineeringGraph(
            equipment=self.equipment,
            lines=self.lines,
            instruments=self.instruments,
            valves=self.valves,
            safety_relief_valves=self.safety_relief_valves,
            relationships=self.relationships,
        )

    @property
    def total_items(self) -> int:
        """Total number of extracted items across all entity types."""
        return (
            len(self.equipment) + len(self.lines) + len(self.instruments) +
            len(self.valves) + len(self.safety_relief_valves) +
            len(self.luminaires) + len(self.panels) + len(self.cables) +
            len(self.earthing_components) + len(self.generic_components) +
            len(self.annotations)
        )
