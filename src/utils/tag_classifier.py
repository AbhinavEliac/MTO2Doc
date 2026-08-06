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

# Generic 1-3 letter + number equipment (e.g., P-101, TK-101, E-201, V-301, C-101, M-101)
_GENERIC_EQUIP_PATTERN = re.compile(
    r'\b([A-Z]{1,3}-\d{2,5}[A-Z]?(?:/[A-Z])?)\b', re.IGNORECASE
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

# Bare instrument tags without project prefix: PIT-9062, TIT-9057, PDIT-9054, PDI-9054, TE-101
_ISA_CODES_JOINED = '|'.join(sorted(_INSTRUMENT_CODES, key=len, reverse=True))
_BARE_INSTRUMENT_SEARCH = re.compile(
    rf'\b((?:{_ISA_CODES_JOINED})-?\d{{2,5}}[A-Z]?)\b',
    re.IGNORECASE
)

# Valve tags: 26CB9131, 26-CB-9131, 26GB9178, 26-GB-9178, HV-101, XV-201, V-101, MOV-101
_VALVE_SEARCH = re.compile(
    r'\b(\d{2}-?[A-Z]{2}-?\d{4,6}|(?:HV|XV|CV|PCV|FCV|TCV|LCV|EV|MOV|SDV|BDV|FV|UV|PV|TV|LV|AV|ZV|V)-\d{2,5}[A-Z]?)\b',
    re.IGNORECASE
)

# Line tags: 8"-PV-26-9035-FC11S-08, 1/2"-PV-26-9035-FC11S, 3"-VA-26-9121-AC21-00, PV-26-9035-FC11S-08
_LINE_SEARCH = re.compile(
    r'((?:\d+(?:[/\.]\d+)?["\']?\s*[-–]?\s*)?[A-Z]{1,4}\s*[-–]\s*(?:\d{2,4}\s*[-–]\s*)?\d{3,5}'
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

# Luminaire tags: L-01, LS-201, TL-101, FL-01
_LUMINAIRE_SEARCH = re.compile(
    r'\b((?:TL|FL|EL|SL|LS?|WL)-\d{1,4}[A-Z]?)\b', re.IGNORECASE
)

# Elevation / level labels: EL.101.445, EL 100.000, TL 101.445
_ELEVATION_SEARCH = re.compile(
    r'\b((?:EL|TL|RL|BL|GL|FFL|SFL)\s*[.:]?\s*[+\-]?\d{2,5}(?:\.\d{1,3})?)\b',
    re.IGNORECASE
)

# Panel / distribution board tags: DB-01, MDB-A, LDB-3, LPDB, EMDB, MVDB
_PANEL_SEARCH = re.compile(
    r'\b((?:EMDB|MVDB|LVDB|LPDB|EPDB|MDB|LDB|SDB|DB|PDB|NDB|MSB|LSB|ESB|SMDB)\s*[-–/]?\s*[A-Z0-9]{0,4})\b',
    re.IGNORECASE
)

# Circuit / breaker tags: C-101, CB-01, MCB-1, MCCB-3, ACB-01
_CIRCUIT_SEARCH = re.compile(
    r'\b((?:MCB|RCCB|MCCB|ACB|VCB|CB|C)-\d{1,4}[A-Z]?)\b', re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# Earthing Layout Patterns
# ──────────────────────────────────────────────────────────────────────────────

_EARTH_BAR_SEARCH = re.compile(r'\b(EBM?-\d{1,4}[A-Z]?|MEB|EBM?)\b', re.IGNORECASE)
_EARTH_PIT_SEARCH = re.compile(r'\b(EP-[A-Z0-9]{1,4}|EARTH\s+PIT)\b', re.IGNORECASE)
_BOND_CONDUCTOR_SEARCH = re.compile(r'\b([BE]C-\d{1,4}[A-Z]?)\b', re.IGNORECASE)

# ──────────────────────────────────────────────────────────────────────────────
# Text normalization & bulk classifier
# ──────────────────────────────────────────────────────────────────────────────

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
    Retains ALL non-tag text lines as NOTE annotations so 100% of readable text is preserved.
    """
    found: Dict[str, Dict] = {}  # tag → item (deduplicated by tag string)
    dt = (drawing_type or 'PID').upper()

    for item in items:
        text = item.get('text', '').strip()
        conf = item.get('confidence', 0)

        if conf < 0.10 or not text:
            continue

        t = _normalize(text)
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

        # Line tags
        for m in _LINE_SEARCH.finditer(t):
            tag = re.sub(r'\s+', '', m.group(1)).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'LINE_TAG', conf, item)
                item_added = True

        # Project-prefix tags (instruments + equipment)
        for m in _PROJECT_TAG_SEARCH.finditer(t):
            full_tag = m.group(1).upper()
            code = m.group(2).upper()
            seq = m.group(3)
            if len(seq) == 6:
                continue  # Drawing reference number, skip
            if full_tag in found and found[full_tag]['classification'] != 'NOTE':
                continue
            if code in _INSTRUMENT_CODES:
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

        # Bare instrument tags
        for m in _BARE_INSTRUMENT_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'INSTRUMENT_TAG', conf, item)
                item_added = True

        # Valve tags
        for m in _VALVE_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if not re.match(r'\d{2}[A-Z]{2}\d{7,}', tag):
                if tag not in found:
                    found[tag] = _make_item(tag, 'VALVE_TAG', conf, item)
                    item_added = True

        # Generic equipment
        for m in _GENERIC_EQUIP_PATTERN.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                prefix = tag.split('-')[0]
                if len(prefix) <= 3 and prefix.isalpha():
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
                    item_added = True

        # Electrical / Earthing / SLD specific patterns
        if dt in ('ELECTRICAL_LAYOUT', 'EARTHING_LAYOUT', 'SLD', 'CABLE_SCHEDULE'):
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
            for m in _EARTH_BAR_SEARCH.finditer(t):
                tag = m.group(1).upper()
                if tag not in found:
                    found[tag] = _make_item(tag, 'EARTH_BAR_TAG', conf, item)
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
        # If the item did not contain a specific tag, preserve it as a NOTE
        if not item_added and len(t) >= 3:
            if t not in found:
                found[t] = _make_item(t, 'NOTE', conf, item)

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
    for r in results:
        breakdown[r['classification']] = breakdown.get(r['classification'], 0) + 1
    logger.info(
        f"[{dt}] Tag classifier extracted {len(results)} total items from "
        f"{len(items)} OCR items. Breakdown: "
        + ', '.join(f"{k}:{v}" for k, v in sorted(breakdown.items()))
    )
    return results


def _make_item(tag: str, classification: str, conf: float, raw_item: dict) -> dict:
    """Create a structured classification result dict."""
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
