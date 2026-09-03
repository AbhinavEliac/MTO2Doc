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

# Valve prefix fragments (e.g., HV, XV, 26-GB, 26CB)
_VALVE_PREFIX_PATTERN = re.compile(
    r'^(?:\d{2}-?)?(?:HV|XV|CV|PCV|FCV|TCV|LCV|MOV|SDV|BDV|GB|CB|BV|NV|GV|BFV|PLV|V)[-–]?$',
    re.IGNORECASE
)


def rectify_ocr_typos(text: str) -> str:
    """
    Fixes common engineering OCR character misrecognitions in piping and valve tags.
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
            best_dist = 999.0

            for j in range(n):
                if i == j or j in merged_indices:
                    continue
                item_j = processed_items[j]
                text_j = item_j.get("text", "").strip()
                cx_j, cy_j, w_j, h_j, xmin_j, xmax_j = _get_item_box(item_j)

                # Same horizontal line (cy close) and j is to the right of i
                is_horiz = abs(cy_i - cy_j) < max(0.025, h_i * 1.2) and (0 <= (cx_j - cx_i) < 0.25)
                # Or same vertical column (cx close) and j is below i
                is_vert = abs(cx_i - cx_j) < max(0.025, w_i * 1.2) and (0 <= (cy_j - cy_i) < 0.20)

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
                    cx_k, cy_k, _, _, _, _ = _get_item_box(item_k)
                    if abs(cy_m - cy_k) < 0.025 and (0 <= (cx_k - cx_m) < 0.20) and _SPEC_OR_INSULATION_PATTERN.match(text_k):
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

    logger.debug(f"tag_stitcher: Processed {n} OCR items -> {len(stitched_items)} stitched items.")
    return stitched_items
