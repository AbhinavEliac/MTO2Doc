"""
Universal Engineering Entity Taxonomy & Classification Layer.

Defines:
1. Universal Engineering Entity Taxonomy (ISA 5.1 / ISO 15926 / CFIHOS / IEC).
2. Entity Lifecycle Statuses.
3. Candidate Roles & Evidence Types.
4. Drawing Region Classifications.
5. Deterministic, evidence-based tag decomposition and classification rules:
   - Critical Valve vs. Instrument vs. Control Function resolution.
   - Alarm and setpoint attribute separation.
   - Base tag vs. suffix extraction.
   - Equipment and sub-component parsing.
"""

from __future__ import annotations

import re
import enum
from typing import Dict, Any, List, Optional, Tuple, Set
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# 1. Universal Engineering Taxonomy Enums
# ──────────────────────────────────────────────────────────────────────────────

class EngineeringTaxonomy(str, enum.Enum):
    """
    Standard engineering entity taxonomy adhering to ISA 5.1 and ISO 15926.
    Every candidate resolves to one of these types or UNKNOWN_ENGINEERING_OBJECT.
    """
    # Piping & Transport
    LINE = "LINE"
    PIPELINE = "PIPELINE"
    
    # Valves (Physical in-line piping components)
    VALVE = "VALVE"
    CONTROL_VALVE = "CONTROL_VALVE"
    CHECK_VALVE = "CHECK_VALVE"
    BALL_VALVE = "BALL_VALVE"
    GATE_VALVE = "GATE_VALVE"
    GLOBE_VALVE = "GLOBE_VALVE"
    BUTTERFLY_VALVE = "BUTTERFLY_VALVE"
    NEEDLE_VALVE = "NEEDLE_VALVE"
    PLUG_VALVE = "PLUG_VALVE"
    RELIEF_VALVE = "RELIEF_VALVE"
    SAFETY_VALVE = "SAFETY_VALVE"
    PSV = "PSV"

    # Instruments (Physical measuring / sensing bubbles and devices)
    INSTRUMENT = "INSTRUMENT"
    PRESSURE_INSTRUMENT = "PRESSURE_INSTRUMENT"
    TEMPERATURE_INSTRUMENT = "TEMPERATURE_INSTRUMENT"
    FLOW_INSTRUMENT = "FLOW_INSTRUMENT"
    LEVEL_INSTRUMENT = "LEVEL_INSTRUMENT"
    ANALYZER = "ANALYZER"
    VIBRATION_INSTRUMENT = "VIBRATION_INSTRUMENT"
    POSITION_INSTRUMENT = "POSITION_INSTRUMENT"

    # Instrument Functions & Signal Elements (Logical / Control Layer)
    CONTROL_FUNCTION = "CONTROL_FUNCTION"
    INDICATOR = "INDICATOR"
    TRANSMITTER = "TRANSMITTER"
    SWITCH = "SWITCH"
    ELEMENT = "ELEMENT"
    CONTROLLER = "CONTROLLER"
    SAFETY_INTERLOCK = "SAFETY_INTERLOCK"

    # Major Equipment
    EQUIPMENT = "EQUIPMENT"
    COMPRESSOR = "COMPRESSOR"
    PUMP = "PUMP"
    VESSEL = "VESSEL"
    TANK = "TANK"
    HEAT_EXCHANGER = "HEAT_EXCHANGER"
    COOLER = "COOLER"
    FILTER = "FILTER"
    SEPARATOR = "SEPARATOR"
    STRAINER = "STRAINER"
    COLUMN = "COLUMN"
    REACTOR = "REACTOR"
    DRIVER = "DRIVER"
    MOTOR = "MOTOR"
    TURBINE = "TURBINE"
    PACKAGE_SKID = "PACKAGE_SKID"

    # Physical Nozzles, Ports & Junctions
    NOZZLE = "NOZZLE"
    JUNCTION = "JUNCTION"
    CONNECTION = "CONNECTION"

    # Electrical & Earthing Entities
    PANEL = "PANEL"
    LUMINAIRE = "LUMINAIRE"
    CABLE = "CABLE"
    CIRCUIT = "CIRCUIT"
    EARTH_BAR = "EARTH_BAR"
    EARTH_PIT = "EARTH_PIT"
    BOND_CONDUCTOR = "BOND_CONDUCTOR"

    # Non-Entity Data (Attributes, Annotations, Documentation)
    ANNOTATION = "ANNOTATION"
    NOTE = "NOTE"
    ATTRIBUTE = "ATTRIBUTE"
    SPECIFICATION = "SPECIFICATION"
    REFERENCE = "REFERENCE"
    LEGEND_OBJECT = "LEGEND_OBJECT"
    TITLE_BLOCK_OBJECT = "TITLE_BLOCK_OBJECT"
    
    # Uncertainty States
    UNKNOWN_ENGINEERING_OBJECT = "UNKNOWN_ENGINEERING_OBJECT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class EntityStatus(str, enum.Enum):
    """
    Lifecycle status of an engineering candidate.
    Only RESOLVED items with sufficient confidence enter the final engineering graph.
    """
    CANDIDATE = "CANDIDATE"              # Newly observed, undergoing evidence fusion
    RESOLVED = "RESOLVED"                # Verified canonical engineering entity
    REJECTED = "REJECTED"                # Excluded (noise, fragment, invalid grammar)
    DUPLICATE = "DUPLICATE"              # Merged into a primary canonical entity
    ATTRIBUTE = "ATTRIBUTE"              # Subsumed as an attribute/alarm of a primary entity
    ANNOTATION = "ANNOTATION"            # Pure text callout, elevation, or drawing note
    REFERENCE = "REFERENCE"              # Off-page continuation, tie-in, or drawing pointer
    NEEDS_REVIEW = "NEEDS_REVIEW"        # Ambiguous observation flagged for human check
    UNKNOWN = "UNKNOWN"                  # Evidence insufficient to classify


class CandidateRole(str, enum.Enum):
    """
    Semantic role of an observation before promotion to entity.
    """
    BASE_TAG = "BASE_TAG"                # Primary component identifier (e.g. 26-PIT-9055)
    SUFFIX_ATTRIBUTE = "SUFFIX_ATTRIBUTE"# Alarm or state suffix (e.g. HH, LL, FO)
    ALARM_FUNCTION = "ALARM_FUNCTION"    # High/Low alarm callout
    SETPOINT = "SETPOINT"                # Operating setpoint (e.g. 225.4 BARG)
    SPECIFICATION = "SPECIFICATION"      # Pipe/material spec (e.g. FC11S, 150#)
    SERVICE_DESCRIPTION = "SERVICE_DESCRIPTION" # Fluid/service label (e.g. FUEL GAS)
    EQUIPMENT_DESCRIPTOR = "EQUIPMENT_DESCRIPTOR" # Parameter table row (Duty, Flow, etc.)
    GRAPHIC_SYMBOL = "GRAPHIC_SYMBOL"    # Visual geometry / bounding box
    NOTE = "NOTE"                        # Numbered drawing note or hold note
    TITLE_BLOCK = "TITLE_BLOCK"          # Drawing metadata block
    LEGEND = "LEGEND"                    # Legend or symbol definition item


class DrawingRegion(str, enum.Enum):
    """
    Functional layout zone of an engineering drawing sheet.
    """
    PROCESS_AREA = "PROCESS_AREA"
    EQUIPMENT_AREA = "EQUIPMENT_AREA"
    INSTRUMENT_AREA = "INSTRUMENT_AREA"
    VALVE_AREA = "VALVE_AREA"
    NOTES_AREA = "NOTES_AREA"
    LEGEND = "LEGEND"
    TITLE_BLOCK = "TITLE_BLOCK"
    REVISION_BLOCK = "REVISION_BLOCK"
    EQUIPMENT_TABLE = "EQUIPMENT_TABLE"
    LINE_LIST = "LINE_LIST"
    SPECIFICATION_TABLE = "SPECIFICATION_TABLE"
    WORK_PACK = "WORK_PACK"
    CONSTRUCTION_HOLD = "CONSTRUCTION_HOLD"
    REFERENCE_AREA = "REFERENCE_AREA"
    UNKNOWN_REGION = "UNKNOWN_REGION"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Known Engineering Code Sets & Dictionaries
# ──────────────────────────────────────────────────────────────────────────────

# Control Valve Function Prefixes (ISA 5.1).
# These represent PHYSICAL VALVES that perform control functions, NOT standalone instruments!
CONTROL_VALVE_CODES: Set[str] = {
    'FV', 'PV', 'TV', 'LV', 'HV', 'XV', 'CV', 'FCV', 'PCV', 'TCV', 'LCV',
    'MOV', 'SDV', 'BDV', 'ESV', 'UV', 'ZV'
}

# In-line Manual / Check / Relief Valve Prefixes
MANUAL_AND_RELIEF_VALVE_CODES: Set[str] = {
    'GB', 'CB', 'BL', 'GT', 'GL', 'CK', 'NV', 'ND', 'BV', 'PL', 'BF', 'BFV',
    'PLV', 'PSV', 'PRV', 'PVRV', 'V', 'RV', 'SV', 'DV'
}

# ISA 5.1 Instrument Function Prefix to Taxonomy Map:
# Maps prefix -> (Device Category, Logical Function).
# e.g. 'PIT' -> (PRESSURE_INSTRUMENT, TRANSMITTER)
INSTRUMENT_PREFIX_MAP: Dict[str, Tuple[EngineeringTaxonomy, EngineeringTaxonomy]] = {
    # Pressure
    'PIT': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'PDIT': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'PDT': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'PT': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'PI': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'PDI': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'PIC': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    'PSH': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'PSL': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'PE': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'PSE': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.ELEMENT), # Rupture Disc / Safety Element
    'PY': (EngineeringTaxonomy.PRESSURE_INSTRUMENT, EngineeringTaxonomy.CONTROLLER), # Pressure Relay
    
    # Temperature
    'TIT': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'TT': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'TI': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'TIC': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    'TSH': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'TSL': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'TE': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'TW': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'TY': (EngineeringTaxonomy.TEMPERATURE_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    
    # Flow
    'FIT': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'FT': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'FI': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'FIC': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    'FE': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'FO': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'FSH': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'FSL': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'FY': (EngineeringTaxonomy.FLOW_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    
    # Level
    'LIT': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'LT': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'LI': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'LIC': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    'LG': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'LSH': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'LSL': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    'LE': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.ELEMENT),
    'LY': (EngineeringTaxonomy.LEVEL_INSTRUMENT, EngineeringTaxonomy.CONTROLLER),
    
    # Vibration & Mechanical
    'VIT': (EngineeringTaxonomy.VIBRATION_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'VT': (EngineeringTaxonomy.VIBRATION_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'VI': (EngineeringTaxonomy.VIBRATION_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'VS': (EngineeringTaxonomy.VIBRATION_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    
    # Position
    'ZIT': (EngineeringTaxonomy.POSITION_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'ZT': (EngineeringTaxonomy.POSITION_INSTRUMENT, EngineeringTaxonomy.TRANSMITTER),
    'ZI': (EngineeringTaxonomy.POSITION_INSTRUMENT, EngineeringTaxonomy.INDICATOR),
    'ZS': (EngineeringTaxonomy.POSITION_INSTRUMENT, EngineeringTaxonomy.SWITCH),
    
    # Analytical
    'AIT': (EngineeringTaxonomy.ANALYZER, EngineeringTaxonomy.TRANSMITTER),
    'AT': (EngineeringTaxonomy.ANALYZER, EngineeringTaxonomy.TRANSMITTER),
    'AI': (EngineeringTaxonomy.ANALYZER, EngineeringTaxonomy.INDICATOR),
}

# Major Equipment Codes to Taxonomy
EQUIPMENT_CODE_MAP: Dict[str, EngineeringTaxonomy] = {
    'KA': EngineeringTaxonomy.COMPRESSOR,
    'KB': EngineeringTaxonomy.COMPRESSOR,
    'KC': EngineeringTaxonomy.COMPRESSOR,
    'CP': EngineeringTaxonomy.COMPRESSOR,
    'CM': EngineeringTaxonomy.COMPRESSOR,
    'KT': EngineeringTaxonomy.TURBINE,
    'HA': EngineeringTaxonomy.HEAT_EXCHANGER,
    'HB': EngineeringTaxonomy.HEAT_EXCHANGER,
    'HC': EngineeringTaxonomy.HEAT_EXCHANGER,
    'HX': EngineeringTaxonomy.HEAT_EXCHANGER,
    'HE': EngineeringTaxonomy.HEAT_EXCHANGER,
    'EA': EngineeringTaxonomy.COOLER,
    'EB': EngineeringTaxonomy.HEAT_EXCHANGER,
    'VA': EngineeringTaxonomy.VESSEL,
    'VB': EngineeringTaxonomy.VESSEL,
    'VC': EngineeringTaxonomy.VESSEL,
    'TK': EngineeringTaxonomy.TANK,
    'TA': EngineeringTaxonomy.TANK,
    'DA': EngineeringTaxonomy.VESSEL, # Knockout Drum
    'DB': EngineeringTaxonomy.VESSEL,
    'KO': EngineeringTaxonomy.VESSEL,
    'CA': EngineeringTaxonomy.COLUMN,
    'CB': EngineeringTaxonomy.COLUMN,
    'R':  EngineeringTaxonomy.REACTOR,
    'PA': EngineeringTaxonomy.PUMP,
    'PB': EngineeringTaxonomy.PUMP,
    'PC': EngineeringTaxonomy.PUMP,
    'GA': EngineeringTaxonomy.PUMP,
    'GB': EngineeringTaxonomy.PUMP,
    'PM': EngineeringTaxonomy.PUMP,
    'FA': EngineeringTaxonomy.FILTER,
    'FB': EngineeringTaxonomy.FILTER,
    'FC': EngineeringTaxonomy.FILTER,
    'FL': EngineeringTaxonomy.FILTER,
    'CX': EngineeringTaxonomy.SEPARATOR, # Coalescing Separator
    'SA': EngineeringTaxonomy.SEPARATOR, # Scrubber
    'SB': EngineeringTaxonomy.SEPARATOR,
    'SC': EngineeringTaxonomy.SEPARATOR,
    'ST': EngineeringTaxonomy.STRAINER,
    'CK': EngineeringTaxonomy.STRAINER, # Temporary Commissioning Strainer / Cone Strainer
    'KZ': EngineeringTaxonomy.PACKAGE_SKID,
    'SK': EngineeringTaxonomy.PACKAGE_SKID,
    'PK': EngineeringTaxonomy.PACKAGE_SKID,
    'PKG': EngineeringTaxonomy.PACKAGE_SKID,
}

# Known Alarm Suffixes and Parameter Modifiers that attach to an Entity rather than creating a new physical device
ALARM_SUFFIX_PATTERNS = re.compile(
    r'[-_]?(HH|LL|H|L|HIGH|LOW|TRIP|SD|ESD|ALARM|ALM|SH|SL|AH|AL|O|C|ZSO|ZSC|MEDIUM|OIL|GAS|STAGE|HP|LP|DUTY|STANDBY|150|300|600|2|N\d{4})$',
    re.IGNORECASE
)

# Known Valve State & Rating Suffixes
VALVE_STATE_PATTERNS = re.compile(
    r'[-_]?(FO|FC|FAI|FL|LO|LC|CSO|CSC|NC|NO|N|150#|300#|600#|900#|1500#|2500#)$',
    re.IGNORECASE
)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Evidence-Aware Tag Decomposition & Classification
# ──────────────────────────────────────────────────────────────────────────────

class DecomposedTag(BaseModel):
    """
    Deconstructed representation of an engineering tag string.
    Ensures attributes, alarms, and area prefixes are isolated cleanly.
    """
    raw_tag: str
    normalized_tag: str
    canonical_base_tag: str          # e.g., 'PDIT-9054' (without area prefix or alarm suffix)
    area_prefix: Optional[str] = None# e.g., '26'
    function_code: str               # e.g., 'PDIT', 'FV', 'KA', 'PV'
    sequence_number: str             # e.g., '9054'
    suffix: Optional[str] = None     # e.g., 'A', 'B' (train/sibling suffix)
    alarms: List[str] = Field(default_factory=list) # e.g., ['HH', 'TRIP']
    sub_component: Optional[str] = None # e.g., 'M01' for motor driver
    detected_taxonomy: EngineeringTaxonomy
    secondary_function: Optional[EngineeringTaxonomy] = None
    role: CandidateRole
    is_valve: bool = False
    is_instrument: bool = False
    is_equipment: bool = False
    is_line: bool = False


def decompose_engineering_tag(
    raw_tag: str,
    graphic_hint: Optional[str] = None
) -> DecomposedTag:
    """
    Deconstructs a raw tag string into its canonical engineering components.
    
    Examples:
      '26-PDI-9054-HH' -> canonical_base='PDI-9054', alarms=['HH'], taxonomy=PRESSURE_INSTRUMENT
      '26-FV-9076'     -> canonical_base='FV-9076', taxonomy=CONTROL_VALVE, is_valve=True
      '26-KA-901-M01'  -> canonical_base='KA-901', sub_component='M01', taxonomy=MOTOR
      '8"-PV-26-9035-FC11S-08' -> taxonomy=LINE, is_line=True
    """
    cleaned = raw_tag.strip().upper()
    cleaned = re.sub(r'\s+', '', cleaned)

    # 1. Detect Line Tags: MUST have explicit pipe size mark (", ', mm, DN) or full ISA 4-6 part piping spec
    has_explicit_pipe_size = bool(
        re.match(r'^\d+(?:[/\.]\d+)?(?:["\']|MM|DN)(?:-|$)', cleaned, re.I) or
        re.match(r'^\d+/\d+["\']', cleaned) or
        ('"' in cleaned and re.search(r'[A-Z]{2,4}-\d{3,5}', cleaned))
    )
    
    # Line tags without size (e.g. PV-26-9035-FC11S-08) — must have service + unit + seq + spec
    is_nosize_line = bool(
        re.match(r'^[A-Z]{2,4}-\d{2,4}-\d{3,5}-[A-Z]{2}\d{2,3}[A-Z0-9]?(?:-\d{2})?$', cleaned)
    )

    if has_explicit_pipe_size or is_nosize_line:
        line_match = re.match(
            r'^(\d+(?:[/\.]\d+)?(?:["\']|MM|DN)?)-([A-Z]{1,4})-(\d{1,4}-)?(\d{3,5})(-[A-Z0-9]+)?(-[A-Z0-9]+)?$',
            cleaned
        )
        seq_val = line_match.group(4) if (line_match and line_match.group(4)) else "0000"
        return DecomposedTag(
            raw_tag=raw_tag,
            normalized_tag=cleaned,
            canonical_base_tag=cleaned,
            function_code="LINE",
            sequence_number=seq_val,
            detected_taxonomy=EngineeringTaxonomy.LINE,
            role=CandidateRole.BASE_TAG,
            is_line=True,
        )

    # 2. Check for Alarm / Suffix stripping
    alarms: List[str] = []
    base_no_alarm = cleaned
    m_alarm = ALARM_SUFFIX_PATTERNS.search(cleaned)
    if m_alarm and not re.search(r'-(?:M\d{2}|C0\d)$', cleaned):
        # Verify it's not a normal tag sequence
        suffix_str = m_alarm.group(1).upper()
        if suffix_str in {'HH', 'LL', 'H', 'L', 'HIGH', 'LOW', 'TRIP', 'SD', 'ESD', 'ALARM', 'ALM'}:
            alarms.append(suffix_str)
            base_no_alarm = cleaned[:m_alarm.start()].rstrip('-_')

    # 3. Extract Area Prefix (e.g. '26-')
    area_prefix = None
    core_tag = base_no_alarm
    m_prefix = re.match(r'^(\d{2,3})-([A-Z0-9].*)$', base_no_alarm)
    if m_prefix:
        area_prefix = m_prefix.group(1)
        core_tag = m_prefix.group(2)

    # 4. Check for Motor / Sub-component Driver (e.g. '26-KA-901-M01')
    sub_comp = None
    m_sub = re.search(r'-(M\d{1,2}|MOTOR|STAGE\d?|C0\d)$', core_tag)
    if m_sub:
        sub_comp = m_sub.group(1)
        core_tag = core_tag[:m_sub.start()]

    # 5. Extract Function Code and Sequence Number
    # Match standard patterns like 'PIT-9054', 'FV-9076', '26CB9131', 'KA-901'
    m_code = re.match(r'^([A-Z]{1,5})-?(\d{2,5})([A-Z])?$', core_tag)
    if not m_code:
        # Try dense valve format like 'CB9131' or 'GB9178'
        m_code = re.match(r'^([A-Z]{2})(\d{3,5})([A-Z])?$', core_tag)

    if m_code:
        fcode = m_code.group(1)
        seq_num = m_code.group(2)
        sib_suffix = m_code.group(3) if len(m_code.groups()) >= 3 else None
        canon_base = f"{fcode}-{seq_num}" + (sib_suffix if sib_suffix else "")
    else:
        fcode = re.search(r'([A-Z]{1,5})', core_tag).group(1) if re.search(r'([A-Z]{1,5})', core_tag) else "UNKNOWN"
        seq_num = re.search(r'(\d{2,5})', core_tag).group(1) if re.search(r'(\d{2,5})', core_tag) else "0000"
        sib_suffix = None
        canon_base = core_tag

    # 6. Critical Resolution: Valve vs. Instrument vs. Equipment
    taxonomy = EngineeringTaxonomy.UNKNOWN_ENGINEERING_OBJECT
    sec_func = None
    is_valve = False
    is_inst = False
    is_equip = False
    role = CandidateRole.BASE_TAG

    # A. PSV / Safety Relief Valve
    if fcode == 'PSV' or 'PSV' in raw_tag.upper():
        taxonomy = EngineeringTaxonomy.PSV
        is_valve = True
        is_inst = False

    # B. Control Valves (FV, PV, TV, LV, XV, HV, CV, FCV, PCV, TCV, LCV, MOV, SDV, BDV)
    # These represent IN-LINE VALVES executing a control function!
    elif fcode in CONTROL_VALVE_CODES or (graphic_hint and "VALVE" in graphic_hint.upper() and fcode in {'FV', 'PV', 'TV', 'LV', 'XV', 'HV'}):
        taxonomy = EngineeringTaxonomy.CONTROL_VALVE
        sec_func = EngineeringTaxonomy.CONTROL_FUNCTION
        is_valve = True
        is_inst = False  # NEVER double-instantiate as standalone instrument!

    # C. Manual / In-line Valves
    elif fcode in MANUAL_AND_RELIEF_VALVE_CODES or (graphic_hint and "VALVE" in graphic_hint.upper()):
        if fcode in {'CB', 'CK'}:
            taxonomy = EngineeringTaxonomy.CHECK_VALVE
        elif fcode in {'BL', 'BV'}:
            taxonomy = EngineeringTaxonomy.BALL_VALVE
        elif fcode in {'GT', 'GB'}:
            taxonomy = EngineeringTaxonomy.GATE_VALVE
        elif fcode in {'GL'}:
            taxonomy = EngineeringTaxonomy.GLOBE_VALVE
        elif fcode in {'BF', 'BFV'}:
            taxonomy = EngineeringTaxonomy.BUTTERFLY_VALVE
        elif fcode in {'NV', 'ND'}:
            taxonomy = EngineeringTaxonomy.NEEDLE_VALVE
        elif fcode in {'PL', 'PLV'}:
            taxonomy = EngineeringTaxonomy.PLUG_VALVE
        else:
            taxonomy = EngineeringTaxonomy.VALVE
        is_valve = True

    # D. Instruments (PIT, TIT, LIT, FIT, PDT, PDI, etc.)
    elif fcode in INSTRUMENT_PREFIX_MAP:
        primary_tax, func_tax = INSTRUMENT_PREFIX_MAP[fcode]
        taxonomy = primary_tax
        sec_func = func_tax
        is_inst = True

    # E. Major Equipment
    elif fcode in EQUIPMENT_CODE_MAP:
        taxonomy = EQUIPMENT_CODE_MAP[fcode]
        is_equip = True
        if sub_comp and 'M' in sub_comp:
            taxonomy = EngineeringTaxonomy.MOTOR

    # F. Fallback based on Graphic Symbol Hint
    elif graphic_hint:
        gh_up = graphic_hint.upper()
        if "VALVE" in gh_up:
            taxonomy = EngineeringTaxonomy.VALVE
            is_valve = True
        elif "COMPRESSOR" in gh_up:
            taxonomy = EngineeringTaxonomy.COMPRESSOR
            is_equip = True
        elif "PUMP" in gh_up:
            taxonomy = EngineeringTaxonomy.PUMP
            is_equip = True
        elif "VESSEL" in gh_up:
            taxonomy = EngineeringTaxonomy.VESSEL
            is_equip = True
        elif "EXCHANGER" in gh_up:
            taxonomy = EngineeringTaxonomy.HEAT_EXCHANGER
            is_equip = True

    return DecomposedTag(
        raw_tag=raw_tag,
        normalized_tag=cleaned,
        canonical_base_tag=canon_base,
        area_prefix=area_prefix,
        function_code=fcode,
        sequence_number=seq_num,
        suffix=sib_suffix,
        alarms=alarms,
        sub_component=sub_comp,
        detected_taxonomy=taxonomy,
        secondary_function=sec_func,
        role=role,
        is_valve=is_valve,
        is_instrument=is_inst,
        is_equipment=is_equip,
        is_line=False,
    )
