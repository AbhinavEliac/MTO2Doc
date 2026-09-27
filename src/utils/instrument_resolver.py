"""
Instrumentation Resolver & Loop Normalization for SID-AI.

Transforms raw and fragmented instrument OCR detections into structured,
physically coherent instrument loop representations.

Differentiates:
- Primary transmitter / sensor tag
- Indicator representation
- Controller / converter
- Alarms and trip setpoints (HH, LL, H, L)
- Loop ID and unit number

Prevents indicator bubbles, transmitter bubbles, alarms, and OCR fragments from
becoming separate independent physical instrument entities.
"""
from __future__ import annotations

import re
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from src.utils.entity_validator import normalize_instrument_tag

logger = logging.getLogger(__name__)


# Standard measurement classification from first letter of ISA code
_MEASUREMENT_MAP = {
    'P': 'Pressure',
    'PD': 'Differential Pressure',
    'T': 'Temperature',
    'TD': 'Differential Temperature',
    'F': 'Flow',
    'FD': 'Differential Flow',
    'L': 'Level',
    'LD': 'Differential Level',
    'A': 'Analytical',
    'V': 'Vibration',
    'Z': 'Position',
    'S': 'Speed',
    'W': 'Weight',
}

_ISA_TYPE_DESC = {
    'PIT': 'Pressure Indicating Transmitter',
    'PT': 'Pressure Transmitter',
    'PI': 'Pressure Indicator',
    'PDIT': 'Differential Pressure Indicating Transmitter',
    'PDI': 'Differential Pressure Indicator',
    'PDT': 'Differential Pressure Transmitter',
    'TIT': 'Temperature Indicating Transmitter',
    'TT': 'Temperature Transmitter',
    'TI': 'Temperature Indicator',
    'FIT': 'Flow Indicating Transmitter',
    'FT': 'Flow Transmitter',
    'FI': 'Flow Indicator',
    'FE': 'Flow Element',
    'LIT': 'Level Indicating Transmitter',
    'LT': 'Level Transmitter',
    'LI': 'Level Indicator',
    'PY': 'Pressure Relay/Converter',
    'TY': 'Temperature Relay',
    'PSV': 'Pressure Safety Valve',
    'PRV': 'Pressure Relief Valve',
}

# Tokens that are strictly non-instruments (spec codes, materials, table fragments)
_FORBIDDEN_INSTRUMENT_STRINGS = {
    '46-LTCS-1X100', 'OMS-26-CX', 'AT-4', 'FE-9017-NOTE', 'FE-9017-31',
    'DSS-2500-DSS-EL', 'CK-921-OMSMODUL',
}


@dataclass
class AlarmAttribute:
    alarm_type: str  # HH, LL, H, L, SD
    value: Optional[str] = None


@dataclass
class ResolvedInstrument:
    tag: str
    loop_id: str
    measurement: str
    primary_type: str
    indicator_tag: Optional[str] = None
    transmitter_tag: Optional[str] = None
    controller_tag: Optional[str] = None
    element_tag: Optional[str] = None
    alarms: List[AlarmAttribute] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    source_tokens: List[str] = field(default_factory=list)
    confidence: float = 0.90
    coordinates: Optional[List[float]] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


def resolve_instrument_candidates(
    candidates: List[Dict[str, Any]],
) -> Tuple[List[ResolvedInstrument], List[Dict[str, Any]]]:
    """
    Groups raw instrument items by physical loop sequence, resolves primary tags,
    indicators, and alarms, and eliminates synthetic/fragmented duplicates.
    """
    # 1. Filter and normalize items
    cleaned_items = []
    rejected_items = []

    for c in candidates:
        raw_tag = (c.get('tag') or c.get('text') or c.get('value') or '').strip().upper()
        if not raw_tag or raw_tag in _FORBIDDEN_INSTRUMENT_STRINGS:
            rejected_items.append({**c, 'rejection_reason': 'Forbidden string / table fragment'})
            continue

        # Reject strings with words like NOTE, PLEASE, DRAWING, LTCS, OMS
        if any(w in raw_tag for w in ('NOTE', 'LTCS', 'OMS', 'MODUL', 'DRAIN')):
            rejected_items.append({**c, 'rejection_reason': 'Contains non-instrument note/spec word'})
            continue

        norm_tag = normalize_instrument_tag(raw_tag)

        # Extract sequence loop digits (e.g. 9026 from PIT-9026, 0001 from 27-PIT-0001B)
        loop_match = re.search(r'(\d{3,5})([A-Z]?)', norm_tag)
        if not loop_match:
            # Reject bare letters without loop number
            rejected_items.append({**c, 'rejection_reason': 'No valid instrument loop number'})
            continue

        loop_num = loop_match.group(1)
        suffix = loop_match.group(2) or ""

        # Extract unit/area prefix
        area_match = re.match(r'^(\d{2,3})-', norm_tag)
        unit = area_match.group(1) if area_match else ""

        cleaned_items.append({
            'raw': c,
            'raw_tag': raw_tag,
            'norm_tag': norm_tag,
            'unit': unit,
            'loop_num': loop_num,
            'suffix': suffix,
            'loop_key': f"{unit}-{loop_num}{suffix}".lstrip('-'),
            'conf': float(c.get('confidence', 0.90)),
            'coords': c.get('bbox') or c.get('coordinates'),
        })

    # 2. Group by physical loop key (e.g. '26-9026', '9026')
    loops: Dict[str, List[Dict[str, Any]]] = {}
    for item in cleaned_items:
        # Group by loop sequence number
        key = item['loop_num'] + (item['suffix'] if item['suffix'] else "")
        loops.setdefault(key, []).append(item)

    resolved: List[ResolvedInstrument] = []

    for l_key, group in loops.items():
        # Identify unit prefix if any in group has it
        unit = next((it['unit'] for it in group if it['unit']), "26")
        unit_prefix = f"{unit}-" if unit else ""

        # Separate functions present in group: transmitter, indicator, controller, element
        transmitter_tag = None
        indicator_tag = None
        controller_tag = None
        element_tag = None
        all_norm_tags = set()
        all_raw_tags = []
        alarms: List[AlarmAttribute] = []
        best_conf = 0.0
        best_coords = None

        for it in group:
            t = it['norm_tag']
            r = it['raw_tag']
            all_norm_tags.add(t)
            all_raw_tags.append(r)
            if it['conf'] > best_conf:
                best_conf = it['conf']
            if it['coords'] and not best_coords:
                best_coords = it['coords']

            # Check if raw tag carried an alarm token (e.g. PDIT-9015-HH, PI-9026-L)
            alarm_match = re.search(r'[-–](HH|LL|H|L)$', r)
            if alarm_match:
                alarms.append(AlarmAttribute(alarm_type=alarm_match.group(1)))

            # Function classification
            if re.search(r'\b(?:[0-9]+-)?(?:PIT|TIT|FIT|LIT|PDIT|AIT|VIT|ZIT)\b', t):
                transmitter_tag = t
            elif re.search(r'\b(?:[0-9]+-)?(?:PI|TI|FI|LI|PDI|AI|VI|ZI)\b', t):
                indicator_tag = t
            elif re.search(r'\b(?:[0-9]+-)?(?:PIC|TIC|FIC|LIC|PCV|TCV|FCV)\b', t):
                controller_tag = t
            elif re.search(r'\b(?:[0-9]+-)?(?:FE|TE|PE|LE)\b', t):
                element_tag = t

        # Determine primary canonical tag
        # Precedence: Transmitter > Controller > Element > Indicator
        primary = transmitter_tag or controller_tag or element_tag or indicator_tag
        if not primary:
            primary = group[0]['norm_tag']

        # Ensure unit prefix is applied on primary if available
        if unit and not primary.startswith(f"{unit}-"):
            primary = f"{unit}-{primary}"

        # Extract primary type code
        code_match = re.search(r'([A-Z]{2,5})', re.sub(r'^\d{2,3}-', '', primary))
        ptype = code_match.group(1) if code_match else "INST"

        # Measurement classification
        meas = "Process Instrumentation"
        for prefix, m_desc in sorted(_MEASUREMENT_MAP.items(), key=lambda x: -len(x[0])):
            if ptype.startswith(prefix):
                meas = m_desc
                break

        # Calculate calibrated confidence
        # Multi-representation confirmation increases confidence
        rep_count = len(group)
        if rep_count >= 2:
            calibrated_conf = min(0.96, best_conf + 0.05)
        else:
            calibrated_conf = min(0.90, best_conf)

        # Collect aliases (all other tags that mapped into this physical loop)
        aliases = [t for t in all_norm_tags if t != primary]

        res_inst = ResolvedInstrument(
            tag=primary,
            loop_id=l_key,
            measurement=meas,
            primary_type=_ISA_TYPE_DESC.get(ptype, ptype),
            indicator_tag=indicator_tag if indicator_tag != primary else None,
            transmitter_tag=transmitter_tag if transmitter_tag != primary else None,
            controller_tag=controller_tag,
            element_tag=element_tag,
            alarms=alarms,
            aliases=aliases,
            source_tokens=all_raw_tags,
            confidence=round(calibrated_conf, 2),
            coordinates=best_coords,
        )
        resolved.append(res_inst)

        # Mark non-primary items as duplicates for rejection/audit record
        for it in group[1:]:
            rejected_items.append({
                'raw_tag': it['raw_tag'],
                'norm_tag': it['norm_tag'],
                'rejection_reason': f"Consolidated into physical loop entity '{primary}'",
            })

    return resolved, rejected_items
