"""
Annotation Reconstruction & Region Segmentation for SID-AI.

Transforms fragmented token-level OCR into coherent, structured AnnotationRegion objects.
Preserves raw tokens, normalized text, bounding boxes, and categorizes annotations:
- EQUIPMENT_DESCRIPTION (e.g. '3RD STAGE HP GAS EXPORT COMPRESSOR')
- PROCESS_DESCRIPTION (e.g. 'LUBE OIL RESERVOIR VENT OIL MIST SEPARATOR')
- FLARE_DESTINATION (e.g. 'TO HP FLARE')
- NOTE / REFERENCE / DRAWING_METADATA
"""
from __future__ import annotations

import re
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AnnotationRegion:
    annotation_id: str
    raw_tokens: List[str] = field(default_factory=list)
    raw_text: str = ""
    normalized_text: str = ""
    bbox: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])  # [ymin, xmin, ymax, xmax]
    page: int = 1
    annotation_type: str = "NOTE"
    confidence: float = 0.90


def classify_annotation_type(text: str) -> str:
    """Classifies reconstructed annotation text into engineering categories."""
    t_up = text.upper()
    if re.search(r'\b(?:TO\s+HP\s+FLARE|TO\s+LP\s+FLARE|HP\s+FLARE|LP\s+FLARE|FLARE\s+HEADER)\b', t_up):
        return "FLARE_DESTINATION"
    if re.search(r'\b(?:COMPRESSOR|TURBINE|SEPARATOR|PUMP|EXCHANGER|COOLER|VESSEL|SCRUBBER|SKID)\b', t_up):
        return "EQUIPMENT_DESCRIPTION"
    if re.search(r'\b(?:LUBE\s+OIL|SEAL\s+GAS|CLOSED\s+DRAIN|OPEN\s+DRAIN|FUEL\s+GAS|COOLING\s+WATER|INSTRUMENT\s+AIR)\b', t_up):
        return "PROCESS_DESCRIPTION"
    if re.search(r'\b(?:NOTE\s*\d*|NOTES|HOLD|IMPORTANT|CAUTION|WARNING)\b', t_up):
        return "NOTE"
    if re.search(r'\b(?:FROM|TO|SEE\s+DWG|REF\s+DWG|CONTINUED\s+ON|TIE-IN)\b', t_up):
        return "REFERENCE"
    return "GENERAL_NOTE"


def reconstruct_annotation_regions(
    ocr_items: List[Dict[str, Any]],
    page: int = 1,
) -> List[AnnotationRegion]:
    """
    Groups fragmented OCR tokens into coherent annotation regions using
    spatial geometry and reading order.
    """
    # Select text items that are not already classified as tags
    note_items = []
    for it in ocr_items:
        cls = it.get('classification')
        txt = (it.get('text') or it.get('value') or '').strip()
        if not txt or len(txt) < 2:
            continue
        # Exclude recognized tags from being absorbed into annotation regions
        if cls in ('EQUIPMENT_TAG', 'LINE_TAG', 'VALVE_TAG', 'PSV_TAG'):
            continue

        cy = float(it.get('center_y', 0.5))
        cx = float(it.get('center_x', 0.5))
        note_items.append({
            'text': txt,
            'cx': cx,
            'cy': cy,
            'conf': float(it.get('confidence', 0.90)),
        })

    if not note_items:
        return []

    # Sort primarily top-to-bottom, then left-to-right
    sorted_items = sorted(note_items, key=lambda x: (round(x['cy'], 2), round(x['cx'], 2)))
    used = set()
    regions: List[AnnotationRegion] = []
    region_counter = 1

    for i, item_i in enumerate(sorted_items):
        if i in used:
            continue

        cluster = [i]
        curr_y = item_i['cy']
        curr_x = item_i['cx']

        # Cluster tokens that are vertically adjacent (lines of a multi-line note)
        # or horizontally adjacent (same line words)
        for j, item_j in enumerate(sorted_items):
            if j == i or j in used or j in cluster:
                continue

            jx = item_j['cx']
            jy = item_j['cy']

            # Case A: Same line (horizontal continuation)
            is_same_line = abs(curr_y - jy) <= 0.012 and 0.0 < (jx - curr_x) <= 0.15
            # Case B: Next line down in same column (vertical paragraph/callout)
            is_next_line = abs(curr_x - jx) <= 0.08 and 0.005 <= (jy - curr_y) <= 0.035

            if is_same_line or is_next_line:
                cluster.append(j)
                curr_y = jy
                curr_x = jx

        # If cluster formed
        if cluster:
            for idx in cluster:
                used.add(idx)

            # Sort cluster in reading order (top-to-bottom, left-to-right)
            cluster_sorted = sorted(cluster, key=lambda idx: (round(sorted_items[idx]['cy'], 3), sorted_items[idx]['cx']))
            tokens = [sorted_items[idx]['text'] for idx in cluster_sorted]
            raw_text = " ".join(tokens)
            norm_text = re.sub(r'\s+', ' ', raw_text).strip()

            min_x = min(sorted_items[idx]['cx'] for idx in cluster)
            max_x = max(sorted_items[idx]['cx'] for idx in cluster)
            min_y = min(sorted_items[idx]['cy'] for idx in cluster)
            max_y = max(sorted_items[idx]['cy'] for idx in cluster)
            avg_conf = sum(sorted_items[idx]['conf'] for idx in cluster) / len(cluster)

            atype = classify_annotation_type(norm_text)

            regions.append(AnnotationRegion(
                annotation_id=f"ann_{region_counter:04d}",
                raw_tokens=tokens,
                raw_text=raw_text,
                normalized_text=norm_text,
                bbox=[min_y, min_x, max_y, max_x],
                page=page,
                annotation_type=atype,
                confidence=round(avg_conf, 2),
            ))
            region_counter += 1

    return regions
