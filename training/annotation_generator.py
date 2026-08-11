"""
Strategy B — Part 1: Object Detection Annotation Generator.

Runs SymbolRecognitionAgent on each patch image to extract ISA-5.1 symbol
bounding boxes, then converts them to:
  1. YOLO v8 .txt format  (one file per patch image)
  2. COCO JSON format     (single merged annotations file)
  3. data.yaml            (YOLOv8 dataset config)

Usage:
    python training/train.py annotate --dataset C:/path/to/pid_aug_dataset/claude
    python training/train.py annotate --dataset C:/path/to/pid_aug_dataset/claude --limit 10
"""

import os
import sys
import json
import shutil
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ISA-5.1 Symbol class labels (used as YOLO class IDs)
SYMBOL_CLASSES = [
    "INST_BUBBLE",        # 0 — Instrument circles (PI, TI, FI, etc.)
    "COMPRESSOR",         # 1
    "MOTOR",              # 2
    "COOLER",             # 3
    "FILTER",             # 4
    "VESSEL",             # 5
    "PUMP",               # 6
    "HEAT_EXCHANGER",     # 7
    "GLOBE_VALVE",        # 8
    "GATE_VALVE",         # 9
    "CHECK_VALVE",        # 10
    "BALL_VALVE",         # 11
    "CONTROL_VALVE",      # 12
    "NEEDLE_VALVE",       # 13
    "BUTTERFLY_VALVE",    # 14
    "SAFETY_VALVE",       # 15
    "PSV",                # 16
    "STRAINER",           # 17
    "REDUCER",            # 18
    "NOZZLE",             # 19
    "SPECTACLE_BLIND",    # 20
    "TEE",                # 21
    "FLANGE",             # 22
    "SKID",               # 23
    "COALESCER",          # 24
    "SEPARATOR",          # 25
]

CLASS_TO_ID = {cls: i for i, cls in enumerate(SYMBOL_CLASSES)}


def _run_symbol_recognition(
    image_path: str,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Runs SymbolRecognitionAgent on a patch image.
    Returns list of symbol dicts with keys: symbol_type, ymin, xmin, ymax, xmax, inferred_tag.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.agents.parallel_vision import SymbolRecognitionAgent
        from src.state import GraphState

        agent = SymbolRecognitionAgent()
        state: GraphState = {
            "raw_documents": [image_path],
            "metadata": {"drawing_type": "PID", "rasterized_pages": [image_path]},
            "engineering_context": {},
            "extracted_entities": {"text_elements": [], "symbols": [], "relations": [], "geometry": {}},
            "engineering_graph": None,
            "validation_reports": [],
            "missing_entities": [],
            "revision_history": [],
            "deliverables": {},
            "re_extraction_count": 0,
            "max_re_extractions": 1,
            "re_extracted_targets": [],
            "symbol_engine": "vlm",
            "llm_provider": provider,
            "llm_model": model_name,
            "use_mocks": False,
            "local_mode": False,
        }
        result = agent.run(state)
        return result.get("extracted_entities", {}).get("symbols", [])
    except Exception as e:
        logger.error(f"Symbol recognition failed for {os.path.basename(image_path)}: {e}")
        return []


def _normalize_class(symbol_type: str) -> int:
    """Maps detected symbol type string to YOLO class ID."""
    sym_upper = symbol_type.upper().strip()
    # Direct match
    if sym_upper in CLASS_TO_ID:
        return CLASS_TO_ID[sym_upper]
    # Partial match
    for cls, idx in CLASS_TO_ID.items():
        if cls in sym_upper or sym_upper in cls:
            return idx
    # Fallback: INST_BUBBLE for unknown circular symbols
    logger.debug(f"Unknown symbol type '{symbol_type}' — mapping to INST_BUBBLE (0).")
    return 0


def _convert_to_yolo(symbols: List[Dict[str, Any]], img_w: int = 1000, img_h: int = 800) -> List[str]:
    """
    Converts normalized [ymin, xmin, ymax, xmax] bboxes to YOLO format:
    <class_id> <x_center> <y_center> <width> <height>   (all normalized 0-1)
    """
    lines = []
    for sym in symbols:
        ymin = float(sym.get("ymin", 0))
        xmin = float(sym.get("xmin", 0))
        ymax = float(sym.get("ymax", 1))
        xmax = float(sym.get("xmax", 1))

        # Skip degenerate boxes
        if xmax <= xmin or ymax <= ymin:
            continue
        if xmin < 0 or ymin < 0 or xmax > 1 or ymax > 1:
            # Clamp to [0, 1]
            xmin, ymin = max(0.0, xmin), max(0.0, ymin)
            xmax, ymax = min(1.0, xmax), min(1.0, ymax)

        x_center = (xmin + xmax) / 2
        y_center = (ymin + ymax) / 2
        width    = xmax - xmin
        height   = ymax - ymin

        class_id = _normalize_class(sym.get("symbol_type", "INST_BUBBLE"))
        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
    return lines


def generate_annotations(
    dataset_dir: str,
    limit: Optional[int] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Tuple[str, str]:

    """
    Main entry: generates YOLO .txt annotations and COCO JSON for all patches.

    Returns:
        Tuple of (annotations_dir, coco_json_path)
    """
    dataset_path = Path(dataset_dir)
    patches_dir  = dataset_path / "patches"
    manifest_path = dataset_path / "manifest.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.csv not found at: {manifest_path}")

    # Output directories
    output_dir   = Path(__file__).parent / "outputs"
    ann_dir      = output_dir / "annotations"
    images_train = ann_dir / "images" / "train"
    labels_train = ann_dir / "labels" / "train"
    images_val   = ann_dir / "images" / "val"
    labels_val   = ann_dir / "labels" / "val"

    for d in [images_train, labels_train, images_val, labels_val]:
        d.mkdir(parents=True, exist_ok=True)

    # Read only patch entries from manifest
    patch_entries = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["type"] == "patch":
                patch_entries.append(row)

    if limit:
        patch_entries = patch_entries[:limit]

    logger.info(f"=== Annotation Generator ===")
    logger.info(f"Patches to annotate: {len(patch_entries)}")

    # 80/20 train/val split
    split_idx = int(len(patch_entries) * 0.8)
    train_entries = patch_entries[:split_idx]
    val_entries   = patch_entries[split_idx:]

    coco_annotations = {
        "info": {"description": "SID-AI P&ID Symbol Detection Dataset", "version": "1.0"},
        "categories": [{"id": i, "name": cls} for i, cls in enumerate(SYMBOL_CLASSES)],
        "images": [],
        "annotations": []
    }
    ann_id = 0
    stats  = {"processed": 0, "skipped_empty": 0, "failed": 0, "total_symbols": 0}

    def _process_entry(entry: Dict, split: str, img_id: int):
        nonlocal ann_id
        filename = entry["filename"]
        img_path = str(patches_dir / filename)
        stem     = Path(filename).stem

        if not os.path.exists(img_path):
            logger.warning(f"Patch image not found: {img_path} — skipping.")
            stats["failed"] += 1
            return

        logger.info(f"  Annotating [{split}]: {filename} ...")
        stats["processed"] += 1

        # Run symbol recognition
        symbols = _run_symbol_recognition(img_path, provider=provider, model_name=model_name)
        if not symbols:
            logger.warning(f"  No symbols detected in {filename} — writing empty label file.")
            stats["skipped_empty"] += 1

        # Determine output dirs
        img_out_dir = images_train if split == "train" else images_val
        lbl_out_dir = labels_train if split == "train" else labels_val

        # Copy image
        shutil.copy2(img_path, img_out_dir / filename)

        # Write YOLO .txt
        yolo_lines = _convert_to_yolo(symbols)
        lbl_path = lbl_out_dir / (stem + ".txt")
        with open(lbl_path, "w") as f:
            f.write("\n".join(yolo_lines))

        # Add COCO image entry
        coco_annotations["images"].append({
            "id": img_id, "file_name": filename,
            "width": int(entry.get("width", 1000)),
            "height": int(entry.get("height", 800))
        })

        # Add COCO annotations
        for sym in symbols:
            class_id = _normalize_class(sym.get("symbol_type", "INST_BUBBLE"))
            ymin, xmin = float(sym.get("ymin", 0)), float(sym.get("xmin", 0))
            ymax, xmax = float(sym.get("ymax", 1)), float(sym.get("xmax", 1))
            # COCO bbox: [x, y, width, height] in absolute pixels
            w_img = int(entry.get("width", 1000))
            h_img = int(entry.get("height", 800))
            x_abs = xmin * w_img
            y_abs = ymin * h_img
            w_abs = (xmax - xmin) * w_img
            h_abs = (ymax - ymin) * h_img
            coco_annotations["annotations"].append({
                "id": ann_id, "image_id": img_id,
                "category_id": class_id,
                "bbox": [round(x_abs, 2), round(y_abs, 2), round(w_abs, 2), round(h_abs, 2)],
                "area": round(w_abs * h_abs, 2),
                "iscrowd": 0
            })
            ann_id += 1
            stats["total_symbols"] += 1

    for img_id, entry in enumerate(train_entries):
        _process_entry(entry, "train", img_id)
    for img_id, entry in enumerate(val_entries, start=len(train_entries)):
        _process_entry(entry, "val", img_id)

    # Write COCO JSON
    coco_path = ann_dir / "coco_annotations.json"
    with open(coco_path, "w", encoding="utf-8") as f:
        json.dump(coco_annotations, f, indent=2, ensure_ascii=False)

    # Write YOLOv8 data.yaml
    yaml_path = ann_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        f.write(f"path: {ann_dir.resolve()}\n")
        f.write(f"train: images/train\n")
        f.write(f"val: images/val\n")
        f.write(f"nc: {len(SYMBOL_CLASSES)}\n")
        f.write(f"names: {SYMBOL_CLASSES}\n")

    # Summary
    logger.info("\n" + "="*55)
    logger.info("Annotation Generator — Summary")
    logger.info("="*55)
    logger.info(f"  Train patches   : {len(train_entries)}")
    logger.info(f"  Val patches     : {len(val_entries)}")
    logger.info(f"  Total symbols   : {stats['total_symbols']}")
    logger.info(f"  Empty patches   : {stats['skipped_empty']}")
    logger.info(f"  Failed          : {stats['failed']}")
    logger.info(f"  COCO JSON       : {coco_path}")
    logger.info(f"  YOLO data.yaml  : {yaml_path}")

    return str(ann_dir), str(coco_path)
