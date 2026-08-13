"""
Datasheet Block Detector & PSV Set-Pressure Parser.

Extracts structured equipment datasheet fields and PSV set pressures
from OCR items using proximity-based key-value block matching.
"""
from __future__ import annotations

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Scope-marker set (bare words or asterisks that mean vendor-supplied item, not actual vendor name)
_SCOPE_MARKER_RE = re.compile(
    r'^(?:VENDOR|VENDOR\s+SUPPLY|VENDOR\s+SUPPLIED|BY\s+VENDOR|\*|N/A|ANY|-|\s*)$',
    re.IGNORECASE
)


def _extract_tail_value(text: str, label_pattern: str) -> Optional[str]:
    cleaned = re.sub(label_pattern, '', text, flags=re.I).strip().lstrip(':=- ').strip()
    return cleaned if len(cleaned) >= 2 else None


def _extract_vendor_value(text: str) -> Optional[str]:
    val = _extract_tail_value(text, r'\b(?:VENDOR|MANUFACTURER|SUPPLIER|MFR)\b')
    if not val:
        return None
    if _SCOPE_MARKER_RE.match(val):
        return None
    return val


def _extract_type_value(text: str) -> Optional[str]:
    if text.strip().startswith('('):
        return None
    val = _extract_tail_value(text, r'\b(?:TYPE|MACHINE\s*TYPE|COMPRESSOR\s*TYPE|PUMP\s*TYPE|VESSEL\s*TYPE)\b')
    if not val or val.startswith('('):
        return None
    return val


def _extract_unit_value(text: str, unit_re: str, num_re: str, unit_default: str = '') -> Optional[str]:
    m_num = re.search(r'([\d,]+(?:\.\d+)?)', text)
    if not m_num:
        return None
    num_str = m_num.group(1).strip()
    m_unit = re.search(r'\b(' + unit_re + r')\b', text, re.I)
    unit_str = m_unit.group(1).strip() if m_unit else unit_default
    return f"{num_str} {unit_str}".strip()


def _extract_pressure_value(text: str) -> Optional[str]:
    m_unit = re.search(r'\b(barg|bar\s*\(g\)|psig|kPag|MPag)\b', text, re.I)
    unit_str = m_unit.group(1) if m_unit else "Barg"
    m_num = re.search(r'\b((?:FV\s*/\s*)?\d+(?:\.\d+)?(?:\s*/\s*(?:FV|\d+(?:\.\d+)?))*)\b', text, re.I)
    if m_num:
        val_str = m_num.group(1).strip()
        if len(val_str) >= 1 and re.search(r'\d', val_str):
            return f"{val_str} {unit_str}".strip() if not re.search(r'barg|psig|kpag', val_str, re.I) else val_str
    return None


def _extract_temp_value(text: str) -> Optional[str]:
    num_match = re.search(r'(-?\d+[\d.,\s/°CF-]{2,})', text)
    if num_match:
        val_str = num_match.group(1).strip().rstrip('/')
        if len(val_str) >= 2:
            unit_match = re.search(r'(°?\s*[CF])', text)
            unit_str = unit_match.group(1) if unit_match else "°C"
            return f"{val_str} {unit_str}".strip()
    return None


def _extract_qty_value(text: str) -> Optional[str]:
    m = re.search(r'(\d+\s*[xX]\s*\d+%|\d+\s*(?:DUTY|STANDBY|INSTALLED)?)', text, re.I)
    return m.group(1).strip() if m else None


_DATASHEET_FIELDS: List[Dict[str, Any]] = [
    {
        'field': 'duty',
        'label_re': re.compile(r'\b(?:DUTY|POWER|RATED\s*POWER|MOTOR\s*POWER)\b', re.I),
        'extract': lambda t: _extract_unit_value(t, r'kW|MW|HP|BHP', r'[\d,.]+', unit_default='kW'),
    },
    {
        'field': 'flow_rate',
        'label_re': re.compile(r'\b(?:FLOW\s*RATE|MASS\s*FLOW|CAPACITY|THROUGHPUT)\b', re.I),
        'extract': lambda t: _extract_unit_value(t, r'kg/h|t/h|m3/h|MMSCFD|Sm3/h|Nm3/h|bbl/d', r'[\d,.\s]+', unit_default='kg/h'),
    },
    {
        'field': 'design_pressure',
        'label_re': re.compile(
            r'\b(?:DESIGN\s*PRESS(?:URE)?|MAWP|MAPD|DESIGN\s*P)\b', re.I),
        'extract': lambda t: _extract_pressure_value(t),
    },
    {
        'field': 'operating_pressure',
        'label_re': re.compile(
            r'\b(?:OPERATING\s*PRESS(?:URE)?|OP\.\s*PRESS|WORKING\s*PRESS(?:URE)?|MOP|MAOP)\b', re.I),
        'extract': lambda t: _extract_pressure_value(t),
    },
    {
        'field': 'design_temperature',
        'label_re': re.compile(
            r'\b(?:DESIGN\s*TEMP(?:ERATURE)?|OPERATING\s*TEMP(?:ERATURE)?|MAX\s*TEMP(?:ERATURE)?|DT)\b',
            re.I),
        'extract': lambda t: _extract_temp_value(t),
    },
    {
        'field': 'material',
        'label_re': re.compile(r'\b(?:MATERIAL(?:\s*OF\s*CONSTRUCTION)?|MOC|METALLURGY)\b', re.I),
        'extract': lambda t: _extract_tail_value(t, r'\b(?:MATERIAL(?:\s*OF\s*CONSTRUCTION)?|MOC|METALLURGY)\b'),
    },
    {
        'field': 'vendor',
        'label_re': re.compile(r'\b(?:VENDOR|MANUFACTURER|SUPPLIER|MFR)\b', re.I),
        'extract': lambda t: _extract_vendor_value(t),
    },
    {
        'field': 'quantity',
        'label_re': re.compile(r'\b(?:QUANTITY|QTY|NO\.\s*OF\s*UNITS|DUTY/STANDBY)\b', re.I),
        'extract': lambda t: _extract_qty_value(t),
    },
    {
        'field': 'service',
        'label_re': re.compile(r'\b(?:SERVICE|FLUID|DESCRIPTION|APPLICATION)\b', re.I),
        'extract': lambda t: _extract_tail_value(t, r'\b(?:SERVICE|FLUID|DESCRIPTION|APPLICATION)\b'),
    },
    {
        'field': 'type',
        'label_re': re.compile(
            r'\b(?:TYPE|MACHINE\s*TYPE|COMPRESSOR\s*TYPE|PUMP\s*TYPE|VESSEL\s*TYPE)\b', re.I),
        'extract': lambda t: _extract_type_value(t),
    },
]

# PSV Set Pressure Pattern
_SP_PATTERN = re.compile(
    r'SP\s*=\s*([\d.,]+\s*(?:bar[\s(g)]*|barg|psig|kPag))',
    re.IGNORECASE
)
_SET_PRESSURE_PATTERN = re.compile(
    r'SET\s*PRESS(?:URE)?\s*[=:]\s*([\d.,]+\s*(?:bar[\s(g)]*|barg|psig|kPag))',
    re.IGNORECASE
)

# Flange ratings near PSV (e.g. 3"x4" 300# 150#)
_FLANGE_SPEC_RE = re.compile(
    r'\b(\d+(?:/\d+)?["\']?)\s*[xX]\s*(\d+(?:/\d+)?["\']?)\s*(?:(\d{3,4}#)\s*(\d{3,4}#)?)?',
    re.IGNORECASE
)


def _get_float_y(item: Dict[str, Any]) -> float:
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
    equip_anchors = [
        item for item in ocr_items
        if item.get('classification') == 'EQUIPMENT_TAG'
    ]

    results: Dict[str, Dict[str, str]] = {}

    for item in ocr_items:
        text = (item.get('text') or item.get('value') or item.get('tag') or '').strip()
        if not text or len(text) < 3:
            continue

        for field_def in _DATASHEET_FIELDS:
            if not field_def['label_re'].search(text):
                continue

            value = field_def['extract'](text)
            if not value or len(value) < 2:
                continue

            item_y = _get_float_y(item)
            if item_y < 0:
                continue

            best_tag: Optional[str] = None
            best_dist = 0.15

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
    psv_anchors = [
        item for item in ocr_items
        if item.get('classification') == 'PSV_TAG'
    ]

    results: Dict[str, str] = {}

    for item in ocr_items:
        text = (item.get('text') or item.get('value') or item.get('tag') or '').strip()
        if not text:
            continue

        val_match = _SP_PATTERN.search(text) or _SET_PRESSURE_PATTERN.search(text)
        if not val_match:
            continue

        sp_value = val_match.group(1).strip()
        sp_value = re.sub(r'\s+', ' ', sp_value).strip()

        sp_value = re.sub(r'bar\s*\(g\)', 'bar(g)', sp_value, flags=re.I)
        sp_value = re.sub(r'barg', 'bar(g)', sp_value, flags=re.I)
        if not re.search(r'\s+bar\(g\)', sp_value):
            sp_value = re.sub(r'bar\(g\)', ' bar(g)', sp_value)

        item_y = _get_float_y(item)

        best_tag: Optional[str] = None
        best_dist = 0.10

        for anchor in psv_anchors:
            anchor_y = _get_float_y(anchor)
            if anchor_y < 0 or item_y < 0:
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

    return results


def parse_psv_flange_specs(
    ocr_items: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """
    Parse PSV inlet/outlet sizes and flange rating classes (e.g., 3"x4" 300# 150#)
    near PSV tags.
    """
    psv_anchors = [
        item for item in ocr_items
        if item.get('classification') == 'PSV_TAG'
    ]

    results: Dict[str, Dict[str, str]] = {}

    for item in ocr_items:
        text = (item.get('text') or item.get('value') or '').strip()
        if not text:
            continue

        m = _FLANGE_SPEC_RE.search(text)
        if not m:
            continue

        inlet_sz = m.group(1).strip()
        outlet_sz = m.group(2).strip()
        inlet_rating = m.group(3).strip() if m.group(3) else "300#"
        outlet_rating = m.group(4).strip() if m.group(4) else "150#"

        item_y = _get_float_y(item)

        best_tag: Optional[str] = None
        best_dist = 0.10

        for anchor in psv_anchors:
            anchor_y = _get_float_y(anchor)
            if anchor_y < 0 or item_y < 0:
                if anchor.get('tag') and anchor['tag'] not in results:
                    best_tag = anchor['tag']
                continue
            dist = abs(item_y - anchor_y)
            if dist < best_dist:
                best_dist = dist
                best_tag = anchor.get('tag')

        if best_tag and best_tag not in results:
            results[best_tag] = {
                'inlet_size': inlet_sz,
                'outlet_size': outlet_sz,
                'inlet_spec': inlet_rating,
                'remarks': f"Flange Rating: {inlet_rating} x {outlet_rating}",
            }
            logger.info(f"PSV flange spec: {best_tag} → {results[best_tag]}")

    return results
