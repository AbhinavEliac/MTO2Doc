"""
Entity Validation & Tag Grammar Layer for SID-AI.

Implements:
1. EntityCandidate dataclass with comprehensive status tracking:
   - CANDIDATE, VALIDATED, DUPLICATE, REJECTED, NEEDS_REVIEW
2. Multi-factor confidence tracking (OCR, grammar, symbol, spatial, semantic).
3. Generalized engineering tag grammars (Lines, Valves, Instruments, Equipment, PSVs).
4. Rejection logging to keep rejected candidates for debugging & auditability.
"""
from __future__ import annotations

import re
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class EntityStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class EntityType(str, Enum):
    EQUIPMENT = "EQUIPMENT"
    LINE = "LINE"
    VALVE = "VALVE"
    INSTRUMENT = "INSTRUMENT"
    PSV = "PSV"
    ANNOTATION = "ANNOTATION"


class InstrumentRole(str, Enum):
    ON_PAGE_INSTRUMENT = "ON_PAGE_INSTRUMENT"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
    CONTROL_VALVE = "CONTROL_VALVE"
    LINE_IDENTIFIER = "LINE_IDENTIFIER"
    EQUIPMENT_ATTRIBUTE = "EQUIPMENT_ATTRIBUTE"
    ANNOTATION = "ANNOTATION"


@dataclass
class EntityCandidate:
    id: str
    raw_text: str
    normalized_tag: str
    entity_type: EntityType
    subtype: Optional[str] = None
    bbox: Optional[List[float]] = None
    page: int = 1
    source: str = "ocr"
    ocr_confidence: float = 0.90
    grammar_confidence: float = 0.0
    symbol_confidence: float = 0.0
    spatial_confidence: float = 0.0
    semantic_confidence: float = 0.0
    final_confidence: float = 0.0
    status: EntityStatus = EntityStatus.CANDIDATE
    rejection_reason: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status in (EntityStatus.VALIDATED, EntityStatus.CANDIDATE) and self.status != EntityStatus.REJECTED


# ─────────────────────────────────────────────────────────────────────────────
# Recognized Engineering Grammar Sets & Patterns
# ─────────────────────────────────────────────────────────────────────────────

# Piping Service Fluid Codes
PIPING_SERVICE_CODES = {
    'PV', 'DC', 'WC', 'AI', 'GI', 'VF', 'PL', 'DO', 'DR', 'IA', 'PA', 'NG', 'FG',
    'VA', 'FO', 'LO', 'CW', 'RW', 'FW', 'SW', 'WW', 'BD', 'FL', 'SL', 'CL', 'OG',
}

# Known Piping Specification Codes
PIPING_SPEC_PATTERN = re.compile(
    r'\b(?:FC11[S|J]?|GC11[S|J]?|AC21[S|J]?|AS20[S|J]?|BC11[S|J]?|BS20[S|J]?|'
    r'CC11[S|J]?|CS20[S|J]?|DC11[S|J]?|DS20[S|J]?|EC11[S|J]?|ES20[S|J]?|'
    r'FD70[X]?|FS20[S|J]?|AC11[S|J]?|AS10[S|J]?|GS20[S|J]?|FD[0-9]{2}[A-Z]?)\b',
    re.IGNORECASE
)

# Known Valve Function Prefix Codes
VALVE_FUNCTION_CODES = {
    'GT', 'BL', 'CB', 'GB', 'GL', 'BV', 'NV', 'BF', 'CK', 'ND', 'PL',
    'HV', 'XV', 'CV', 'PCV', 'FCV', 'TCV', 'LCV', 'MOV', 'SDV', 'BDV',
    'FV', 'ZV', 'EV', 'UV', 'TV', 'LV', 'AV', 'RV', 'SV', 'DV', 'WV',
}

# ISA-5.1 Instrument Function Letter Codes
INSTRUMENT_FUNCTION_CODES = {
    'PIT', 'PI', 'PDIT', 'PDI', 'PDT', 'PT', 'TIT', 'TI', 'TT', 'TDT',
    'FIT', 'FI', 'FT', 'FE', 'FCV', 'FO', 'LIT', 'LI', 'LT', 'LG', 'LCV',
    'AIT', 'AI', 'AT', 'VIT', 'VI', 'VT', 'ZIT', 'ZI', 'ZT', 'ZT',
    'PY', 'TY', 'FY', 'LY', 'AY', 'PSV', 'PRV', 'TIC', 'PIC', 'FIC', 'LIC',
}

# Equipment Type Codes
EQUIPMENT_TYPE_CODES = {
    'KA', 'KB', 'KC', 'KT', 'CP', 'CM', 'KZ',
    'HA', 'HB', 'HC', 'EA', 'EB', 'EC', 'HX', 'HE',
    'VA', 'VB', 'VC', 'TK', 'DA', 'DB', 'KO', 'CA', 'CB',
    'PA', 'PB', 'PC', 'GA', 'GB', 'PM', 'PU',
    'FA', 'FB', 'FC', 'SA', 'SB', 'SC', 'CX', 'FL', 'ST',
    'SK', 'PK', 'PKG', 'MA', 'MB', 'ME',
}

# Rejection keywords for equipment (tables, headers, descriptions)
EQUIPMENT_REJECT_KEYWORDS = {
    'STAGE', 'GAS', 'OIL', 'AIR', 'WATER', 'COOLING', 'SUPPLY', 'TAG', 'SERVICE',
    'DUTY', 'FLOW', 'DISCHARGE', 'SUCTION', 'MATERIAL', 'QUANTITY', 'VENDOR',
    'PRESSURE', 'TEMPERATURE', 'DRAWING', 'MODULE', 'OMSMODUL', 'NOTE',
}


# ─────────────────────────────────────────────────────────────────────────────
# Normalization Functions
# ─────────────────────────────────────────────────────────────────────────────

def normalize_psv_tag(raw: str) -> str:
    """Normalize PSV tag by stripping leading hyphens or extra punctuation."""
    t = raw.strip().upper()
    t = re.sub(r'^[–—_\-\s]+', '', t)
    # Ensure format like 26-PSV-9027A or PSV-9027A
    m = re.search(r'(\d{2,3}-)?PSV-\d{3,5}[A-Z]?', t)
    return m.group(0) if m else t


def normalize_valve_tag(raw: str) -> str:
    """Normalize valve tag (e.g. 26CB9131 or 26-CB-9131 -> 26CB9131)."""
    t = raw.strip().upper()
    t = re.sub(r'^[–—_\-\s]+|[–—_\-\s]+$', '', t)
    # Check if dense format 26CB9131
    m_dense = re.match(r'^(\d{2})([A-Z]{2})(\d{4,6}[A-Z]?)$', t)
    if m_dense:
        return f"{m_dense.group(1)}{m_dense.group(2)}{m_dense.group(3)}"
    # Check separated 26-CB-9131 -> 26CB9131
    m_sep = re.match(r'^(\d{2})[-–]([A-Z]{2})[-–](\d{4,6}[A-Z]?)$', t)
    if m_sep:
        return f"{m_sep.group(1)}{m_sep.group(2)}{m_sep.group(3)}"
    return t


def normalize_instrument_tag(raw: str) -> str:
    """
    Clean instrument tag from glued alarms, repeated tokens, or note references.
    Examples:
      'TIT-9018-TIT' -> 'TIT-9018'
      'FE-9017-NOTE' -> 'FE-9017'
      'PDIT-9015-PDI' -> 'PDIT-9015'
      'PDIT-9015-HH' -> 'PDIT-9015'
      'PI-9016-PIT' -> 'PIT-9016' (prefers transmitter/controller over indicator)
      'PI-9026-L' -> 'PI-9026'
      'PIT-9026-26' -> '26-PIT-9026'
    """
    t = raw.strip().upper()
    t = re.sub(r'^[–—_\-\s]+|[–—_\-\s]+$', '', t)

    # Remove trailing NOTE callouts
    t = re.sub(r'[-–]NOTE.*$', '', t)

    # Check for area prefix: e.g. 26-PIT-9026
    area_prefix = ""
    m_area = re.match(r'^(\d{2,3})[-–](.+)$', t)
    if m_area:
        area_prefix = f"{m_area.group(1)}-"
        t = m_area.group(2)

    # If trailing area number was appended (e.g. PIT-9026-26)
    m_trail_area = re.match(r'^([A-Z]{2,5})[-–](\d{3,5})[-–](\d{2,3})$', t)
    if m_trail_area:
        area_prefix = f"{m_trail_area.group(3)}-"
        t = f"{m_trail_area.group(1)}-{m_trail_area.group(2)}"

    # If alarm suffix attached (e.g. PDIT-9015-HH, PI-9019-LL, PI-9026-L)
    t = re.sub(r'[-–](?:HH|LL|H|L|SD|TRIP|ALARM)$', '', t)

    # If repeated type token attached (e.g. TIT-9018-TIT, PDIT-9015-PDI, PI-9016-PIT)
    m_rep = re.match(r'^([A-Z]{2,5})[-–](\d{3,5})[-–]([A-Z]{2,5})$', t)
    if m_rep:
        t1, seq, t2 = m_rep.group(1), m_rep.group(2), m_rep.group(3)
        # Choose the more specific type (e.g. PIT over PI, PDIT over PDI, TIT over TI)
        chosen_type = t2 if len(t2) > len(t1) else t1
        t = f"{chosen_type}-{seq}"

    return f"{area_prefix}{t}"


# ─────────────────────────────────────────────────────────────────────────────
# Candidate Validation Functions
# ─────────────────────────────────────────────────────────────────────────────

def validate_equipment_candidate(raw: str) -> EntityCandidate:
    """
    Validates whether a raw string represents a genuine equipment entity.
    Strictly prevents:
    1. Line tags (e.g. VA-26-9110-AS20S-00)
    2. Table headers / column names (e.g. KA-902-STAGE)
    3. Concatenated strings with notes or embedded instruments
    """
    t = raw.strip().upper()
    cand = EntityCandidate(
        id=f"eq_{t}",
        raw_text=raw,
        normalized_tag=t,
        entity_type=EntityType.EQUIPMENT,
    )

    # 1. Reject if contains pipe specification codes (AS20S, AC21, FC11S, GS20, etc.)
    if PIPING_SPEC_PATTERN.search(t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Contains piping specification code (line tag, not equipment)"
        return cand

    # 2. Reject if starts with pipe size (e.g. 2", 3/4", 12mm)
    if re.match(r'^(?:\d+(?:/\d+)?["\']|mm|DN)', t, re.IGNORECASE):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Has pipe size prefix (piping line)"
        return cand

    # 3. Reject if matches line pattern: SERVICE-UNIT-SEQ-SPEC
    # (e.g. VA-26-9110-AS20S-00)
    parts = t.split('-')
    if len(parts) >= 4 and parts[0] in PIPING_SERVICE_CODES and parts[1].isdigit() and parts[2].isdigit():
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Matches piping line grammar (SERVICE-UNIT-SEQ-SPEC)"
        return cand

    # 4. Reject if contains reject keywords (STAGE, GAS, OIL, DRAWING, etc.)
    for kw in EQUIPMENT_REJECT_KEYWORDS:
        if kw in parts or f"-{kw}" in t or f"{kw}-" in t:
            cand.status = EntityStatus.REJECTED
            cand.rejection_reason = f"Contains non-equipment text keyword: {kw}"
            return cand

    # 5. Reject concatenated strings with embedded instrument tags
    for inst_code in ('PIT', 'TIT', 'PDIT', 'FIT', 'LIT'):
        if f"-{inst_code}-" in t:
            cand.status = EntityStatus.REJECTED
            cand.rejection_reason = f"Concatenated text with embedded instrument tag ({inst_code})"
            return cand

    # 6. Reject drawing reference prefixes like STAGE-26-000001
    if re.search(r'\b(?:STAGE|DWG|DRAWING|PAGE|REF)\b', t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Drawing or document reference"
        return cand

    # Reject bare service code + 2-digit unit (e.g. VA-26, PV-26)
    if re.match(r'^[A-Z]{1,4}-\d{1,2}$', t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Matches bare piping service code + unit (e.g. VA-26, PV-26)"
        return cand

    # 7. Check strict equipment grammar
    # Standard: [UNIT-]CODE-NUMBER[SUFFIX][-M01/C01]
    # Examples: 26-KA-902, 26-CX-9021, 26-KZ-902, 26-KA-902-M01, KA-902, TK-101
    # Reject bare digit suffixes like -2, -3 (which are OCR collisions with line sizes)
    eq_match = re.match(r'^(?:(\d{2,3})-)?([A-Z]{1,3})-(\d{2,5}[A-Z]?)(?:-([A-Z]\d{1,3}|[A-Z]{1,2}))?$', t)
    if not eq_match:
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Fails standard equipment tag grammar"
        return cand

    code = eq_match.group(2)
    # Check equipment code allowlist
    if code not in EQUIPMENT_TYPE_CODES:
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = f"Unknown equipment code '{code}'"
        return cand

    # Passed all checks
    cand.status = EntityStatus.VALIDATED
    cand.grammar_confidence = 0.95
    cand.final_confidence = 0.95
    return cand


def validate_line_candidate(raw: str) -> EntityCandidate:
    """
    Validates whether a raw string represents a genuine piping line entity.
    Strictly rejects:
    1. Compressor datasheet duty/flow blocks (RD-1835-62809-199-77)
    2. Instrument alarm strings (PDIT-9015-HH-H, PI-9019-LL-3)
    3. Note / module fragments (FE-9017-31-FC11S, CK-921-OMSMODUL, S-9003-MECHANIC)
    4. Spec / electrical codes (DSS-2500-DSS-EL)
    """
    t = raw.strip().upper()
    cand = EntityCandidate(
        id=f"ln_{t}",
        raw_text=raw,
        normalized_tag=t,
        entity_type=EntityType.LINE,
    )

    # 1. Reject duty/flow/table columns (RD-1835-...)
    if t.startswith('RD-') or re.search(r'\bRD-\d+', t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Rated Duty table column (datasheet text)"
        return cand

    # 2. Reject strings containing alarm suffixes (-HH, -LL, -HH-H, -LL-3)
    if re.search(r'[-–](?:HH|LL)(?:[-–][A-Z0-9]+)?$', t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Instrument alarm setpoint string"
        return cand

    # 3. Reject strings containing known non-line words
    for bad_w in ('OMSMODUL', 'MECHANIC', 'NOTE', 'DRAWING', 'STAGE'):
        if bad_w in t:
            cand.status = EntityStatus.REJECTED
            cand.rejection_reason = f"Contains note/table keyword: {bad_w}"
            return cand

    # 4. Reject concatenated instrument tags (e.g. TI-90239025)
    if re.search(r'^(?:TI|PI|PIT|TIT|PDIT)\d{6,}', t) or re.search(r'^(?:TI|PI|PIT|TIT|PDIT)-\d{6,}', t):
        cand.status = EntityStatus.REJECTED
        cand.rejection_reason = "Concatenated instrument loop numbers"
        return cand

    # 5. Check Line Grammar:
    # A genuine line should either:
    # Case A: Have a valid pipe size prefix (e.g. 4"-PV-26-9020-FC11S-38, 12MM-PV-26-9116-FD70X-00)
    # Case B: Have a genuine piping service code + unit + sequence + pipe spec (e.g. PV-26-9020-FC11S-38)
    has_size = bool(re.match(r'^(?:\d+(?:/\d+)?["\']|\d+\s*(?:MM|DN)|(?:DN|MM)\s*\d+)', t, re.IGNORECASE))
    
    parts = t.split('-')
    if has_size:
        # Check that the token after size is a valid service code
        if len(parts) >= 3:
            cand.status = EntityStatus.VALIDATED
            cand.grammar_confidence = 0.95
            cand.final_confidence = 0.95
            return cand
    else:
        # No size prefix: must have valid service code AND valid pipe spec
        svc_code = parts[0] if parts else ""
        if svc_code in PIPING_SERVICE_CODES and len(parts) >= 4 and PIPING_SPEC_PATTERN.search(t):
            cand.status = EntityStatus.VALIDATED
            cand.grammar_confidence = 0.90
            cand.final_confidence = 0.90
            return cand

    cand.status = EntityStatus.REJECTED
    cand.rejection_reason = "Fails line grammar: missing valid size prefix or service/spec definition"
    return cand


def validate_valve_candidate(raw: str) -> EntityCandidate:
    """Validates whether a raw string represents a genuine valve entity."""
    t = normalize_valve_tag(raw)
    cand = EntityCandidate(
        id=f"v_{t}",
        raw_text=raw,
        normalized_tag=t,
        entity_type=EntityType.VALVE,
    )

    # Dense format e.g. 26CB9131, 26GT9128, 43BL9054
    m_dense = re.match(r'^(\d{2})([A-Z]{2})(\d{4,6}[A-Z]?)$', t)
    if m_dense:
        code = m_dense.group(2)
        if code in VALVE_FUNCTION_CODES:
            cand.status = EntityStatus.VALIDATED
            cand.grammar_confidence = 0.98
            cand.final_confidence = 0.98
            return cand

    # Hyphenated format e.g. 26-CB-9131, HV-101, BV-101
    m_hyphen = re.match(r'^(?:(\d{2})-)?([A-Z]{2,4})-(\d{2,6}[A-Z]?)$', t)
    if m_hyphen:
        code = m_hyphen.group(2)
        if code in VALVE_FUNCTION_CODES or code.endswith('V'):
            cand.status = EntityStatus.VALIDATED
            cand.grammar_confidence = 0.95
            cand.final_confidence = 0.95
            return cand

    cand.status = EntityStatus.REJECTED
    cand.rejection_reason = "Fails valve tag grammar"
    return cand


def canonicalize_line_tag(raw: str) -> Tuple[str, str, str]:
    """
    Parses a raw line tag into (canonical_tag, core_tag, size_prefix).
    Example:
      '2"-VA-26-9120-AS20S-00' -> ('2"-VA-26-9120-AS20S-00', 'VA-26-9120-AS20S-00', '2"')
      'VA-26-9120-AS20S-00'    -> ('VA-26-9120-AS20S-00', 'VA-26-9120-AS20S-00', '')
    """
    t = raw.strip().upper()
    m_size = re.match(r'^((?:\d+(?:/\d+)?["\']|\d+\s*(?:MM|DN)|(?:DN|MM)\s*\d+))[-–](.*)$', t, re.IGNORECASE)
    if m_size:
        size_prefix = m_size.group(1).upper()
        core_tag = m_size.group(2).strip()
        return f"{size_prefix}-{core_tag}", core_tag, size_prefix
    return t, t, ""


def classify_instrument_role(
    raw_tag: str,
    context: Optional[Dict[str, Any]] = None,
    current_unit: str = "26",
    known_lines: Optional[List[str]] = None,
    all_ocr_texts: Optional[List[str]] = None,
) -> Tuple[InstrumentRole, str]:
    """
    Classifies the engineering role of an instrument candidate into:
    - ON_PAGE_INSTRUMENT
    - EXTERNAL_REFERENCE
    - CONTROL_VALVE
    - LINE_IDENTIFIER
    - EQUIPMENT_ATTRIBUTE
    - ANNOTATION
    """
    tag = raw_tag.strip().upper()
    ctx = context or {}
    known_lines = [l.upper() for l in (known_lines or [])]
    all_texts = [str(x).upper() for x in (all_ocr_texts or [])]

    # 1. Descriptive Note / Specification Annotation
    if any(w in tag for w in ('NOTE', 'LTCS', 'OMS', 'MODUL', 'DRAIN', 'SPEC', 'DWG', 'DETAIL')):
        return InstrumentRole.ANNOTATION, f"Contains annotation/spec keyword in '{tag}'"

    # 2. Control Valve (FV, PV, TV, LV, HV, XV, PCV, FCV, TCV, LCV, SDV, BDV)
    # Control elements installed on process piping lines belong to Valves catalog, not instrument bubbles
    # E.g., 26-FV-9038, FV-9038, 26-HV-101
    m_code = re.search(r'\b(?:(\d{2,3})-)?([A-Z]{2,4})-(\d{2,5}[A-Z]?)\b', tag)
    if m_code:
        fcode = m_code.group(2)
        if fcode in ('FV', 'HV', 'XV', 'CV', 'PCV', 'FCV', 'TCV', 'LCV', 'MOV', 'SDV', 'BDV') or (fcode.endswith('V') and fcode[0] in ('F', 'P', 'T', 'L', 'H', 'X', 'Z', 'B', 'S')):
            return InstrumentRole.CONTROL_VALVE, f"Control valve / final control element code '{fcode}'"

    # 3. Line Identifier (e.g. 26-AI-63-9000, 26-AI-63-9001, AI-63-9000)
    # Line identifiers have:
    # A) Piping service code (e.g. AI = Instrument Air, IA, PA, FG, DO, DC, VF, PV, PL, WC, VA)
    # B) Two numeric sequences separated by hyphens (e.g. system 63 and sequence 9000: 26-AI-63-9000)
    m_line_pattern = re.match(r'^(?:(\d{2,3})-)?([A-Z]{2,3})-(\d{2,3})-(\d{3,5}[A-Z]?)(?:-.*)?$', tag)
    if m_line_pattern:
        svc = m_line_pattern.group(2)
        if svc in PIPING_SERVICE_CODES or svc in ('AI', 'IA', 'PA', 'FG', 'FO', 'DO', 'DC', 'VF', 'PV', 'PL', 'WC', 'VA', 'GI'):
            return InstrumentRole.LINE_IDENTIFIER, f"Matches line identifier structure <service>-<subsystem>-<seq> ('{svc}')"

    # Check if tag is part of a known line (e.g. 'AI-63-9000' in '1"-AI-63-9000-AS20-00')
    clean_tag_core = re.sub(r'^\d{2,3}-', '', tag)
    for kl in known_lines:
        if clean_tag_core in kl or tag in kl:
            return InstrumentRole.LINE_IDENTIFIER, f"Matches substring of documented piping line '{kl}'"

    # 4. Equipment Attribute / Vessel Trim / Cable Data (e.g. 26-TT-26-9711, TT-26-9711)
    # Pattern where unit number is duplicated (e.g. 26-TT-26) or matches transmitter cable tag
    if re.search(r'(\d{2,3})-[A-Z]{2,4}-\1-\d+', tag) or re.match(r'^[A-Z]{2,4}-\d{2}-\d{4,}$', tag):
        return InstrumentRole.EQUIPMENT_ATTRIBUTE, "Vessel trim / internal equipment sensor or transmitter cable"
    if ctx.get("source_region") in ("equipment_table", "equipment_trim") or ctx.get("is_vessel_trim"):
        return InstrumentRole.EQUIPMENT_ATTRIBUTE, "Documented as vessel trim or equipment table data"

    # 5. External Reference (e.g. 27-PIT-0001B, FROM 26-PIT-9087)
    # A) Text context contains reference indicators
    raw_ctx_text = str(ctx.get("text", "")).upper()
    if ctx.get("is_reference") or bool(re.search(r'\b(?:FROM|TO|TIE-IN|CONTINUED\s+ON|SEE\s+DWG|REF\s+DWG|DWG\s+NO)\b', raw_ctx_text)):
        return InstrumentRole.EXTERNAL_REFERENCE, "Context indicates external tie-in or drawing continuation"

    # Check if any OCR text containing this tag starts with FROM or TO (e.g. 'FROM 26-PIT-9087')
    for txt in all_texts:
        if tag in txt and bool(re.search(r'\b(?:FROM|TO|TIE-IN|CONTINUED)\b', txt)):
            return InstrumentRole.EXTERNAL_REFERENCE, f"Contained in off-page reference phrase '{txt}'"

    # B) Unit prefix differs from drawing primary unit (e.g. 27-PIT-0001B on Unit 26 sheet)
    m_unit = re.match(r'^(\d{2,3})-', tag)
    if m_unit:
        tag_unit = m_unit.group(1)
        if current_unit and tag_unit != current_unit:
            return InstrumentRole.EXTERNAL_REFERENCE, f"Unit prefix '{tag_unit}' differs from drawing sheet unit '{current_unit}' (off-sheet tie-in)"

    # C) Specific header/off-page reference context
    if ctx.get("is_header_ref") or "HEADER" in raw_ctx_text:
        return InstrumentRole.EXTERNAL_REFERENCE, "Header / off-page connector reference"

    # 6. Valid On-Page Instrument Loop
    m_inst = re.match(r'^(?:(\d{2,3})-)?([A-Z]{2,4})-(\d{3,5}[A-Z]?)$', tag)
    if m_inst:
        code = m_inst.group(2)
        if code in INSTRUMENT_FUNCTION_CODES or code.startswith(('P', 'T', 'F', 'L', 'A', 'V', 'Z')):
            return InstrumentRole.ON_PAGE_INSTRUMENT, "Valid on-page ISA-5.1 instrument loop"

    return InstrumentRole.ON_PAGE_INSTRUMENT, "On-page instrument candidate"
