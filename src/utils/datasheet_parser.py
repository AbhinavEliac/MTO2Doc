"""
Datasheet Block Detector & PSV Set-Pressure Parser.

Extracts structured equipment datasheet fields and PSV set pressures
from OCR items using proximity-based key-value block matching.

These are the two highest-impact empty-field categories identified in QA:
  • Equipment: design_pressure, design_temperature, flow_rate, duty, material, vendor, quantity
  • PSV: set_pressure (SP= value near PSV tag)
"""
from __future__ import annotations

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ─── Equipment Datasheet Field Patterns ──────────────────────────────────────

_DATASHEET_FIELDS: List[Dict[str, Any]] = [
    # Each entry: key name in output dict, regex to detect the label, regex to capture the value
    {
        'field': 'duty',
        'label_re': re.compile(r'\b(?:DUTY|POWER|RATED\s*POWER|MOTOR\s*POWER)\b', re.I),
        'value_re': re.compile(r'([\d,.]+\s*(?:kW|MW|HP|BHP))', re.I),
    },
    {
        'field': 'flow_rate',
        'label_re': re.compile(r'\b(?:FLOW\s*RATE|MASS\s*FLOW|CAPACITY|THROUGHPUT)\b', re.I),
        'value_re': re.compile(r'([\d,.\s]+\s*(?:kg/h|t/h|m3/h|MMSCFD|Sm3/h|Nm3/h|bbl/d))', re.I),
    },
    {
        'field': 'design_pressure',
        'label_re': re.compile(
            r'\b(?:DESIGN\s*PRESS(?:URE)?|DISC(?:HARGE)?\s*(?:PRESS(?:URE)?|OP(?:ERATING)?)|'
            r'MAX(?:IMUM)?\s*ALLOW(?:ABLE)?\s*(?:WORKING|OPERATING)?\s*PRESS(?:URE)?|MAWP|'
            r'DP|DESIGN\s*P)\b', re.I),
        'value_re': re.compile(r'((?:FV\s*/\s*)?[\d.,]+\s*(?:barg|bar\s*\(g\)|psig|kPag|MPag))', re.I),
    },
    {
        'field': 'design_temperature',
        'label_re': re.compile(
            r'\b(?:DESIGN\s*TEMP(?:ERATURE)?|OPERATING\s*TEMP(?:ERATURE)?|MAX\s*TEMP(?:ERATURE)?|DT)\b',
            re.I),
        'value_re': re.compile(r'((?:-?\d+\s*/\s*)?-?\d+\s*°?\s*[CF])', re.I),
    },
    {
        'field': 'material',
        'label_re': re.compile(r'\b(?:MATERIAL(?:\s*OF\s*CONSTRUCTION)?|MOC|METALLURGY)\b', re.I),
        'value_re': re.compile(r'(.{4,60})', re.I),  # capture rest of line (up to 60 chars)
    },
    {
        'field': 'vendor',
        'label_re': re.compile(r'\b(?:VENDOR|MANUFACTURER|SUPPLIER|MFR)\b', re.I),
        'value_re': re.compile(r'(.{3,50})', re.I),
    },
    {
        'field': 'quantity',
        'label_re': re.compile(r'\b(?:QUANTITY|QTY|NO\.\s*OF\s*UNITS|DUTY/STANDBY)\b', re.I),
        'value_re': re.compile(r'(\d+\s*[xX]\s*\d+%|\d+\s*(?:DUTY|STANDBY|INSTALLED)?)', re.I),
    },
    {
        'field': 'service',
        'label_re': re.compile(r'\b(?:SERVICE|FLUID|DESCRIPTION|APPLICATION)\b', re.I),
        'value_re': re.compile(r'(.{3,80})', re.I),
    },
    {
        'field': 'type',
        'label_re': re.compile(
            r'\b(?:TYPE|MACHINE\s*TYPE|COMPRESSOR\s*TYPE|PUMP\s*TYPE|VESSEL\s*TYPE)\b', re.I),
        'value_re': re.compile(r'(.{3,60})', re.I),
    },
]

# ─── PSV Set Pressure Pattern ────────────────────────────────────────────────

_SP_PATTERN = re.compile(
    r'SP\s*=\s*([\d.,]+\s*(?:bar[\s(g)]*|barg|psig|kPag))',
    re.IGNORECASE
)
_SET_PRESSURE_PATTERN = re.compile(
    r'SET\s*PRESS(?:URE)?\s*[=:]\s*([\d.,]+\s*(?:bar[\s(g)]*|barg|psig|kPag))',
    re.IGNORECASE
)

# Equipment tag pattern for anchoring
_EQUIP_TAG_RE = re.compile(r'\b\d{0,3}-?[A-Z]{1,3}-\d{2,5}[A-Z]?\b', re.IGNORECASE)
# PSV tag pattern
_PSV_TAG_RE = re.compile(r'\b(?:\d{0,3}-?)?PSV-\d{3,5}[A-Z]?\b', re.IGNORECASE)


def _get_float_y(item: Dict[str, Any]) -> float:
    """Safely extract float Y coordinate from item dict."""
    val = item.get('center_y') or (item.get('attributes') or {}).get('pos_y')
    if val is None:
        return -1.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return -1.0


def parse_equipment_datasheets(
    ocr_items: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """
    Scan OCR items for equipment datasheet key-value blocks and anchor them
    to the nearest equipment tag by Y-coordinate proximity.

    Returns:
        Dict mapping equipment_tag -> {field_name: value_string}
    """
    # Find all EQUIPMENT_TAG items as anchors
    equip_anchors = [
        item for item in ocr_items
        if item.get('classification') == 'EQUIPMENT_TAG'
    ]

    results: Dict[str, Dict[str, str]] = {}

    # For each OCR item, check if it's a datasheet label line
    for item in ocr_items:
        text = (item.get('text') or item.get('value') or item.get('tag') or '').strip()
        if not text or len(text) < 3:
            continue

        for field_def in _DATASHEET_FIELDS:
            if not field_def['label_re'].search(text):
                continue

            # Found a datasheet label — extract the value
            # Try to get value from same text (key: value on one line)
            val_match = field_def['value_re'].search(text)
            if not val_match:
                continue
            value = val_match.group(1).strip()
            if not value or len(value) < 2:
                continue

            # Find the nearest equipment tag by Y-position
            item_y = _get_float_y(item)
            if item_y < 0:
                # No position info — skip spatial anchor, try global assignment
                continue

            best_tag: Optional[str] = None
            best_dist = 0.15  # max Y-distance threshold (normalized)

            for anchor in equip_anchors:
                anchor_y = _get_float_y(anchor)
                if anchor_y < 0:
                    continue
                dist = abs(item_y - anchor_y)
                if dist < best_dist:
                    best_dist = dist
                    best_tag = anchor.get('tag') or anchor.get('value')

            if best_tag:
                if best_tag not in results:
                    results[best_tag] = {}
                # Don't overwrite if already set by closer item
                if field_def['field'] not in results[best_tag]:
                    results[best_tag][field_def['field']] = value
                    logger.debug(
                        f"Datasheet: {best_tag}.{field_def['field']} = '{value}' "
                        f"(Y-dist={best_dist:.3f})"
                    )

    if results:
        total_fields = sum(len(v) for v in results.values())
        logger.info(
            f"Datasheet parser: found {total_fields} field values "
            f"across {len(results)} equipment tags."
        )
    else:
        logger.info("Datasheet parser: no equipment datasheet blocks found.")

    return results


def parse_psv_set_pressures(
    ocr_items: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Scan OCR items for 'SP = <value>' or 'SET PRESSURE = <value>' patterns
    near PSV tags, and return a mapping of {psv_tag: set_pressure_string}.

    Anchoring: the PSV tag nearest in Y-coordinate to the SP= line gets assigned.

    Returns:
        Dict mapping psv_tag -> set_pressure string (e.g., "225.4 bar(g)")
    """
    # Find PSV anchors
    psv_anchors = [
        item for item in ocr_items
        if item.get('classification') == 'PSV_TAG'
    ]

    results: Dict[str, str] = {}

    for item in ocr_items:
        text = (item.get('text') or item.get('value') or item.get('tag') or '').strip()
        if not text:
            continue

        # Try SP= or SET PRESSURE= match
        val_match = _SP_PATTERN.search(text) or _SET_PRESSURE_PATTERN.search(text)
        if not val_match:
            continue

        sp_value = val_match.group(1).strip()
        sp_value = re.sub(r'\s+', ' ', sp_value).strip()

        # Normalize: "225.4 bar (g)" → "225.4 bar(g)"
        sp_value = re.sub(r'bar\s*\(g\)', 'bar(g)', sp_value, flags=re.I)
        sp_value = re.sub(r'barg', 'bar(g)', sp_value, flags=re.I)

        item_y = _get_float_y(item)

        best_tag: Optional[str] = None
        best_dist = 0.10  # max Y-distance to anchor PSV tag

        for anchor in psv_anchors:
            anchor_y = _get_float_y(anchor)
            if anchor_y < 0 or item_y < 0:
                # No position data — assign to any unassigned PSV
                if anchor.get('tag') and anchor['tag'] not in results:
                    best_tag = anchor['tag']
                continue
            dist = abs(item_y - anchor_y)
            if dist < best_dist:
                best_dist = dist
                best_tag = anchor.get('tag')

        if best_tag and best_tag not in results:
            results[best_tag] = sp_value
            logger.info(f"PSV set pressure: {best_tag} → '{sp_value}' (Y-dist={best_dist:.3f})")

    if results:
        logger.info(f"PSV parser: found set pressures for {len(results)} PSV tags: {results}")
    else:
        logger.info("PSV parser: no SP= values found near PSV tags.")

    return results
