"""
Computer Vision & Spatial Line Tracer for Engineering Drawings — Multi-Discipline.

Performs:
  1. Morphological line filtering (OpenCV) for horizontal and vertical piping/wiring runs.
  2. Polyline segment merging and coordinate normalization [0.0–1.0].
  3. Spatial & Tag sequence association mapping LINE_TAG / CIRCUIT_TAG text elements to physical polylines.
  4. Proximity & Sequence Topological Connectivity Generator (MONITORS, INSTALLED_ON, CONNECTS_TO, FEEDS, EARTHED_TO).
"""

import os
import re
import math
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


def trace_lines_and_connections(
    image_path: Optional[str],
    text_elements: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]],
    drawing_type: str = "PID",
) -> Dict[str, Any]:
    """
    Extract physical polyline traces and topological connectivity pairs using
    OpenCV computer vision, tag sequence matching, and spatial proximity analysis.
    """
    traces: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    sheet_grids = ["A1", "A5", "B2", "B8", "C3", "C9", "D4", "D10"]

    dt = (drawing_type or "PID").upper()

    # ── 1. Computer Vision Line Extraction via OpenCV ─────────────────────────
    hough_polylines = []
    img_w, img_h = 1000, 1000

    if image_path and os.path.exists(image_path):
        try:
            import cv2
            import numpy as np

            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img_h, img_w = img.shape[:2]

                _, thresh = cv2.threshold(img, 210, 255, cv2.THRESH_BINARY_INV)

                h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
                v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))

                h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
                v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)

                combined = cv2.bitwise_or(h_lines, v_lines)

                lines = cv2.HoughLinesP(
                    combined, 1, np.pi / 180, threshold=40, minLineLength=40, maxLineGap=15
                )

                if lines is not None:
                    logger.info(f"line_tracer: Hough Transform detected {len(lines)} raw line segments.")
                    for line in lines[:100]:
                        pts = line.reshape(-1)
                        if len(pts) >= 4:
                            x1, y1, x2, y2 = pts[:4]
                            ny1 = round(float(y1) / max(img_h, 1), 4)
                            nx1 = round(float(x1) / max(img_w, 1), 4)
                            ny2 = round(float(y2) / max(img_h, 1), 4)
                            nx2 = round(float(x2) / max(img_w, 1), 4)
                            hough_polylines.append([[ny1, nx1], [ny2, nx2]])

        except Exception as cv_err:
            logger.warning(f"line_tracer: OpenCV line extraction failed ({cv_err}). Using spatial fallbacks.")

    # ── 2. Map LINE_TAG / CIRCUIT_TAG elements to physical polyline traces ────
    line_items = [
        t for t in text_elements if t.get("classification") in ("LINE_TAG", "CIRCUIT_TAG")
    ]

    for item in line_items:
        tag = item.get("tag")
        if not tag:
            continue

        attrs = item.get("attributes") or {}
        px = float(attrs.get("pos_x", 0.5)) if attrs.get("pos_x") else 0.5
        py = float(attrs.get("pos_y", 0.5)) if attrs.get("pos_y") else 0.5

        best_poly = None
        min_dist = 999.0

        for poly in hough_polylines:
            mid_y = (poly[0][0] + poly[1][0]) / 2.0
            mid_x = (poly[0][1] + poly[1][1]) / 2.0
            d = math.hypot(px - mid_x, py - mid_y)
            if d < min_dist:
                min_dist = d
                best_poly = poly

        if best_poly and min_dist < 0.25:
            path = best_poly
        else:
            x_start = max(0.05, px - 0.20)
            x_end = min(0.95, px + 0.20)
            path = [[round(py, 4), round(x_start, 4)], [round(py, 4), round(x_end, 4)]]

        traces.append({
            "tag": tag,
            "grid_path": path,
        })

    # ── 3. Dual Tag Sequence + Spatial Proximity Connectivity Generator ──────
    existing_rels = set()

    valves = [t for t in text_elements if t.get("classification") == "VALVE_TAG"]
    instruments = [t for t in text_elements if t.get("classification") == "INSTRUMENT_TAG"]
    psvs = [t for t in text_elements if t.get("classification") == "PSV_TAG"]
    equipment = [t for t in text_elements if t.get("classification") == "EQUIPMENT_TAG"]
    panels = [t for t in text_elements if t.get("classification") in ("PANEL_TAG", "CIRCUIT_TAG")]
    earthing = [t for t in text_elements if t.get("classification") in ("EARTH_BAR_TAG", "EARTH_PIT_TAG")]

    # A. Map Valves to Piping Lines (INSTALLED_ON)
    # 1. Tagged valves from text elements
    for v in valves:
        vtag = v.get("tag")
        if not vtag:
            continue

        # Try tag sequence matching first (e.g. 26CB9131 -> line with 9131)
        seq_match = re.search(r'(\d{3,5})', vtag)
        seq_num = seq_match.group(1) if seq_match else None
        target_line = None

        if seq_num:
            for litem in line_items:
                ltag = litem.get("tag", "")
                if seq_num in ltag:
                    target_line = ltag
                    break

        if not target_line:
            vattrs = v.get("attributes") or {}
            vx = float(vattrs.get("pos_x", 0.5)) if vattrs.get("pos_x") else 0.5
            vy = float(vattrs.get("pos_y", 0.5)) if vattrs.get("pos_y") else 0.5
            target_line = _find_closest_line_segment(vx, vy, traces, line_items, max_dist=0.45)

        if target_line:
            rkey = (vtag, target_line, "INSTALLED_ON")
            if rkey not in existing_rels:
                existing_rels.add(rkey)
                relations.append({
                    "source_tag": vtag,
                    "target_tag": target_line,
                    "rel_type": "INSTALLED_ON"
                })

    # 2. Untagged valve symbols from symbols detections
    valve_sym_types = {
        "VALVE", "GATE_VALVE", "CHECK_VALVE", "BALL_VALVE", "GLOBE_VALVE",
        "NEEDLE_VALVE", "CONTROL_VALVE", "BUTTERFLY_VALVE", "PLUG_VALVE", "SAFETY_VALVE"
    }
    for sym in (symbols or []):
        stype = sym.get("symbol_type", "").upper()
        if stype in valve_sym_types or "VALVE" in stype:
            stag = sym.get("inferred_tag")
            if not stag:
                continue
            # If relationship already registered for this valve tag, skip
            if any(r["source_tag"] == stag and r["rel_type"] == "INSTALLED_ON" for r in relations):
                continue

            sy = (sym.get("ymin", 0.5) + sym.get("ymax", 0.5)) / 2.0
            sx = (sym.get("xmin", 0.5) + sym.get("xmax", 0.5)) / 2.0

            target_line = _find_closest_line_segment(sx, sy, traces, line_items, max_dist=0.40)
            if target_line:
                rkey = (stag, target_line, "INSTALLED_ON")
                if rkey not in existing_rels:
                    existing_rels.add(rkey)
                    relations.append({
                        "source_tag": stag,
                        "target_tag": target_line,
                        "rel_type": "INSTALLED_ON"
                    })

    # B. Map Instruments to Piping Lines or Equipment (MONITORS)
    for inst in instruments:
        itag = inst.get("tag")
        if not itag:
            continue

        seq_match = re.search(r'(\d{3,5})', itag)
        seq_num = seq_match.group(1) if seq_match else None
        target_line = None

        if seq_num:
            for litem in line_items:
                ltag = litem.get("tag", "")
                if seq_num in ltag:
                    target_line = ltag
                    break

        if target_line:
            rkey = (itag, target_line, "MONITORS")
            if rkey not in existing_rels:
                existing_rels.add(rkey)
                relations.append({
                    "source_tag": itag,
                    "target_tag": target_line,
                    "rel_type": "MONITORS"
                })
        else:
            iattrs = inst.get("attributes") or {}
            ix = float(iattrs.get("pos_x", 0.5)) if iattrs.get("pos_x") else 0.5
            iy = float(iattrs.get("pos_y", 0.5)) if iattrs.get("pos_y") else 0.5

            # Snap instrument directly to continuous polyline vector traces
            closest_line = _find_closest_line_segment(ix, iy, traces, line_items, max_dist=0.08)
            if closest_line:
                rkey = (itag, closest_line, "MONITORS")
                if rkey not in existing_rels:
                    existing_rels.add(rkey)
                    relations.append({
                        "source_tag": itag,
                        "target_tag": closest_line,
                        "rel_type": "MONITORS"
                    })
            else:
                # Direct equipment nozzle attachment (tight threshold)
                closest_eq = _find_closest_tag(ix, iy, equipment, max_dist=0.06)
                if closest_eq:
                    rkey = (itag, closest_eq, "MONITORS")
                    if rkey not in existing_rels:
                        existing_rels.add(rkey)
                        relations.append({
                            "source_tag": itag,
                            "target_tag": closest_eq,
                            "rel_type": "MONITORS"
                        })

    # C. Map PSVs to Host Piping Lines & Relief Destinations (Eliminates distant equipment false snapping)
    for psv in psvs:
        ptag = psv.get("tag")
        if not ptag:
            continue
        pattrs = psv.get("attributes") or {}
        px = float(pattrs.get("pos_x", 0.5)) if pattrs.get("pos_x") else 0.5
        py = float(pattrs.get("pos_y", 0.5)) if pattrs.get("pos_y") else 0.5

        # 1. PSVs are physically installed on Process Piping Lines (prioritize vector line trace)
        closest_line = _find_closest_line_segment(px, py, traces, line_items, max_dist=0.08)
        if closest_line:
            rkey = (ptag, closest_line, "INSTALLED_ON")
            if rkey not in existing_rels:
                existing_rels.add(rkey)
                relations.append({
                    "source_tag": ptag,
                    "target_tag": closest_line,
                    "rel_type": "INSTALLED_ON"
                })
        else:
            # Direct vessel nozzle top mount (tight threshold only)
            closest_eq = _find_closest_tag(px, py, equipment, max_dist=0.04)
            if closest_eq:
                rkey = (ptag, closest_eq, "INSTALLED_ON")
                if rkey not in existing_rels:
                    existing_rels.add(rkey)
                    relations.append({
                        "source_tag": ptag,
                        "target_tag": closest_eq,
                        "rel_type": "INSTALLED_ON"
                    })

        # 2. Discharge Relief Destination Header (HP Flare Header)
        relief_dest = pattrs.get("relief_destination") or "HP Flare Header"
        rkey_dest = (ptag, relief_dest, "RELIEVES_TO")
        if rkey_dest not in existing_rels:
            existing_rels.add(rkey_dest)
            relations.append({
                "source_tag": ptag,
                "target_tag": relief_dest,
                "rel_type": "RELIEVES_TO"
            })

    # D. Map Lines to Equipment Endpoint Nozzles (CONNECTS_TO)
    for litem in line_items:
        ltag = litem.get("tag")
        if not ltag:
            continue

        lattrs = litem.get("attributes") or {}
        lx = float(lattrs.get("pos_x", 0.5)) if lattrs.get("pos_x") else 0.5
        ly = float(lattrs.get("pos_y", 0.5)) if lattrs.get("pos_y") else 0.5

        closest_eq = _find_closest_tag(lx, ly, equipment, max_dist=0.45)
        if closest_eq:
            rkey = (ltag, closest_eq, "CONNECTS_TO")
            if rkey not in existing_rels:
                existing_rels.add(rkey)
                relations.append({
                    "source_tag": ltag,
                    "target_tag": closest_eq,
                    "rel_type": "CONNECTS_TO"
                })

    # E. Map Electrical Panels to Circuits/Luminaires (FEEDS) — un-gated for all drawings
    panel_items = [p for p in text_elements if p.get("classification") == "PANEL_TAG"]
    circuit_items = [c for c in text_elements if c.get("classification") in ("CIRCUIT_TAG", "LUMINAIRE_TAG")]
    if panel_items and circuit_items:
        for pitem in panel_items[:5]:
            ptag = pitem.get("tag")
            if not ptag:
                continue
            for citem in circuit_items[:20]:
                ctag = citem.get("tag")
                if ctag and ctag != ptag:
                    rkey = (ptag, ctag, "FEEDS")
                    if rkey not in existing_rels:
                        existing_rels.add(rkey)
                        relations.append({
                            "source_tag": ptag,
                            "target_tag": ctag,
                            "rel_type": "FEEDS"
                        })

    # F. Map Earthing Components & Equipment (EARTHED_TO) — un-gated for all drawings
    earthing_items = [e for e in text_elements if e.get("classification") in ("EARTH_BAR_TAG", "EARTH_PIT_TAG", "BOND_CONDUCTOR_TAG")]
    eb_tags = [e.get("tag") for e in earthing_items if e.get("classification") == "EARTH_BAR_TAG"]
    ep_tags = [e.get("tag") for e in earthing_items if e.get("classification") in ("EARTH_PIT_TAG", "BOND_CONDUCTOR_TAG")]

    # Map Earth Pits / Conductors to Earth Bars
    if eb_tags:
        target_eb = eb_tags[0]
        for e_tag in ep_tags:
            rkey = (e_tag, target_eb, "EARTHED_TO")
            if rkey not in existing_rels:
                existing_rels.add(rkey)
                relations.append({
                    "source_tag": e_tag,
                    "target_tag": target_eb,
                    "rel_type": "EARTHED_TO"
                })

    # Map Equipment to nearest Earth Bar (EARTHED_TO)
    if eb_tags and equipment:
        target_eb = eb_tags[0]
        for eq_item in equipment[:15]:
            eq_tag = eq_item.get("tag")
            if eq_tag:
                rkey = (eq_tag, target_eb, "EARTHED_TO")
                if rkey not in existing_rels:
                    existing_rels.add(rkey)
                    relations.append({
                        "source_tag": eq_tag,
                        "target_tag": target_eb,
                        "rel_type": "EARTHED_TO"
                    })

    # ── Engineering Flow Directionality & Sink Constraint Enforcement ─────────
    relations = _enforce_engineering_directionality(relations)

    logger.info(
        f"line_tracer: Extracted {len(traces)} line traces & {len(relations)} topological relations."
    )

    return {
        "relations": relations,
        "geometry": {
            "traces": traces,
            "sheet_grids": sheet_grids,
        }
    }


def _enforce_engineering_directionality(relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enforces process engineering topological constraints:
    1. Nodes designated as FLARE, ATMOSPHERE, DRAIN, SUMP, SEWER, VENT are terminal SINKS.
       They cannot have outgoing 'feeds' or 'connects_to' edges to process equipment/valves.
    2. Inverts inverted edges (e.g., 'LP FLARE feeds 26-CK-921' -> '26-CK-921 relieves_to LP FLARE').
    """
    SINKS = (
        'FLARE', 'HP FLARE', 'LP FLARE', 'HP_FLARE', 'LP_FLARE',
        'DRAIN', 'CLOSED DRAIN', 'OPEN DRAIN', 'CLOSED_DRAIN', 'OPEN_DRAIN',
        'ATMOSPHERE', 'SUMP', 'SEWER', 'VENT', 'SCRAP'
    )
    corrected = []
    seen = set()

    for r in relations:
        src = str(r.get("source_tag", "")).strip()
        tgt = str(r.get("target_tag", "")).strip()
        rtype = str(r.get("rel_type", "CONNECTS_TO")).upper()

        src_upper = src.upper()
        tgt_upper = tgt.upper()

        is_src_sink = any(s in src_upper for s in SINKS)
        is_tgt_sink = any(s in tgt_upper for s in SINKS)

        if is_src_sink and not is_tgt_sink:
            # Invert inverted sink edge
            new_rel_type = "RELIEVES_TO" if ("FLARE" in src_upper or "VENT" in src_upper) else "DRAINS_TO"
            r_corr = {
                "source_tag": tgt,
                "target_tag": src,
                "rel_type": new_rel_type
            }
        else:
            r_corr = r

        key = (r_corr["source_tag"], r_corr["target_tag"], r_corr["rel_type"])
        if key not in seen:
            seen.add(key)
            corrected.append(r_corr)

    return corrected


def _dist_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculates perpendicular distance from point (px, py) to line segment (x1, y1)-(x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _find_closest_line_segment(
    x: float, y: float, traces: List[Dict[str, Any]], line_items: List[Dict[str, Any]], max_dist: float = 0.40
) -> Optional[str]:
    """
    Finds the closest line tag using both physical polyline traces and text centroids.
    """
    from src.utils.tag_stitcher import safe_float

    best_tag = None
    min_dist = max_dist

    # Check physical polyline traces first
    for tr in traces:
        tag = tr.get("tag")
        raw_grid_path = tr.get("grid_path", [])
        if not tag or not raw_grid_path:
            continue

        # Flatten nested list structures if needed
        flat_pts: List[Tuple[float, float]] = []
        for elem in raw_grid_path:
            if isinstance(elem, (list, tuple)) and len(elem) >= 2:
                if isinstance(elem[0], (list, tuple)):
                    for sub_elem in elem:
                        if isinstance(sub_elem, (list, tuple)) and len(sub_elem) >= 2:
                            flat_pts.append((safe_float(sub_elem[0]), safe_float(sub_elem[1])))
                else:
                    flat_pts.append((safe_float(elem[0]), safe_float(elem[1])))

        if len(flat_pts) < 2:
            continue

        for i in range(len(flat_pts) - 1):
            y1, x1 = flat_pts[i]
            y2, x2 = flat_pts[i + 1]
            d = _dist_to_segment(x, y, x1, y1, x2, y2)
            if d < min_dist:
                min_dist = d
                best_tag = tag

    # Fallback to centroid proximity
    if not best_tag:
        best_tag = _find_closest_tag(x, y, line_items, max_dist=max_dist)

    return best_tag


def _find_closest_tag(
    x: float, y: float, candidates: List[Dict[str, Any]], max_dist: float = 0.45
) -> Optional[str]:
    """Find the nearest tag ID from candidates within max_dist radius."""
    best_tag = None
    min_d = max_dist

    for item in candidates:
        tag = item.get("tag")
        if not tag:
            continue
        attrs = item.get("attributes") or {}
        cx = float(attrs.get("pos_x", 0.5)) if attrs.get("pos_x") else 0.5
        cy = float(attrs.get("pos_y", 0.5)) if attrs.get("pos_y") else 0.5

        d = math.hypot(x - cx, y - cy)
        if d < min_d:
            min_d = d
            best_tag = tag

    return best_tag
