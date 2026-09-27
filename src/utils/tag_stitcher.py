"""
Spatial Tag Stitcher and OCR Typo Rectifier for Engineering Drawings.

Resolves:
1. Fragmented OCR bounding boxes (e.g., '8"' + 'PV-26-9035' + 'FC11S-08' -> '8"-PV-26-9035-FC11S-08').
2. Split valve tags (e.g., '26-' + 'GB9178' or 'HV-' + '101').
3. Common P&ID OCR typos (e.g., 'B"' -> '8"', 'O' -> '0' in numeric sequences, 'l/2"' -> '1/2"').
4. Angle-aligned bounding box spatial clustering.
"""

from __future__ import annotations

import re
import math
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# Common pipe size patterns
_PIPE_SIZE_PATTERN = re.compile(
    r'^(?:\d+(?:[/\.]\d+)?\s*(?:["\']|IN|MM|DN)|\d+/\d+["\']?|\d+["\'])$',
    re.IGNORECASE
)

# Common spec / insulation codes (e.g. FC11S, FC11S-08, AC21-00, CS150, 150#)
_SPEC_OR_INSULATION_PATTERN = re.compile(
    r'^(?:[A-Z0-9]{2,8}(?:-[A-Z0-9]{1,6})?|[A-Z]{2}\d{2,3}[A-Z0-9]?(?:-[A-Z0-9]{1,4})?|CS\d+|SS\d+|AS\d+|FC\d+|GC\d+|AC\d+|[A-Z]-\d{2}|\d{2})$',
    re.IGNORECASE
)

# Service + System + Sequence core pattern (e.g., PV-26-9035, VA-26-9121, WF-43-9032)
_CORE_LINE_TAG_PATTERN = re.compile(
    r'^[A-Z]{1,4}\s*[-–]\s*(?:\d{2,4}\s*[-–]\s*)?\d{3,5}(?:[A-Z]?)',
    re.IGNORECASE
)

# Valve prefix fragments (e.g., HV, XV, 26-GB, 26CB, EF, QR, GH, KL, ST, CS)
_KNOWN_VALVE_PREFIXES = {
    'HV', 'XV', 'CV', 'PCV', 'FCV', 'TCV', 'LCV', 'MOV', 'SDV', 'BDV', 'FV', 'UV', 'TV',
    'LV', 'AV', 'ZV', 'RV', 'SV', 'DV', 'WV', 'MV', 'BV', 'NV', 'GV', 'BFV', 'PLV',
    'QR', 'GH', 'KL', 'EF', 'ST', 'CS'
}
_VALVE_PREFIX_PATTERN = re.compile(
    r'^(?:\d{2}-?)?(?:HV|XV|CV|PCV|FCV|TCV|LCV|MOV|SDV|BDV|GB|CB|BV|NV|GV|BFV|PLV|QR|GH|KL|EF|ST|CS|V)[-–]?$',
    re.IGNORECASE
)


def rectify_ocr_typos(text: str) -> str:
    """
    Fixes common engineering OCR character misrecognitions in piping, equipment, and valve tags.
    """
    if not text:
        return ""

    cleaned = text.strip()

    # 1. Fix quote/inch mark typos: '' or `` -> "
    cleaned = re.sub(r"['`]{2}", '"', cleaned)

    # 2. Fix pipe size typos like B" -> 8", I" -> 1", l/2" -> 1/2", 3I4" -> 3/4"
    cleaned = re.sub(r'\bB"', '8"', cleaned)
    cleaned = re.sub(r'\bl/2"', '1/2"', cleaned)
    cleaned = re.sub(r'\b3I4"', '3/4"', cleaned)
    cleaned = re.sub(r'\bI"', '1"', cleaned)
    # Fix stray tick stroke before single-digit pipe sizes (e.g. 74" -> 4", 73" -> 3", 72" -> 2", 7"- -> 1"-)
    cleaned = re.sub(r'\b7([23468]")', r'\1', cleaned)
    cleaned = re.sub(r'\b7"-(?=[A-Z])', '1"-', cleaned)
    # Clean leading tilde/quote/apostrophe on pipe sizes: ~4"- -> 4"-, "8"- -> 8"-
    cleaned = re.sub(r'^[~`\'\"]+(\d+(?:[/\.]\d+)?["\'])', r'\1', cleaned)
    # Insert missing hyphen between pipe size and letter code (e.g. 4"TA-4424 -> 4"-TA-4424)
    cleaned = re.sub(r'(\d+(?:[/\.]\d+)?(?:["\']|mm|DN))([A-Z])', r'\1-\2', cleaned)

    # Normalize spaces/dots in line tags into hyphens: e.g. 4" TA 4424 -> 4"-TA-4424, 8" PV 26 9035 -> 8"-PV-26-9035
    cleaned = re.sub(
        r'(\d+(?:[/\.]\d+)?(?:["\']|mm|DN))\s*[-–\s\.]\s*([A-Z]{2,4})\s*[-–\s\.]\s*(\d{3,5})',
        r'\1-\2-\3',
        cleaned, flags=re.IGNORECASE
    )

    # Convert dropped inch marks on known standard pipe sizes (e.g. 4-TA-4424 -> 4"-TA-4424)
    valid_pipe_sizes = {'1/2', '3/4', '1', '2', '3', '4', '6', '8', '10', '12', '14', '16', '18', '20', '24'}
    m = re.match(r'^(\d{1,2})\s*[-–]\s*([A-Z]{2,4})\s*[-–]\s*(\d{3,5})(?:[-–](.+))?$', cleaned, re.IGNORECASE)
    if m and m.group(1) in valid_pipe_sizes:
        size, svc, seq = m.group(1), m.group(2).upper(), m.group(3)
        rest = f"-{m.group(4)}" if m.group(4) else ""
        if svc not in _KNOWN_VALVE_PREFIXES:
            cleaned = f'{size}"-{svc}-{seq}{rest}'

    # 3. Fix en-dashes / em-dashes / long underscores to standard hyphen
    cleaned = re.sub(r'[–—_]+', '-', cleaned)

    # 4. Fix spec code typos: FC115 -> FC11S, GC115 -> GC11S, AS205 -> AS20S
    cleaned = re.sub(r'\b(FC\d{2})5\b', r'\g<1>S', cleaned)
    cleaned = re.sub(r'\b(GC\d{2})5\b', r'\g<1>S', cleaned)
    cleaned = re.sub(r'\b(AS\d{2})5\b', r'\g<1>S', cleaned)
    cleaned = re.sub(r'\b(AC\d{2})5\b', r'\g<1>S', cleaned)

    # 5. Fix dropped decimal points in low pressure ratings: 005BARG -> 0.005 BARG, 005 BARG -> 0.005 BARG
    cleaned = re.sub(r'(?<![\.\d])00(\d+)\s*(BARG|PSIG|BAR)\b', r'0.00\1 \2', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?<![\.\d])0([1-9]\d)\s*(BARG|PSIG|BAR)\b', r'0.\1 \2', cleaned, flags=re.IGNORECASE)

    return cleaned


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely converts string, number, or nested list/tuple element to float without throwing."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple)):
        if len(val) > 0:
            return safe_float(val[0], default)
        return default
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default


def _get_item_box(item: Dict[str, Any]) -> Tuple[float, float, float, float, float, float]:
    """
    Extracts (cx, cy, w, h, xmin, xmax) from OCR item.
    Supports 4-point polygon [[x0, y0], [x1, y1], [x2, y2], [x3, y3]],
    flat [ymin, xmin, ymax, xmax] / [x0, y0, x1, y1], normalized and pixel coordinates.
    """
    attrs = item.get("attributes") or {}
    cx_attr = safe_float(attrs.get("pos_x", item.get("center_x")), -1.0)
    cy_attr = safe_float(attrs.get("pos_y", item.get("center_y")), -1.0)

    # If item has precomputed normalized center coordinates (0.0 .. 1.0), prioritize them
    if 0.0 <= cx_attr <= 1.0 and 0.0 <= cy_attr <= 1.0:
        return cx_attr, cy_attr, 0.05, 0.02, max(0.0, cx_attr - 0.025), min(1.0, cx_attr + 0.025)

    box = item.get("box") or item.get("bbox")
    if box and len(box) >= 4:
        # Case A: 4-point polygon list of [x, y] coordinates
        if isinstance(box[0], (list, tuple)) and len(box[0]) >= 2:
            xs = [safe_float(pt[0]) for pt in box if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            ys = [safe_float(pt[1]) for pt in box if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            if xs and ys:
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                cx = (xmin + xmax) / 2.0
                cy = (ymin + ymax) / 2.0
                w = max(0.001, abs(xmax - xmin))
                h = max(0.001, abs(ymax - ymin))
                if cx > 1.0 or cy > 1.0:
                    scale = max(xmax, ymax, 1000.0)
                    return cx / scale, cy / scale, w / scale, h / scale, xmin / scale, xmax / scale
                return cx, cy, w, h, xmin, xmax
        # Case B: Flat bounding box [ymin, xmin, ymax, xmax] or [x0, y0, x1, y1]
        elif not isinstance(box[0], (list, tuple)):
            v0 = safe_float(box[0])
            v1 = safe_float(box[1])
            v2 = safe_float(box[2])
            v3 = safe_float(box[3])
            ymin, ymax = min(v0, v2), max(v0, v2)
            xmin, xmax = min(v1, v3), max(v1, v3)
            cx = (xmin + xmax) / 2.0
            cy = (ymin + ymax) / 2.0
            w = max(0.001, abs(xmax - xmin))
            h = max(0.001, abs(ymax - ymin))
            if cx > 1.0 or cy > 1.0:
                scale = max(xmax, ymax, 1000.0)
                return cx / scale, cy / scale, w / scale, h / scale, xmin / scale, xmax / scale
            return cx, cy, w, h, xmin, xmax

    cx = cx_attr if cx_attr >= 0 else 0.5
    cy = cy_attr if cy_attr >= 0 else 0.5
    return cx, cy, 0.05, 0.02, cx - 0.025, cx + 0.025


def stitch_fragmented_tags(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Takes a list of raw OCR items and spatially stitches fragmented items
    that form complete LINE_TAGs, VALVE_TAGs, or INSTRUMENT_TAGs.
    """
    if not items:
        return []

    # Clean text first
    processed_items: List[Dict[str, Any]] = []
    for it in items:
        raw_t = it.get("text") or it.get("value") or it.get("tag") or ""
        cleaned_t = rectify_ocr_typos(raw_t)
        if cleaned_t:
            new_it = dict(it)
            new_it["text"] = cleaned_t
            if "value" in new_it:
                new_it["value"] = cleaned_t
            if "tag" in new_it:
                new_it["tag"] = cleaned_t
            processed_items.append(new_it)

    n = len(processed_items)
    merged_indices = set()
    stitched_items: List[Dict[str, Any]] = []

    # Spatial clustering threshold (approx 8-12% of screen width / 3% height in normalized space)
    # or proportionally for pixel space
    for i in range(n):
        if i in merged_indices:
            continue

        item_i = processed_items[i]
        text_i = item_i.get("text", "").strip()
        cx_i, cy_i, w_i, h_i, xmin_i, xmax_i = _get_item_box(item_i)

        # ── 1. Check for split Line Tag fragments (e.g. Size + Core + Spec) ──
        # Candidate 1: item_i is a size prefix (e.g. 8", 3", 1/2", 12mm)
        if _PIPE_SIZE_PATTERN.match(text_i):
            # Look for adjacent core line tag to the right or below
            matched_j = None
            best_dist = 0.09  # Strictly adjacent tokens only (not distant drawing elements)

            for j in range(n):
                if i == j or j in merged_indices:
                    continue
                item_j = processed_items[j]
                text_j = item_j.get("text", "").strip()
                # Exclude valve tags from being falsely stitched as line cores
                code_m = re.match(r'^([A-Z]{2,4})[-–]', text_j, re.IGNORECASE)
                if code_m and code_m.group(1).upper() in _KNOWN_VALVE_PREFIXES:
                    continue

                cx_j, cy_j, w_j, h_j, xmin_j, xmax_j = _get_item_box(item_j)

                # Same horizontal line (cy close) and j is to the right of i
                is_horiz = abs(cy_i - cy_j) < max(0.025, h_i * 1.2) and (0 <= (cx_j - cx_i) < 0.08)
                # Or same vertical column (cx close) and j is below i
                is_vert = abs(cx_i - cx_j) < max(0.025, w_i * 1.2) and (0 <= (cy_j - cy_i) < 0.08)

                if (is_horiz or is_vert) and _CORE_LINE_TAG_PATTERN.search(text_j):
                    dist = math.hypot(cx_j - cx_i, cy_j - cy_i)
                    if dist < best_dist:
                        best_dist = dist
                        matched_j = j

            if matched_j is not None:
                item_j = processed_items[matched_j]
                merged_indices.add(i)
                merged_indices.add(matched_j)

                # Combine size with line tag
                combined_tag = f"{text_i}-{item_j.get('text', '').strip()}".replace('--', '-')
                merged_item = dict(item_j)
                merged_item["text"] = combined_tag
                merged_item["value"] = combined_tag
                merged_item["tag"] = combined_tag
                merged_item["confidence"] = max(item_i.get("confidence", 0.9), item_j.get("confidence", 0.9))

                # Check if there is also an adjacent trailing spec code (e.g. FC11S-08)
                cx_m, cy_m, _, _, _, _ = _get_item_box(merged_item)
                for k in range(n):
                    if k in merged_indices:
                        continue
                    item_k = processed_items[k]
                    text_k = item_k.get("text", "").strip()
                    # Do not stitch valve tags as trailing specs
                    code_k = re.match(r'^([A-Z]{2,4})[-–]', text_k, re.IGNORECASE)
                    if code_k and code_k.group(1).upper() in _KNOWN_VALVE_PREFIXES:
                        continue

                    cx_k, cy_k, _, _, _, _ = _get_item_box(item_k)
                    if abs(cy_m - cy_k) < 0.025 and (0 <= (cx_k - cx_m) < 0.08) and _SPEC_OR_INSULATION_PATTERN.match(text_k):
                        combined_tag = f"{combined_tag}-{text_k}".replace('--', '-')
                        merged_item["text"] = combined_tag
                        merged_item["value"] = combined_tag
                        merged_item["tag"] = combined_tag
                        merged_indices.add(k)
                        break

                stitched_items.append(merged_item)
                continue

        # ── 2. Check for split Valve tags (e.g., 'HV-' + '101' or '26-GB-' + '9178') ──
        if _VALVE_PREFIX_PATTERN.match(text_i):
            matched_j = None
            best_dist = 999.0
            for j in range(n):
                if i == j or j in merged_indices:
                    continue
                item_j = processed_items[j]
                text_j = item_j.get("text", "").strip()
                cx_j, cy_j, _, _, _, _ = _get_item_box(item_j)

                if (abs(cy_i - cy_j) < 0.03 or abs(cx_i - cx_j) < 0.03) and re.match(r'^\d{3,5}[A-Z]?$', text_j):
                    dist = math.hypot(cx_j - cx_i, cy_j - cy_i)
                    if dist < 0.15 and dist < best_dist:
                        best_dist = dist
                        matched_j = j

            if matched_j is not None:
                item_j = processed_items[matched_j]
                merged_indices.add(i)
                merged_indices.add(matched_j)

                sep = "" if text_i.endswith('-') else "-"
                combined_valve = f"{text_i}{sep}{item_j.get('text', '').strip()}"
                merged_item = dict(item_i)
                merged_item["text"] = combined_valve
                merged_item["value"] = combined_valve
                merged_item["tag"] = combined_valve
                stitched_items.append(merged_item)
                continue

        # Otherwise keep original item
        stitched_items.append(item_i)

    # ── 3. Multi-line Bubble & Symbol Stacking (Circles, Squares, Circle-in-Square DCS) ──
    # Combines vertically stacked text {text_above}-{middle_text}-{text_below} inside figures
    stitched_items = stitch_symbol_bubbles(stitched_items)

    logger.debug(f"tag_stitcher: Processed {n} OCR items -> {len(stitched_items)} stitched items.")
    return stitched_items


def stitch_symbol_bubbles(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Stitches multi-line text vertically stacked inside equipment and instrument symbols
    (circles, squares, and circle-in-a-square DCS / PLC combo symbols).
    Captures text above, middle, and below, joining them with hyphens:
      {text_above}-{middle_text}-{text_below}
    to form complete, uniquely identified equipment and instrument tags.
    """
    if not items:
        return []

    # Sort items primarily by X, then Y
    sorted_items = sorted(items, key=lambda it: (round(float(it.get('center_x', 0)), 2), float(it.get('center_y', 0))))
    n = len(sorted_items)
    used = set()
    assembled = []

    for i in range(n):
        if i in used:
            continue
        it1 = sorted_items[i]
        t1 = str(it1.get('text', '')).strip()
        cx1 = float(it1.get('center_x', 0))
        cy1 = float(it1.get('center_y', 0))

        # Skip long notes / descriptions
        if len(t1) > 16 or any(w in t1.upper() for w in ['NOTE', 'PLEASE', 'TOLERANCE', 'DRAWING', 'VALVES', 'CLOSED VESSEL', 'TEMPERATURE', 'ALL FIXTURES']):
            continue

        # Look for tokens vertically stacked with i (same X column within 0.015, Y gap within 0.038)
        group = [i]
        curr_y = cy1
        for j in range(n):
            if j == i or j in used or j in group:
                continue
            it2 = sorted_items[j]
            t2 = str(it2.get('text', '')).strip()
            if len(t2) > 16 or any(w in t2.upper() for w in ['NOTE', 'PLEASE', 'TOLERANCE', 'DRAWING']):
                continue
            cx2 = float(it2.get('center_x', 0))
            cy2 = float(it2.get('center_y', 0))
            
            # Check if j is directly below curr_y within vertical bubble/symbol boundary
            if abs(cx1 - cx2) <= 0.015 and 0.003 <= (cy2 - curr_y) <= 0.038:
                group.append(j)
                curr_y = cy2

        if len(group) >= 2:
            # Sort group vertically from top to bottom
            group.sort(key=lambda idx: float(sorted_items[idx].get('center_y', 0)))
            tokens = [str(sorted_items[idx].get('text', '')).strip() for idx in group]
            
            # Clean tokens: remove leading/trailing noise, quotes, tildes, hyphens
            clean_tokens = []
            for tok in tokens:
                c = re.sub(r'^[~`\'\"#@*_\-\s]+|[~`\'\"#@*_\-\s]+$', '', tok).strip()
                if c:
                    clean_tokens.append(c)

            if len(clean_tokens) >= 2:
                for idx in group:
                    used.add(idx)

                # Assemble with hyphens: {top}-{middle}-{bottom}
                composite_tag = "-".join(clean_tokens)
                
                min_cx = min(float(sorted_items[idx].get('center_x', 0)) for idx in group)
                max_cx = max(float(sorted_items[idx].get('center_x', 0)) for idx in group)
                min_cy = min(float(sorted_items[idx].get('center_y', 0)) for idx in group)
                max_cy = max(float(sorted_items[idx].get('center_y', 0)) for idx in group)
                avg_conf = sum(float(sorted_items[idx].get('confidence', 0.9)) for idx in group) / len(group)

                new_item = {
                    'text': composite_tag,
                    'value': composite_tag,
                    'tag': composite_tag,
                    'confidence': round(avg_conf, 3),
                    'center_x': round((min_cx + max_cx) / 2.0, 4),
                    'center_y': round((min_cy + max_cy) / 2.0, 4),
                    'bbox': [[min_cx, min_cy], [max_cx, min_cy], [max_cx, max_cy], [min_cx, max_cy]],
                    'is_symbol_bubble': True
                }
                assembled.append(new_item)

    return items + assembled
