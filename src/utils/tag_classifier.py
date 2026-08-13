"""
Universal P&ID / Engineering Drawing Tag Classifier — Multi-Discipline, High-Yield Extraction.

Strategy: SCAN each OCR string for embedded tag patterns using re.search() / re.finditer()
          rather than matching full strings. Retains ALL text elements & notes to guarantee
          100% extraction completeness across all drawing types.

Drawing-type-aware pattern sets (ISA 5.1 / IEC / CFIHOS / IEEE):
  P&ID / Process:
    EQUIPMENT_TAG : 26-KA-901, TK-101, P-101, E-201, V-301
    LINE_TAG      : 8"-PV-26-9035-FC11S-08, 1/2"-PV-26-9035, 2"-WF-43-9032-GS225-CC
    INSTRUMENT_TAG: 26-PDI-9054, PIT-9062, 26-PIT-9077, TIT-9057, PDIT-9054, TE-101, FE-901
    VALVE_TAG     : 26CB9131, 26GB9178, 26-CB-9131, HV-101, XV-201, V-101, MOV-101
    PSV_TAG       : 26-PSV-9066A, PSV-101A

  Electrical Layout:
    LUMINAIRE_TAG : L-01, LS-201, TL-101, FL-01
    PANEL_TAG     : DB-01, MDB-A, LDB-3, LPDB, MVDB, Switchboard
    CIRCUIT_TAG   : C-101, CB-01, MCB-1, MCCB-3, ACB-01

  Earthing Layout:
    EARTH_BAR_TAG     : EB-01, EBM-01, MEB
    EARTH_PIT_TAG     : EP-01, EP-A, Earth Pit
    BOND_CONDUCTOR_TAG: BC-01, EC-01, Copper Tape

  Structural / Generic:
    GRID_REF  : A-1, B5, C-10
    ELEVATION : EL +100.000, RL 101.445
    NOTE      : Plain text descriptions, callouts, specs, notes
"""
from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Comprehensive ISA 5.1 instrument function letter codes (P&ID)
# ──────────────────────────────────────────────────────────────────────────────
_INSTRUMENT_CODES = {
    # Pressure & Differential Pressure
    'PIT', 'PDT', 'PDIT', 'PDIC', 'PDIS', 'PDS', 'PDR', 'PDC', 'PDI', 'PT', 'PI',
    'PIC', 'PCV', 'PSV', 'PSH', 'PSL', 'PRV', 'PV', 'PAH', 'PAL', 'PE', 'PC',
    'PS', 'PR', 'PY', 'PVI', 'PVR',
    # Temperature
    'TIT', 'TDT', 'TDIT', 'TDIC', 'TT', 'TI', 'TIC', 'TCV', 'TSH', 'TSL', 'TE',
    'TAH', 'TAL', 'TC', 'TS', 'TR', 'TY', 'TW', 'TDI', 'TDR',
    # Flow
    'FIT', 'FDT', 'FDIT', 'FT', 'FI', 'FIC', 'FCV', 'FE', 'FRC', 'FO', 'FSL',
    'FSH', 'FAL', 'FC', 'FS', 'FR', 'FY', 'FDI', 'FDR', 'FG',
    # Level
    'LIT', 'LDT', 'LDIT', 'LT', 'LI', 'LIC', 'LCV', 'LSH', 'LSL', 'LE', 'LAH',
    'LAL', 'LC', 'LS', 'LR', 'LY', 'LG', 'LDI', 'LDR', 'LV',
    # Analysis & Quality
    'AIT', 'ADT', 'ADIT', 'AT', 'AI', 'AIC', 'ACV', 'AAH', 'AAL', 'AC', 'AS',
    'AR', 'AY', 'AE', 'AV',
    # Vibration & Mechanical
    'VIT', 'VT', 'VI', 'VIC', 'VAH', 'VAL', 'VE', 'VS', 'VR', 'VY', 'VSD', 'VD',
    # Position & Dimension
    'ZIT', 'ZT', 'ZI', 'ZIC', 'ZCV', 'ZE', 'ZS', 'ZR', 'ZY', 'ZV',
    # Weight / Force / Power / Speed / Hand / Unclassified
    'WIT', 'WT', 'WI', 'WIC', 'WE', 'WS', 'WR', 'WY',
    'EIT', 'ET', 'EI', 'EIC', 'EE', 'ES', 'ER', 'EY',
    'JIT', 'JT', 'JI', 'JIC', 'JE', 'JS', 'JR', 'JY',
    'SIT', 'ST', 'SI', 'SIC', 'SE', 'SS', 'SR', 'SY', 'SH', 'SL',
    'HIT', 'HT', 'HI', 'HIC', 'HV', 'HS', 'HC', 'HY',
    'XIT', 'XT', 'XI', 'XE', 'XV', 'XS', 'XR', 'XY', 'XC',
    'GIT', 'GT', 'GI', 'GIC', 'GE', 'GS', 'GR', 'GY', 'GC',
    'MCC', 'UCP', 'OMS', 'ESD', 'PLC', 'DCS', 'SIS', 'FGS', 'SCADA', 'BMS',
}

_EQUIPMENT_CODES = {
    # Compressors / Blowers / Turbines
    'KA', 'KB', 'KC', 'KT', 'CP', 'CM',
    # Heat exchangers / Coolers / Heaters
    'HA', 'HB', 'HC', 'EA', 'EB', 'EC', 'HX', 'HE',
    # Vessels / Tanks / Columns / Drums
    'VA', 'VB', 'VC', 'TA', 'TB', 'TK', 'DA', 'DB', 'CA', 'CB',
    # Pumps
    'PA', 'PB', 'PC', 'GA', 'GB', 'PM', 'PU',
    # Filters / Separators / Strainers
    'FA', 'FB', 'FC', 'SA', 'SB', 'SC', 'CX', 'FL', 'SE', 'ST',
    # Skids / Packages / Mechanical Units
    'KZ', 'ME', 'MA', 'MB', 'NA', 'NB', 'SK', 'PK', 'PKG',
    # Miscellaneous
    'EC', 'GH', 'GJ', 'KD', 'KE', 'LA', 'LB',
}

# Equipment prefix allowlist — only known equipment codes to eliminate false positives
# (line specs like FC11S, GC11S, drawing refs like AB-1234 are excluded)
_EQUIP_PREFIX_ALLOWLIST = {
    # Compressors, blowers, turbines, motors
    'K', 'KA', 'KB', 'KC', 'KT', 'CM', 'CP', 'MT', 'MG',
    # Heat exchangers, coolers, heaters, furnaces
    'E', 'EA', 'EB', 'HX', 'HE', 'BA',
    # Vessels, drums, tanks, columns
    'V', 'VA', 'VB', 'TK', 'T', 'D', 'DA', 'C', 'R', 'DR',
    # Pumps
    'P', 'PA', 'PB', 'PC', 'G', 'GA', 'PM', 'PU',
    # Filters, separators, strainers
    'F', 'FA', 'FB', 'ST', 'CX',
    # Skids, packages
    'SK', 'PK',
    # General mechanical
    'M', 'MA', 'MB', 'U', 'UA', 'W', 'WA',
}

# Generic 1-3 letter + number equipment — guarded with prefix allowlist
_GENERIC_EQUIP_PATTERN = re.compile(
    r'\b([A-Z]{1,3}-\d{2,5}[A-Z]?(?:/[A-Z])?)\b', re.IGNORECASE
)

# Patterns that must NOT be classified as equipment (spec codes, sheet refs, etc.)
_EQUIP_REJECT_PATTERN = re.compile(
    r'^(?:FC|GC|AC|AS|VC|SC|DC|WF|PV|VF|VA|HC|RC)[0-9]',  # spec codes
    re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# P&ID Search Patterns
# ──────────────────────────────────────────────────────────────────────────────

# PSV — Pressure Safety Valves
_PSV_SEARCH = re.compile(
    r'\b(\d{0,4}-?PSV-\d{3,5}[A-Z]?)\b', re.IGNORECASE
)

# Equipment tags: 26-KA-901, 26-HA-911-C01
# Instrument tags with project prefix: 26-PIT-9077, 26-PDI-9054, 26-TIT-9057
_PROJECT_TAG_SEARCH = re.compile(
    r'\b(\d{2}-([A-Z]{2,4})-([\dA-Z]{3,6})(?:-[A-Z]{1,4}\d{1,4})?)\b',
    re.IGNORECASE
)

# Bare instrument tags without project prefix: PIT-9062, TIT-9057, PDIT-9054, PDI-9054
# RULES:
#   1. Require mandatory hyphen separator (prevents GC11S, AS20S, FC11S spec code matches)
#   2. Require 3+ digit loop numbers (prevents PV-26, VA-26 service-code matches)
#   3. Only use unambiguous ISA codes (exclude 2-letter codes that match spec prefixes)
_ISA_CODES_JOINED = '|'.join(sorted(_INSTRUMENT_CODES, key=len, reverse=True))
# Unambiguous codes only — 3+ letter codes first, then safe 2-letter instrument codes
# Excludes: AC, AS, GC, FC, SC, VC, DC, WF, RC — these match spec code prefixes
_ISA_SAFE_CODES = [
    c for c in sorted(_INSTRUMENT_CODES, key=len, reverse=True)
    if len(c) >= 3 or c.upper() not in {
        'AC', 'AS', 'GC', 'FC', 'SC', 'VC', 'DC', 'RC',
        'WF', 'PV', 'TV', 'LV', 'AV', 'FV', 'ZV',  # valve-action codes (classified as valves)
    }
]
_ISA_SAFE_CODES_JOINED = '|'.join(_ISA_SAFE_CODES)
_BARE_INSTRUMENT_SEARCH = re.compile(
    rf'\b((?:{_ISA_SAFE_CODES_JOINED})-\d{{3,5}}[A-Z]?)\b',  # hyphen required, 3+ digits
    re.IGNORECASE
)

# Pipe spec code pattern — must NEVER be classified as instruments or equipment
# Matches: GC11S, AS20S, FC11S, AC21S, GC115, AC21 etc.
_SPEC_CODE_PATTERN = re.compile(
    r'^(?:GC|AC|AS|FC|VC|SC|DC|WF|RC|CC|SG|CS|AG)[\dA-Z]{2,6}$',
    re.IGNORECASE
)
# Also reject bare service codes (2-4 letters + 2-digit number): PV-26, VA-26
_SERVICE_CODE_PATTERN = re.compile(
    r'^[A-Z]{1,4}-\d{2}$',
    re.IGNORECASE
)

# Valve tags (ISA 5.1 comprehensive):
#   Dense format:    26CB9131, 26GB9178  (no separator)
#   Separated:       26-CB-9131A, 26-GB-9178
#   Named control valves: HV-101, XV-201, FV-9076, PCV-9044, SDV-201
#   Block valves: BV-101, NV-201, GV-101, BFV-201
_VALVE_SEARCH = re.compile(
    r'\b('
    r'\d{2}-?[A-Z]{2}-?\d{4,6}[A-Z]?'                           # 26CB9131, 26-CB-9131A
    r'|(?:HV|XV|CV|PCV|FCV|TCV|LCV|EV|MOV|SDV|BDV|FV|UV|TV|LV|AV|ZV)[-–]\d{2,5}[A-Z]?'  # HV-101, SDV-201
    r'|(?:BV|NV|GV|BFV|SBV|NGV|PLV|RV|PRV)[-–]\d{2,5}[A-Z]?'  # BV-101, NV-201
    r'|\bV-\d{3,5}[A-Z]?'                                         # V-101
    r')\b',
    re.IGNORECASE
)

# Line tags: 8"-PV-26-9035-FC11S-08, 12mm-PV-26-9116-FD70X-00, 3"-VA-26-9121-AC21-00, PV-26-9035-FC11S-08
_LINE_SEARCH = re.compile(
    r'((?:\d+(?:[/\.]\d+)?(?:["\']|mm|DN)?\s*[-–]?\s*)?[A-Z]{1,4}\s*[-–]\s*(?:\d{2,4}\s*[-–]\s*)?\d{3,5}'
    r'\s*[-–]\s*[A-Z0-9]{2,8}(?:\s*[-–]\s*[A-Z0-9]{1,8})?)',
    re.IGNORECASE
)

# Pressure/class ratings: 150#, 2500#, 257 barg, 100 psig
_RATING_SEARCH = re.compile(
    r'\b(\d{2,4}(?:#|#\s|barg|psig|kpag|bar|mpa|kpa))\b', re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# Electrical Layout Patterns
# ──────────────────────────────────────────────────────────────────────────────

# Luminaire / Lighting Fitting tags: L-01, LS-201, TL-101, FL-01, FLOODLIGHT, WELLGLASS, HIGHBAY
_LUMINAIRE_SEARCH = re.compile(
    r'\b('
    r'(?:TL|FL|EL|SL|LS|WL|LT|LP|LGT|FIX|LED|EML|WGL)[-–]?\d{1,4}[A-Z]?'
    r'|L-\d{1,4}[A-Z]?'
    r'|FLOODLIGHT(?:-?\d{1,4}[A-Z]?)?'
    r'|WELLGLASS(?:-?\d{1,4}[A-Z]?)?'
    r'|LUMINAIRE(?:-?\d{1,4}[A-Z]?)?'
    r'|LIGHT\s+FIXTURE(?:-?\d{1,4}[A-Z]?)?'
    r'|LIGHTING\s+FITTING(?:-?\d{1,4}[A-Z]?)?'
    r'|HIGH\s*BAY(?:-?\d{1,4}[A-Z]?)?'
    r'|LOW\s*BAY(?:-?\d{1,4}[A-Z]?)?'
    r'|EMERGENCY\s+LIGHT(?:-?\d{1,4}[A-Z]?)?'
    r')\b',
    re.IGNORECASE
)

# Elevation / level labels: EL.101.445, EL 100.000, TL 101.445
_ELEVATION_SEARCH = re.compile(
    r'\b((?:EL|TL|RL|BL|GL|FFL|SFL)\s*[.:]?\s*[+\-]?\d{2,5}(?:\.\d{1,3})?)\b',
    re.IGNORECASE
)

# Panel / distribution board tags: DB-01, MDB-A, LDB-3, LPDB-01, EPDB, MVDB, LIGHTING PANEL, SWITCHBOARD
_PANEL_SEARCH = re.compile(
    r'\b('
    r'(?:EMDB|MVDB|LVDB|LPDB|EPDB|MDB|LDB|SDB|DB|PDB|NDB|MSB|LSB|ESB|SMDB|MLP|ELP|SLP|LP|MCC|PCC|PDP|PDPB)'
    r'\s*[-–/]?\s*[A-Z0-9]{1,6}'
    r'|LIGHTING\s+PANEL(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|DISTRIBUTION\s+BOARD(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|EARTHING\s+PANEL(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|SWITCHBOARD(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|SWITCHGEAR(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r')\b',
    re.IGNORECASE
)

# Circuit / breaker tags: C-101, CB-01, MCB-1, MCCB-3, ACB-01, CK-01
_CIRCUIT_SEARCH = re.compile(
    r'\b((?:MCB|RCCB|MCCB|ACB|VCB|CB|CK|CIRCUIT|C)-\d{1,4}[A-Z]?)\b', re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# Earthing Layout Patterns (Comprehensive IEEE 80 / IS 3043 / IEC 62305)
# ──────────────────────────────────────────────────────────────────────────────

# Earth Bar / Busbar: EBM-01, EB-01, MEB-1, EEB-01, SEB-01, MAIN EARTH BAR, EARTH BUSBAR
_EARTH_BAR_SEARCH = re.compile(
    r'\b('
    r'(?:EBM|MEB|EEB|SEB|PEB|EGB|MGB|GBB|EB|EBB)[-–]?\d{1,4}[A-Z]?'
    r'|MAIN\s+EARTH\s+BAR(?:\s*[-–]?\s*\d{1,4}[A-Z]?)?'
    r'|EARTH\s+(?:BAR|BUSBAR|BUS|STRIP\s+BAR)(?:\s*[-–]?\s*[A-Z0-9]{1,4})?'
    r'|GROUND\s+(?:BAR|BUSBAR|BUS)(?:\s*[-–]?\s*[A-Z0-9]{1,4})?'
    r'|EARTHING\s+(?:BAR|BUSBAR|BUS)(?:\s*[-–]?\s*[A-Z0-9]{1,4})?'
    r')\b',
    re.IGNORECASE
)

# Earth Pit / Electrode: EP-01, EP-A, EE-01, EARTH PIT, EARTH CHAMBER, EARTH ELECTRODE, TEST PIT
_EARTH_PIT_SEARCH = re.compile(
    r'\b('
    r'(?:EP|EE|ER|GP|ELP)[-–]?\d{1,4}[A-Z]?'
    r'|EARTH\s+(?:PIT|CHAMBER|ELECTRODE|WELL|ROD)(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|GROUND(?:ING)?\s+(?:PIT|CHAMBER|ELECTRODE|WELL)(?:\s*[-–/]?\s*[A-Z0-9]{1,4})?'
    r'|EARTH\s+TEST\s+PIT'
    r'|TEST\s+(?:PIT|LINK|CHAMBER)'
    r'|DISCONNECTING\s+LINK'
    r')\b',
    re.IGNORECASE
)

# Bond Conductor / Earthing Strip: BC-01, EC-01, GC-01, COPPER TAPE, GS FLAT, GI FLAT, 25X3 MM, 50X6 MM, 70 SQMM
_BOND_CONDUCTOR_SEARCH = re.compile(
    r'\b('
    r'(?:BC|EC|EBC|GBC|GC-)[-–]?\d{1,4}[A-Z]?'
    r'|COPPER\s+(?:TAPE|STRIP|CONDUCTOR|WIRE|CABLE)'
    r'|CU\s+(?:TAPE|STRIP|CONDUCTOR)'
    r'|(?:GS|GI|MS)\s+(?:FLAT|STRIP|TAPE)'
    r'|EARTHING\s+(?:CONDUCTOR|STRIP|TAPE|GRID|MAT|LEAD)'
    r'|GROUNDING\s+(?:CONDUCTOR|STRIP|TAPE|GRID|MAT|LEAD)'
    r'|\d{2,3}\s*[xX]\s*\d{1,2}\s*(?:MM|MM2|SQMM)'
    r'|\d{2,3}\s*(?:SQMM|SQ\.MM|MM2)'
    r')\b',
    re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# Text normalization & bulk classifier
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# OCR character correction table (Fix 1: pre-correct before regex matching)
# ──────────────────────────────────────────────────────────────────────────────
_OCR_CORRECTIONS = [
    # In letter-only runs: 0 → O, 1 → I
    (re.compile(r'(?<=[A-Z])0(?=[A-Z])'), 'O'),
    (re.compile(r'(?<=[A-Z])1(?=[A-Z])'), 'I'),
    # In digit-only runs: O → 0, l → 1, S → 5 (only when surrounded by digits)
    (re.compile(r'(?<=\d)[Ol](?=\d)'), '0'),
    # Pipe size inch mark: 8" → 8", protect known fractions
    (re.compile(r'(\d)\"'), r'\1"'),
    # Spec codes: protect known patterns from over-correction
    (re.compile(r'\bFCllS\b'), 'FC11S'),
    (re.compile(r'\bFCIIS\b'), 'FC11S'),
    (re.compile(r'\bGCllS\b'), 'GC11S'),
    (re.compile(r'\bACZlS\b'), 'AC21S'),
    (re.compile(r'\bAS2OS\b'), 'AS20S'),
    # Instrument code corrections: PlT → PIT, TlT → TIT, FlT → FIT
    (re.compile(r'\bPlT\b'), 'PIT'),
    (re.compile(r'\bTlT\b'), 'TIT'),
    (re.compile(r'\bFlT\b'), 'FIT'),
    (re.compile(r'\bLlT\b'), 'LIT'),
    (re.compile(r'\bAlT\b'), 'AIT'),
    (re.compile(r'\bPDl\b'), 'PDI'),
    (re.compile(r'\bPDlT\b'), 'PDIT'),
]


# ──────────────────────────────────────────────────────────────────────────────
# Defect 3 Fix: Setpoint negative-context guard
# Prevents setpoint numbers (PI-150, AT-225) being classified as instrument tags
# ──────────────────────────────────────────────────────────────────────────────
_SETPOINT_CONTEXT_RE = re.compile(
    r'\b(?:SD|HH|LL|HIGH\s*HIGH|LOW\s*LOW|TRIP|SHUT\s*DOWN|'
    r'SP\s*=|SET\s*PRESS(?:URE)?|SETPOINT|'
    r'MAX(?:IMUM)?|MIN(?:IMUM)?|DESIGN|'
    r'MAWP|MAPD|MOP|MAOP|'
    r'BARG|BAR\(G\)|PSIG|KPAG|MPA(?:G)?|'
    r'\d+\.\d+\s*BAR|\d+\s*°[CF]|\d+\s*DEG(?:REE)?|'
    r'H\s*:|L\s*:|HH\s*:|LL\s*:|ALARM|INTERLOCK)',
    re.IGNORECASE
)

_WINDOW = 35  # characters to scan before/after match for setpoint context


def _is_setpoint_context(full_text: str, match_start: int, match_end: int) -> bool:
    """
    Returns True if a setpoint/note keyword appears within _WINDOW chars
    before or after the instrument tag match position.
    This prevents classifying 'PI-150' in 'SD HH: 150 barg' as a real tag.
    """
    window_text = full_text[max(0, match_start - _WINDOW): match_end + _WINDOW]
    return bool(_SETPOINT_CONTEXT_RE.search(window_text))


def _is_setpoint_context_spatial(item_idx: int, all_items: List[Dict[str, Any]]) -> bool:
    """
    Check whether the item at item_idx or any nearby OCR item (within Y-gap 0.05 and X-gap 0.20)
    contains setpoint/alarm keywords.
    """
    target = all_items[item_idx]
    target_text = (target.get('text') or target.get('value') or '').strip()

    if _SETPOINT_CONTEXT_RE.search(target_text):
        return True

    t_y = float(target.get('center_y') or (target.get('attributes') or {}).get('pos_y') or -1)
    t_x = float(target.get('center_x') or (target.get('attributes') or {}).get('pos_x') or -1)

    if t_y < 0 or t_x < 0:
        return False

    for i, other in enumerate(all_items):
        if i == item_idx:
            continue
        o_text = (other.get('text') or other.get('value') or '').strip()
        if not o_text:
            continue
        o_y = float(other.get('center_y') or (other.get('attributes') or {}).get('pos_y') or -1)
        o_x = float(other.get('center_x') or (other.get('attributes') or {}).get('pos_x') or -1)
        if o_y < 0 or o_x < 0:
            continue

        dy = abs(t_y - o_y)
        dx = abs(t_x - o_x)

        if dy <= 0.05 and dx <= 0.20:
            if _SETPOINT_CONTEXT_RE.search(o_text):
                return True

    return False


# ──────────────────────────────────────────────────────────────────────────────
# Defect 4 Fix: Line tag grammar enforcement helpers
# ──────────────────────────────────────────────────────────────────────────────

# Strip NOTE xx references before line-tag matching
_NOTE_REF_STRIP_RE = re.compile(r'\s*NOTE\s*\d+', re.IGNORECASE)

# Valid nominal pipe sizes (NPS inches and DN metric)
_VALID_INCH_SIZES = {
    '1/2', '3/4', '1', '1-1/4', '1-1/2', '2', '2-1/2', '3', '4',
    '6', '8', '10', '12', '14', '16', '18', '20', '24',
}
_VALID_MM_SIZES = {
    '15mm', '20mm', '25mm', '32mm', '40mm', '50mm', '65mm', '80mm',
    '100mm', '125mm', '150mm', '200mm', '250mm', '300mm', '350mm',
    '400mm', '450mm', '500mm', '600mm',
}
# Reject tokens where the numeric prefix has > 3 consecutive digits with inch mark
# (e.g. 262" is impossible, 12" is valid) OR bare digit-only size > 24" (> 600mm)
_CORRUPT_SIZE_RE = re.compile(r'^(\d{4,})"?$', re.IGNORECASE)


def _validate_line_tag_size(tag: str) -> tuple:
    """
    Validate the size prefix of a line tag.
    Returns (is_valid: bool, flag_reason: str or None).
    """
    parts = tag.split('-')
    if not parts:
        return True, None
    p0 = parts[0].strip()
    # Check if there is a size token at all
    if not re.match(r'^[\d/]', p0):
        return True, None  # No size prefix — that's OK
    has_inch = '"' in p0 or "'" in p0
    # Strip inch mark and whitespace for comparison
    size_clean = p0.replace('"', '').replace("'", '').replace(' ', '').lower()
    # Reject corrupt large sizes (e.g. 262", 1000")
    if _CORRUPT_SIZE_RE.match(p0) or (has_inch and size_clean.isdigit() and int(size_clean) > 60):
        return False, f'size_out_of_range({p0})'
    size_with_mm = size_clean + 'mm' if size_clean.isdigit() else size_clean
    if size_clean in _VALID_INCH_SIZES or size_with_mm in _VALID_MM_SIZES:
        return True, None
    # Accept fractional sizes like 3/4
    if re.match(r'^\d+/\d+$', size_clean):
        if size_clean in _VALID_INCH_SIZES:
            return True, None
        # Fraction not in whitelist — flag but keep
        return True, 'unrecognized_fraction_size'
    # Numeric but not in whitelist
    if re.match(r'^\d+$', size_clean):
        try:
            n = int(size_clean)
            if has_inch and n > 60:
                return False, f'size_out_of_range({p0})'
            if 1 <= n <= 600:  # plausible DN size
                return True, 'unverified_size_token'
        except ValueError:
            pass
        return False, f'size_out_of_range({p0})'
    return True, None


# ──────────────────────────────────────────────────────────────────────────────
# Defect 2 Fix: Tag canonicalization for deduplication
# ──────────────────────────────────────────────────────────────────────────────
_AREA_PREFIX_RE = re.compile(r'^\d{2,3}-', re.IGNORECASE)


def canonicalize_tag(tag: str) -> str:
    """
    Strip leading unit/area number prefix (e.g. '26-', '43-') from a tag
    to get the canonical form used for deduplication.
    '26-PIT-9087' → 'PIT-9087',  'PIT-9087' → 'PIT-9087'
    """
    return _AREA_PREFIX_RE.sub('', tag.strip().upper())


def _ocr_correct(text: str) -> str:
    """Apply context-aware OCR character corrections before regex classification."""
    for pattern, replacement in _OCR_CORRECTIONS:
        text = pattern.sub(replacement, text)
    return text


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\n', ' ').strip()
    return re.sub(r'\s+', ' ', text)


def classify_paddle_results(
    items: List[Dict[str, Any]],
    drawing_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scan ALL OCR items for embedded engineering tags using drawing-type-aware patterns.

    Fixes applied:
      Defect 2: Post-deduplication pass — merges short/prefixed tag variants by canonical key.
      Defect 3: Spatial setpoint negative-context filter — demotes PI-150, AT-225 setpoint numbers.
      Defect 4: Line-tag grammar validation & size whitelist rejection (262" rejected, 12mm retained).

    Retains ALL non-tag text lines as NOTE annotations so 100% of readable text is preserved.
    Adds 'confidence' and 'flag_reason' to every returned item.
    """
    found: Dict[str, Dict] = {}  # tag → item (deduplicated by EXACT tag string)
    dt = (drawing_type or 'PID').upper()

    for item_idx, item in enumerate(items):
        text = item.get('text', '').strip()
        conf = float(item.get('confidence', 0))

        if conf < 0.10 or not text:
            continue

        t = _normalize(text)
        t = _ocr_correct(t)   # Fix 1: pre-correct OCR character misreads
        if not t or len(t) < 2:
            continue

        item_added = False

        # ── 1. Specific Engineering Tag Extraction ─────────────────────────────

        # PSV tags
        for m in _PSV_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'PSV_TAG', conf, item)
                item_added = True

        # Line tags — Defect 4: strip NOTE refs, validate pipe size
        for m in _LINE_SEARCH.finditer(t):
            raw_tag = m.group(1)
            # Strip NOTE xx references before processing
            raw_tag_clean = _NOTE_REF_STRIP_RE.sub('', raw_tag).strip().rstrip('-')
            tag = re.sub(r'\s+', '', raw_tag_clean).upper()
            if not tag or len(tag) < 4:
                continue
            flag_reason = None
            tag_conf = conf
            size_valid, size_flag = _validate_line_tag_size(tag)
            if not size_valid:
                # Defect 4 Fix: Reject corrupt line size from LINE_TAG list emission
                demoted_item = _make_item(
                    tag, 'NOTE', 0.25, item,
                    flag_reason=size_flag or 'size_out_of_range'
                )
                found[tag] = demoted_item
                item_added = True
                continue

            if size_flag:
                flag_reason = size_flag
                tag_conf = min(conf, 0.75)
            if raw_tag_clean != raw_tag.strip():
                # NOTE was stripped — record it
                note_ref = _NOTE_REF_STRIP_RE.search(raw_tag)
                if note_ref and not flag_reason:
                    flag_reason = f'note_ref_stripped({note_ref.group().strip()})'
            if tag not in found:
                found[tag] = _make_item(tag, 'LINE_TAG', tag_conf, item,
                                        flag_reason=flag_reason)
                item_added = True

        # Project-prefix tags (instruments + equipment)
        for m in _PROJECT_TAG_SEARCH.finditer(t):
            full_tag = m.group(1).upper()
            code = m.group(2).upper()
            seq = m.group(3)
            if len(seq) == 6:
                continue  # Drawing reference number, skip
            # Reject spec codes like GC11S, AS20S embedded in full tag
            if _SPEC_CODE_PATTERN.match(full_tag) or _SERVICE_CODE_PATTERN.match(full_tag):
                continue
            if full_tag in found and found[full_tag]['classification'] != 'NOTE':
                continue

            _VALVE_FUNCTION_CODES = {'CB', 'GB', 'BL', 'GT', 'BT', 'GL', 'NV'}
            if code in _VALVE_FUNCTION_CODES and len(re.sub(r'\D', '', seq)) >= 4:
                cat = 'VALVE_TAG'
            elif code in _INSTRUMENT_CODES:
                cat = 'INSTRUMENT_TAG'
            elif code in _EQUIPMENT_CODES:
                cat = 'EQUIPMENT_TAG'
            elif len(seq) >= 4:
                cat = 'INSTRUMENT_TAG'
            else:
                cat = 'EQUIPMENT_TAG'

            if full_tag not in found:
                found[full_tag] = _make_item(full_tag, cat, conf, item)
                item_added = True

        # Bare instrument tags — Defect 3: setpoint negative-context guard for 3-digit setpoints
        for m in _BARE_INSTRUMENT_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag in found:
                continue
            seq_num = re.sub(r'\D', '', tag)
            is_3digit_setpoint = len(seq_num) == 3
            if is_3digit_setpoint and (_is_setpoint_context_spatial(item_idx, items) or _is_setpoint_context(t, m.start(), m.end())):
                # 3-digit candidate matches setpoint context (e.g. PI-150 in SD HH: 150) — demote to NOTE
                found[tag] = _make_item(
                    tag, 'NOTE', 0.15, item,
                    flag_reason='ambiguous_setpoint_vs_tag'
                )
                logger.debug(f"Setpoint guard: demoted bare setpoint '{tag}' to NOTE")
            else:
                # Real bare instrument tag (e.g. TIT-9025, PIT-9016)
                found[tag] = _make_item(
                    tag, 'INSTRUMENT_TAG', min(conf, 0.85), item
                )
            item_added = True

        # Valve tags
        for m in _VALVE_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if not re.match(r'\d{2}[A-Z]{2}\d{7,}', tag):
                if tag not in found:
                    found[tag] = _make_item(tag, 'VALVE_TAG', conf, item)
                    item_added = True

        # Electrical / Earthing / SLD / Lighting patterns
        for m in _EARTH_BAR_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'EARTH_BAR_TAG', conf, item)
                item_added = True
        for m in _EARTH_PIT_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'EARTH_PIT_TAG', conf, item)
                item_added = True
        for m in _BOND_CONDUCTOR_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'BOND_CONDUCTOR_TAG', conf, item)
                item_added = True
        for m in _PANEL_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'PANEL_TAG', conf, item)
                item_added = True
        for m in _CIRCUIT_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'CIRCUIT_TAG', conf, item)
                item_added = True
        for m in _LUMINAIRE_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'LUMINAIRE_TAG', conf, item)
                item_added = True

        # Generic equipment — guarded with prefix allowlist
        for m in _GENERIC_EQUIP_PATTERN.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                prefix = tag.split('-')[0].upper()
                if _SPEC_CODE_PATTERN.match(tag) or _SERVICE_CODE_PATTERN.match(tag):
                    continue
                if (prefix in _EQUIP_PREFIX_ALLOWLIST
                        and not _EQUIP_REJECT_PATTERN.match(tag)
                        and len(prefix) <= 3):
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
                    item_added = True

        # Elevation tags
        for m in _ELEVATION_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'ELEVATION_TAG', conf, item)
                item_added = True

        # Rating tags
        for m in _RATING_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'RATING', conf, item)
                item_added = True

        # ── 2. Universal Note Preservation ────────────────────────────────────
        if not item_added and len(t) >= 3:
            if t not in found:
                found[t] = _make_item(t, 'NOTE', conf, item)

    # ── Defect 2 Fix: Post-deduplication pass ─────────────────────────────────
    # Merge items whose canonical form (strip area prefix) is identical.
    # Keep the longer (project-prefixed) tag; record short form as alias.
    canonical_map: Dict[str, str] = {}  # canonical_key → winning raw tag
    _ENG_CLASSES = {
        'INSTRUMENT_TAG', 'VALVE_TAG', 'EQUIPMENT_TAG', 'PSV_TAG', 'LINE_TAG',
    }
    for tag, item in list(found.items()):
        if item['classification'] not in _ENG_CLASSES:
            continue
        ck = canonicalize_tag(tag)
        if ck in canonical_map:
            winner_tag = canonical_map[ck]
            loser_tag = tag
            # Prefer the longer (project-prefixed) form
            if len(tag) > len(winner_tag):
                winner_tag, loser_tag = tag, winner_tag
                canonical_map[ck] = winner_tag
            # Merge alias into winner
            winner_item = found[winner_tag]
            aliases = winner_item.get('aliases') or []
            if loser_tag not in aliases and loser_tag != winner_tag:
                aliases.append(loser_tag)
            winner_item['aliases'] = aliases
            # Remove loser from found (replaced by winner)
            if loser_tag in found and loser_tag != winner_tag:
                del found[loser_tag]
                logger.debug(f"Dedup: merged '{loser_tag}' into '{winner_tag}' (alias)")
        else:
            canonical_map[ck] = tag

    results = list(found.values())

    # Sort: engineering tags first, notes last
    priority = {
        'EQUIPMENT_TAG': 0, 'LINE_TAG': 1, 'INSTRUMENT_TAG': 2,
        'PSV_TAG': 3, 'VALVE_TAG': 4,
        'PANEL_TAG': 5, 'CIRCUIT_TAG': 6, 'LUMINAIRE_TAG': 7,
        'EARTH_BAR_TAG': 8, 'EARTH_PIT_TAG': 9, 'BOND_CONDUCTOR_TAG': 10,
        'ELEVATION_TAG': 11, 'RATING': 12, 'NOTE': 13,
    }
    results.sort(key=lambda x: priority.get(x['classification'], 99))

    breakdown = {}
    flagged = 0
    for r in results:
        breakdown[r['classification']] = breakdown.get(r['classification'], 0) + 1
        if r.get('flag_reason'):
            flagged += 1
    logger.info(
        f"[{dt}] Tag classifier extracted {len(results)} total items from "
        f"{len(items)} OCR items. Breakdown: "
        + ', '.join(f"{k}:{v}" for k, v in sorted(breakdown.items()))
        + (f" | Flagged: {flagged}" if flagged else "")
    )
    return results


def _make_item(
    tag: str,
    classification: str,
    conf: float,
    raw_item: dict,
    flag_reason: Optional[str] = None,
) -> dict:
    """Create a structured classification result dict with confidence and flag_reason."""
    attrs = {
        'ocr_confidence': str(round(conf, 2)),
        'pos_x': str(raw_item.get('center_x', 0)),
        'pos_y': str(raw_item.get('center_y', 0)),
    }
    return {
        'tag': tag,
        'classification': classification,
        'value': tag,
        'rating': None,
        'attributes': attrs,
        'confidence': round(conf, 3),
        'flag_reason': flag_reason,
        'aliases': [],
    }


def extract_metadata_from_paddle(items: List[Dict[str, Any]], filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract drawing type, discipline, title, drawing number, and revision from OCR text items.
    """
    from src.utils.drawing_type_detector import detect_drawing_type, DRAWING_TYPE_LABELS
    dtype = detect_drawing_type(ocr_items=items, filename=filename)
    info = DRAWING_TYPE_LABELS[dtype]

    dwg_no = "UNKNOWN"
    title = info["label"]
    rev = "0"

    for item in items:
        txt = item.get("text", "").strip()
        if not txt:
            continue
        if re.search(r'\b(DWG|DRAWING|DOC)\s*(NO|NUM|\.|\#)?:?\s*([A-Z0-9\-_]{6,30})\b', txt, re.I):
            m = re.search(r'\b([A-Z0-9\-_]{6,30})\b', txt)
            if m and len(m.group(1)) > 6:
                dwg_no = m.group(1)
        elif "REV" in txt.upper():
            m = re.search(r'\b(REV\s*[-.:]?\s*[A-Z0-9]{1,3})\b', txt, re.I)
            if m:
                rev = m.group(1)

    return {
        "drawing_type": dtype.value,
        "discipline": info["discipline"],
        "drawing_number": dwg_no,
        "title": title,
        "revision": rev,
        "client_name": "Unknown",
        "page_count": 1,
    }
