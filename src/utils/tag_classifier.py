"""
Universal P&ID / Engineering Drawing Tag Classifier — Multi-Discipline, Zero LLM Tokens.

Strategy: SCAN each OCR string for embedded tag patterns using re.search()
          rather than matching the full string. This handles:
          - Tags embedded in phrases: "FROM 26-PIT-9077 IN 3RD STAGE" → extracts PIT-9077
          - Tags with surrounding OCR noise: "'IC'-VF-41-6027-4SJ05-CC" → extracts line tag
          - Multiple tags on one OCR line

Drawing-type-aware pattern sets (ISA 5.1 / IEC / CFIHOS):

  P&ID / Process:
    EQUIPMENT_TAG : 26-KA-901, TK-101, P-101
    LINE_TAG      : 8"-PV-26-9035-FC11S-08, 2"-WF-43-9032-GS225-CC
    INSTRUMENT_TAG: PIT-9062, 26-PIT-9077, TIT-9057, PDIT-9054
    VALVE_TAG     : 26CB9131, 26GB9178, HV-101, XV-201
    PSV_TAG       : 26-PSV-9066A

  Electrical Layout:
    LUMINAIRE_TAG : L-01, LS-201, TL-101
    PANEL_TAG     : DB-01, MDB-A, LDB-3, LPDB
    CIRCUIT_TAG   : C-101, CB-01, MCB-1
    ELEVATION_TAG : EL.100.000, EL 101.445, TL 101.445

  Earthing Layout:
    EARTH_BAR_TAG     : EB-01, EBM-01
    EARTH_PIT_TAG     : EP-01, EP-A
    BOND_CONDUCTOR_TAG: BC-01, EC-01

  Structural:
    GRID_REF  : A-1, B5, C-10
    ELEVATION : EL +100.000, RL 101.445

  Generic:
    EQUIPMENT_GENERIC : TK-101, P-101, E-101, V-201
    DRAWING_NUMBER    : 26-000001-001
    RATING            : 150#, 257 barg, 2500#
"""
from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ISA instrument function letter codes (P&ID)
# ──────────────────────────────────────────────────────────────────────────────
_INSTRUMENT_CODES = {
    'PIT', 'PDT', 'PDIT', 'PT', 'PI', 'PIC', 'PCV', 'PSV', 'PSH', 'PSL',
    'PRV', 'PV', 'PAH', 'PAL',
    'TIT', 'TT', 'TI', 'TIC', 'TCV', 'TSH', 'TSL', 'TE', 'TAH', 'TAL',
    'FIT', 'FT', 'FI', 'FIC', 'FCV', 'FE', 'FRC', 'FO', 'FSL', 'FSH', 'FAL',
    'LIT', 'LT', 'LI', 'LIC', 'LCV', 'LSH', 'LSL', 'LE', 'LAH', 'LAL',
    'AIT', 'AI', 'AT', 'AIC', 'ACV', 'AAH', 'AAL',
    'VSD', 'MCC', 'UCP', 'OMS',
    'PY', 'TY', 'FY', 'LY', 'AY',
    'HC', 'HS', 'HV', 'HIC',
    'XIT', 'XT', 'XI', 'XE', 'XV',
    'GC', 'RS', 'VD', 'FD',
    'JT', 'JI', 'JIC', 'JE',
    'SH', 'SL', 'ST',
    'WIT', 'WT', 'WI', 'WIC',
    'ZIT', 'ZT', 'ZI', 'ZIC', 'ZCV',
}

_EQUIPMENT_CODES = {
    # Compressors / Blowers
    'KA', 'KB', 'KC',
    # Heat exchangers / Coolers / Heaters
    'HA', 'HB', 'HC', 'EA', 'EB',
    # Vessels / Tanks
    'VA', 'VB', 'VC', 'TA', 'TB', 'TK',
    # Pumps
    'PA', 'PB', 'PC', 'GA', 'GB',
    # Filters / Separators
    'FA', 'FB', 'FC', 'SA', 'SB', 'SC', 'CX',
    # Skids / Packages
    'KZ', 'ME', 'MA', 'MB', 'NA', 'NB',
    # Miscellaneous
    'EC', 'GH', 'GJ', 'KD', 'KE', 'LA', 'LB',
}

# Generic 1-2 letter + number equipment (e.g., P-101, TK-101, E-201, V-301)
_GENERIC_EQUIP_PATTERN = re.compile(
    r'\b([A-Z]{1,3}-\d{3,5}[A-Z]?(?:/[A-Z])?)\b', re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# P&ID Search Patterns
# ──────────────────────────────────────────────────────────────────────────────

# PSV — most specific, must come first
_PSV_SEARCH = re.compile(
    r'\b(\d{0,4}-?PSV-\d{3,5}[A-Z]?)\b', re.IGNORECASE
)

# Equipment tags: 26-KA-901, 26-HA-911-C01 (2-letter equipment code from known list)
# Instrument tags with project prefix: 26-PIT-9077, 26-TIT-9057
_PROJECT_TAG_SEARCH = re.compile(
    r'\b(\d{2}-([A-Z]{2,4})-([\dA-Z]{3,6})(?:-[A-Z]{1,4}\d{1,4})?)\b',
    re.IGNORECASE
)

# Bare instrument tags without project prefix: PIT-9062, TIT-9057, PDIT-9054
_ISA_CODES_JOINED = '|'.join(sorted(_INSTRUMENT_CODES, key=len, reverse=True))
_BARE_INSTRUMENT_SEARCH = re.compile(
    rf'\b((?:{_ISA_CODES_JOINED})-?\d{{3,5}}[A-Z]?)\b',
    re.IGNORECASE
)

# Valve tags: 26CB9131, 26GB9178, HV-101, XV-201
_VALVE_SEARCH = re.compile(
    r'\b(\d{2}[A-Z]{2}\d{4,6}|(?:HV|XV|CV|PCV|FCV|TCV|LCV|EV|MOV|SDV|BDV|FV)-\d{3,5}[A-Z]?)\b',
    re.IGNORECASE
)

# Line tags: 8"-PV-26-9035-FC11S-08 or 2"-WF-43-9032-GS225-CC
_LINE_SEARCH = re.compile(
    r'(\d+(?:[/\\]\d+)?["\']?\s*[-–]\s*[A-Z]{2,4}\s*[-–]\s*\d{2}\s*[-–]\s*\d{4,5}'
    r'(?:\s*[-–]\s*[A-Z0-9]{2,8}){1,2})',
    re.IGNORECASE
)

# Pressure/class ratings
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

# Panel / distribution board tags: DB-01, MDB-A, LDB-3, LPDB, EMDB
_PANEL_SEARCH = re.compile(
    r'\b((?:EMDB|MVDB|LVDB|LPDB|EPDB|MDB|LDB|SDB|DB|PDB|NDB|MSB|LSB|ESB|SMDB)\s*[-–/]?\s*[A-Z0-9]{0,4})\b',
    re.IGNORECASE
)

# Circuit / breaker tags: C-101, CB-01, MCB-1
_CIRCUIT_SEARCH = re.compile(
    r'\b((?:MCB|RCCB|MCCB|ACB|VCB|CB|C)-\d{1,4}[A-Z]?)\b', re.IGNORECASE
)

# ──────────────────────────────────────────────────────────────────────────────
# Earthing Layout Patterns
# ──────────────────────────────────────────────────────────────────────────────

# Earth bar: EB-01, EBM-01
_EARTH_BAR_SEARCH = re.compile(r'\b(EBM?-\d{1,4}[A-Z]?)\b', re.IGNORECASE)

# Earth pit / electrode: EP-01, EP-A
_EARTH_PIT_SEARCH = re.compile(r'\b(EP-[A-Z0-9]{1,4})\b', re.IGNORECASE)

# Bonding / earthing conductor: BC-01, EC-01
_BOND_CONDUCTOR_SEARCH = re.compile(r'\b([BE]C-\d{1,4}[A-Z]?)\b', re.IGNORECASE)

# ──────────────────────────────────────────────────────────────────────────────
# Structural / Grid Patterns
# ──────────────────────────────────────────────────────────────────────────────

# Grid references: A1, B-5, C10
_GRID_REF_SEARCH = re.compile(r'\b([A-Z]-?\d{1,3})\b')

# ──────────────────────────────────────────────────────────────────────────────
# Text normalization
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Apply light normalization to fix common OCR errors before pattern matching."""
    t = text.strip()
    t = t.strip("~`'\"_|{}[]")
    t = re.sub(r'\s+', ' ', t)
    return t


# ──────────────────────────────────────────────────────────────────────────────
# Drawing-type-aware classify_tag (single string)
# ──────────────────────────────────────────────────────────────────────────────

def classify_tag(text: str, drawing_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Classify a single raw OCR string.
    Scans the string for embedded tag patterns.
    Returns the FIRST matching tag found, or a NOTE dict if plain text.

    Args:
        text:         Raw OCR string.
        drawing_type: DrawingType enum value string (e.g., 'PID', 'ELECTRICAL_LAYOUT').
                      When None, all pattern sets are tried with P&ID prioritized.
    """
    t = _normalize(text)
    if not t or len(t) < 2:
        return None

    dt = (drawing_type or '').upper()

    # ── Electrical Layout ──────────────────────────────────────────────────
    if dt == 'ELECTRICAL_LAYOUT':
        for pat, cat in [
            (_PANEL_SEARCH, 'PANEL_TAG'),
            (_CIRCUIT_SEARCH, 'CIRCUIT_TAG'),
            (_LUMINAIRE_SEARCH, 'LUMINAIRE_TAG'),
            (_ELEVATION_SEARCH, 'ELEVATION_TAG'),
        ]:
            m = pat.search(t)
            if m:
                return _tag_dict(m.group(1).strip(), cat)
        return _generic_note(t)

    # ── Earthing Layout ────────────────────────────────────────────────────
    if dt == 'EARTHING_LAYOUT':
        for pat, cat in [
            (_EARTH_BAR_SEARCH, 'EARTH_BAR_TAG'),
            (_EARTH_PIT_SEARCH, 'EARTH_PIT_TAG'),
            (_BOND_CONDUCTOR_SEARCH, 'BOND_CONDUCTOR_TAG'),
            (_ELEVATION_SEARCH, 'ELEVATION_TAG'),
        ]:
            m = pat.search(t)
            if m:
                return _tag_dict(m.group(1).strip(), cat)
        return _generic_note(t)

    # ── SLD / Cable Schedule / HVAC / Structural / Generic ────────────────
    if dt in ('SLD', 'CABLE_SCHEDULE', 'HVAC_LAYOUT', 'STRUCTURAL_LAYOUT', 'GENERIC'):
        m = _PANEL_SEARCH.search(t)
        if m:
            return _tag_dict(m.group(1).strip(), 'PANEL_TAG')
        m = _ELEVATION_SEARCH.search(t)
        if m:
            return _tag_dict(m.group(1).strip(), 'ELEVATION_TAG')
        m = _GENERIC_EQUIP_PATTERN.search(t)
        if m:
            return _tag_dict(m.group(1).upper(), 'EQUIPMENT_TAG')
        return _generic_note(t)

    # ── P&ID / PFD / Isometric / Unknown (default path) ──────────────────
    m = _PSV_SEARCH.search(t)
    if m:
        return _tag_dict(m.group(1).upper(), 'PSV_TAG')

    m = _LINE_SEARCH.search(t)
    if m:
        return _tag_dict(re.sub(r'\s+', '', m.group(1)).upper(), 'LINE_TAG')

    for m in _PROJECT_TAG_SEARCH.finditer(t):
        full_tag = m.group(1).upper()
        code = m.group(2).upper()
        if code in _INSTRUMENT_CODES:
            return _tag_dict(full_tag, 'INSTRUMENT_TAG')
        elif code in _EQUIPMENT_CODES:
            return _tag_dict(full_tag, 'EQUIPMENT_TAG')
        elif len(m.group(3)) >= 4:
            return _tag_dict(full_tag, 'INSTRUMENT_TAG')
        else:
            return _tag_dict(full_tag, 'EQUIPMENT_TAG')

    m = _BARE_INSTRUMENT_SEARCH.search(t)
    if m:
        return _tag_dict(m.group(1).upper(), 'INSTRUMENT_TAG')

    m = _VALVE_SEARCH.search(t)
    if m:
        tag = m.group(1).upper()
        if not re.match(r'\d{2}[A-Z]{2}\d{7,}', tag):
            return _tag_dict(tag, 'VALVE_TAG')

    m = _GENERIC_EQUIP_PATTERN.search(t)
    if m:
        return _tag_dict(m.group(1).upper(), 'EQUIPMENT_TAG')

    m = _RATING_SEARCH.search(t)
    if m:
        return {'tag': m.group(1), 'classification': 'RATING',
                'value': m.group(1), 'rating': m.group(1), 'attributes': None}

    return _generic_note(t)


def _tag_dict(tag: str, classification: str) -> Dict[str, Any]:
    return {'tag': tag, 'classification': classification,
            'value': tag, 'rating': None, 'attributes': None}


def _generic_note(t: str) -> Optional[Dict[str, Any]]:
    if len(t) <= 2:
        return None
    return {'tag': t, 'classification': 'NOTE', 'value': t,
            'rating': None, 'attributes': None}


# ──────────────────────────────────────────────────────────────────────────────
# Bulk classifier (used by TextDetectionAgent)
# ──────────────────────────────────────────────────────────────────────────────

def classify_paddle_results(
    items: List[Dict[str, Any]],
    drawing_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scan ALL OCR items for embedded tags using drawing-type-aware regex search.

    Each OCR item may contain multiple tags (e.g. a note line referencing two tags).
    This function extracts ALL tags found across all items.

    Args:
        items:        List of dicts from run_paddle_ocr() with 'text', 'confidence', ...
        drawing_type: DrawingType string (e.g. 'PID', 'ELECTRICAL_LAYOUT'). When None,
                      the function uses P&ID patterns (backward-compatible behaviour).

    Returns:
        List of classified dicts matching RawTextDetection schema, deduplicated.
    """
    found: Dict[str, Dict] = {}  # tag → item (for deduplication)
    dt = (drawing_type or 'PID').upper()

    for item in items:
        text = item.get('text', '').strip()
        conf = item.get('confidence', 0)

        if conf < 0.15 or not text:
            continue

        t = _normalize(text)
        if not t:
            continue

        # ── Electrical Layout ──────────────────────────────────────────────
        if dt == 'ELECTRICAL_LAYOUT':
            _scan_and_add(found, conf, item, [
                (_PANEL_SEARCH, 'PANEL_TAG', 1),
                (_CIRCUIT_SEARCH, 'CIRCUIT_TAG', 1),
                (_LUMINAIRE_SEARCH, 'LUMINAIRE_TAG', 1),
                (_ELEVATION_SEARCH, 'ELEVATION_TAG', 1),
            ], t)
            # Also try generic equipment
            for m in _GENERIC_EQUIP_PATTERN.finditer(t):
                tag = m.group(1).upper()
                if tag not in found:
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
            continue

        # ── Earthing Layout ────────────────────────────────────────────────
        if dt == 'EARTHING_LAYOUT':
            _scan_and_add(found, conf, item, [
                (_EARTH_BAR_SEARCH, 'EARTH_BAR_TAG', 1),
                (_EARTH_PIT_SEARCH, 'EARTH_PIT_TAG', 1),
                (_BOND_CONDUCTOR_SEARCH, 'BOND_CONDUCTOR_TAG', 1),
                (_ELEVATION_SEARCH, 'ELEVATION_TAG', 1),
            ], t)
            for m in _GENERIC_EQUIP_PATTERN.finditer(t):
                tag = m.group(1).upper()
                if tag not in found:
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
            continue

        # ── SLD ────────────────────────────────────────────────────────────
        if dt == 'SLD':
            _scan_and_add(found, conf, item, [
                (_PANEL_SEARCH, 'PANEL_TAG', 1),
                (_CIRCUIT_SEARCH, 'CIRCUIT_TAG', 1),
            ], t)
            for m in _GENERIC_EQUIP_PATTERN.finditer(t):
                tag = m.group(1).upper()
                if tag not in found:
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
            continue

        # ── Structural / HVAC / Cable / Generic ────────────────────────────
        if dt in ('STRUCTURAL_LAYOUT', 'HVAC_LAYOUT', 'CABLE_SCHEDULE', 'GENERIC'):
            _scan_and_add(found, conf, item, [
                (_ELEVATION_SEARCH, 'ELEVATION_TAG', 1),
                (_PANEL_SEARCH, 'PANEL_TAG', 1),
            ], t)
            for m in _GENERIC_EQUIP_PATTERN.finditer(t):
                tag = m.group(1).upper()
                if tag not in found:
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)
            continue

        # ── P&ID / PFD / Isometric / default ──────────────────────────────
        # PSV tags
        for m in _PSV_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'PSV_TAG', conf, item)

        # Line tags
        for m in _LINE_SEARCH.finditer(t):
            tag = re.sub(r'\s+', '', m.group(1)).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'LINE_TAG', conf, item)

        # Project-prefix tags (instruments + equipment)
        for m in _PROJECT_TAG_SEARCH.finditer(t):
            full_tag = m.group(1).upper()
            code = m.group(2).upper()
            seq = m.group(3)
            if len(seq) == 6:
                continue  # Drawing number, skip
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

        # Bare instrument tags
        for m in _BARE_INSTRUMENT_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if tag not in found:
                found[tag] = _make_item(tag, 'INSTRUMENT_TAG', conf, item)

        # Valve tags
        for m in _VALVE_SEARCH.finditer(t):
            tag = m.group(1).upper()
            if re.match(r'\d{2}[A-Z]{2}\d{7,}', tag):
                continue
            if tag not in found:
                found[tag] = _make_item(tag, 'VALVE_TAG', conf, item)

        # Generic equipment (fallback)
        for m in _GENERIC_EQUIP_PATTERN.finditer(t):
            tag = m.group(1).upper()
            # Skip if already captured as something more specific
            if tag not in found:
                # Only add if it actually looks like an equipment tag
                prefix = tag.split('-')[0]
                if len(prefix) <= 3 and prefix.isalpha():
                    found[tag] = _make_item(tag, 'EQUIPMENT_TAG', conf, item)

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

    # Log summary
    breakdown = {}
    for r in results:
        breakdown[r['classification']] = breakdown.get(r['classification'], 0) + 1
    logger.info(
        f"[{dt}] Tag classifier extracted {len(results)} unique tags from "
        f"{len(items)} OCR items. Breakdown: "
        + ', '.join(f"{k}:{v}" for k, v in sorted(breakdown.items()))
    )
    return results


def _scan_and_add(
    found: Dict,
    conf: float,
    item: Dict,
    patterns: List[tuple],
    text: str,
) -> None:
    """Helper: run a list of (pattern, category, group_idx) against text and add matches."""
    for pat, cat, grp in patterns:
        for m in pat.finditer(text):
            tag = m.group(grp).strip()
            if tag and tag not in found:
                found[tag] = _make_item(tag, cat, conf, item)


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


# ──────────────────────────────────────────────────────────────────────────────
# Metadata extraction from OCR — universal, drawing-type-aware
# ──────────────────────────────────────────────────────────────────────────────

def extract_metadata_from_paddle(
    items: List[Dict[str, Any]],
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reconstruct drawing metadata from OCR text — no LLM required.
    Performs drawing-type detection internally using the drawing_type_detector.
    """
    from src.utils.drawing_type_detector import detect_drawing_type, DRAWING_TYPE_LABELS

    all_texts = [i['text'] for i in items if i.get('confidence', 0) > 0.3]

    # Auto-detect drawing type
    detected_type = detect_drawing_type(ocr_items=items, filename=filename)
    type_label = DRAWING_TYPE_LABELS[detected_type]
    discipline = type_label.get('discipline', 'Unknown')

    # Drawing number: NN-NNNNNN-NNN or similar doc number formats
    drawing_num = 'UNKNOWN'
    drawing_pat = re.compile(r'\b(\d{2}-\d{5,6}-\d{3})\b')
    for t in all_texts:
        m = drawing_pat.search(t)
        if m:
            drawing_num = m.group(1)
            break

    # Revision
    revision = '0'
    for t in all_texts:
        m = re.search(r'\bRev\.?\s*([A-Z0-9]{1,3})\b', t, re.IGNORECASE)
        if m:
            revision = m.group(1)
            break

    # Title: longest all-caps string from bottom of image
    bottom_texts = [
        i['text'] for i in items
        if i.get('center_y', 0) > 0.7
        and i.get('confidence', 0) > 0.4
        and i['text'].upper() == i['text']
        and len(i['text']) > 8
    ]
    if bottom_texts:
        title = max(bottom_texts, key=len)
    else:
        # Fall back to longest high-confidence string anywhere
        high_conf = [i['text'] for i in items if i.get('confidence', 0) > 0.5 and len(i['text']) > 8]
        title = max(high_conf, key=len) if high_conf else type_label['label']

    return {
        'drawing_type': detected_type.value,
        'discipline': discipline,
        'drawing_number': drawing_num,
        'title': title,
        'revision': revision,
        'client_name': 'Unknown',
        'page_count': 1,
    }
