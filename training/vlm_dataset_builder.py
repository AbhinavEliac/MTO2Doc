"""
Strategy A: VLM Fine-tuning Dataset Builder (Gemini Supervised Fine-tuning Format).

Generates a JSONL dataset of (system, user_with_image, model_answer) triplets
from every image in the P&ID augmented dataset. Output is ready for upload to
the Gemini Supervised Fine-tuning API.

Usage:
    python training/train.py vlm --dataset C:/path/to/pid_aug_dataset/claude
    python training/train.py vlm --dataset C:/path/to/pid_aug_dataset/claude --limit 5
"""

import os
import sys
import json
import base64
import logging
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Gemini SFT JSONL format ────────────────────────────────────────────────────
#
# Each line in the output JSONL follows Gemini's supervised fine-tuning format:
# {
#   "messages": [
#     {"role": "system", "content": "<system_prompt>"},
#     {"role": "user",  "content": [
#         {"type": "text",      "text": "<user_prompt>"},
#         {"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}
#     ]},
#     {"role": "model", "content": "<json_answer_string>"}
#   ]
# }

SYSTEM_PROMPT_FULL = (
    "You are SID-AI, an expert engineering drawing analysis system specialized in "
    "P&ID (Piping and Instrumentation Diagram) interpretation per ISA-5.1 standards. "
    "Given a full-page P&ID drawing image, extract ALL engineering entities: "
    "equipment tags, line tags, instrument tags, valve tags, PSV tags, notes, and ratings. "
    "Return a structured JSON object with an 'items' array. Each item must have: "
    "tag, classification, value, and optional attributes dict."
)

SYSTEM_PROMPT_PATCH = (
    "You are SID-AI, an expert engineering drawing analysis system specialized in "
    "P&ID (Piping and Instrumentation Diagram) interpretation per ISA-5.1 standards. "
    "Given a cropped patch from a P&ID drawing, extract ALL visible engineering entities "
    "including instrument bubbles, valve symbols, piping line tags, and equipment labels. "
    "Return a structured JSON object with an 'items' array. Each item must have: "
    "tag, classification, value, and optional attributes dict."
)

USER_PROMPT_FULL = (
    "Analyze this full P&ID drawing and extract every engineering entity you can identify. "
    "Include: EQUIPMENT_TAG, LINE_TAG, INSTRUMENT_TAG, VALVE_TAG, PSV_TAG, NOTE, RATING. "
    "For each entity, provide its exact tag string, classification, and any specifications "
    "(design_pressure, design_temperature, flow_rate, material, vendor) in the attributes field."
)

USER_PROMPT_PATCH = (
    "Analyze this cropped patch from a P&ID drawing and extract all visible engineering entities. "
    "Focus on instrument bubbles (PI, TI, FI, PDIT, PDI), valve symbols, line tags, and equipment labels. "
    "Return a JSON object with an 'items' array containing each detected entity."
)


def _encode_image_base64(image_path: str, max_dim: int = 1024) -> str:
    """Encode image as base64, downscaling large images to reduce JSONL size."""
    try:
        from PIL import Image
        import io
        with Image.open(image_path) as img:
            w, h = img.size
            if max(w, h) > max_dim:
                ratio = max_dim / float(max(w, h))
                new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


def _run_pipeline_on_image(image_path: str, image_type: str) -> Optional[Dict[str, Any]]:
    """
    Runs the SID-AI text extraction pipeline on a single image to generate
    the ground-truth answer for the training sample.
    Returns extracted entities dict or None on failure.
    """
    try:
        # Import pipeline components
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.agents.parallel_vision import TextRecognitionAgent
        from src.state import GraphState

        agent = TextRecognitionAgent()
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
            "ocr_engine": "paddle",
            "reasoning_engine": "gemini",
            "use_mocks": False,
            "local_mode": False,
        }
        result = agent.run(state)
        text_elements = result.get("extracted_entities", {}).get("text_elements", [])
        if len(text_elements) < 3:
            logger.warning(f"Low yield ({len(text_elements)} entities) for {os.path.basename(image_path)} — skipping.")
            return None
        return {"items": text_elements}
    except Exception as e:
        logger.error(f"Pipeline extraction failed for {os.path.basename(image_path)}: {e}")
        return None


def _build_gemini_sft_record(
    image_path: str,
    image_type: str,
    extracted_answer: Dict[str, Any],
    patch_coords: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds a single Gemini SFT JSONL record.
    Full-page images are downscaled to 1024px max; patches keep 1000×800.
    """
    max_dim = 1024 if image_type == "full_page" else 1000
    b64_image = _encode_image_base64(image_path, max_dim=max_dim)

    system_prompt = SYSTEM_PROMPT_FULL if image_type == "full_page" else SYSTEM_PROMPT_PATCH
    user_prompt   = USER_PROMPT_FULL   if image_type == "full_page" else USER_PROMPT_PATCH

    if patch_coords:
        user_prompt += f"\n\nNote: This patch originates from coordinates {patch_coords} in the full drawing."

    return {
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                    }
                ]
            },
            {
                "role": "model",
                "content": json.dumps(extracted_answer, ensure_ascii=False)
            }
        ]
    }


def build_vlm_dataset(dataset_dir: str, limit: Optional[int] = None) -> str:
    """
    Main entry point: reads manifest.csv, runs pipeline on each image,
    and writes Gemini SFT JSONL to training/outputs/vlm_finetune_gemini.jsonl.

    Args:
        dataset_dir: Path to the dataset root (containing manifest.csv)
        limit: Optional max number of images to process (for testing)

    Returns:
        Path to generated JSONL file.
    """
    dataset_path = Path(dataset_dir)
    manifest_path = dataset_path / "manifest.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.csv not found at: {manifest_path}")

    # Output directory
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "vlm_finetune_gemini.jsonl"

    logger.info(f"=== VLM Fine-tuning Dataset Builder (Gemini SFT Format) ===")
    logger.info(f"Dataset: {dataset_path}")
    logger.info(f"Output:  {output_path}")

    # Read manifest
    entries = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)

    if limit:
        entries = entries[:limit]
        logger.info(f"Limit mode: processing {limit}/{len(entries)} images.")

    stats = {"processed": 0, "skipped_low_yield": 0, "failed": 0, "written": 0}

    with open(output_path, "w", encoding="utf-8") as out_f:
        for i, entry in enumerate(entries):
            img_type = entry["type"]  # "full_page" or "patch"
            filename = entry["filename"]

            # Resolve absolute path
            if img_type == "full_page":
                img_path = str(dataset_path / "full_page" / filename)
            else:
                img_path = str(dataset_path / "patches" / filename)

            if not os.path.exists(img_path):
                logger.warning(f"[{i+1}/{len(entries)}] Image not found: {img_path} — skipping.")
                stats["failed"] += 1
                continue

            logger.info(f"[{i+1}/{len(entries)}] Processing {img_type}: {filename} ...")
            stats["processed"] += 1

            # Extract patch coordinates from filename (patch_NNN_xX_yY.png)
            patch_coords = None
            if img_type == "patch":
                parts = filename.replace(".png", "").split("_")
                coords_parts = [p for p in parts if p.startswith("x") or p.startswith("y")]
                if len(coords_parts) >= 2:
                    patch_coords = f"({coords_parts[0][1:]}, {coords_parts[1][1:]})"

            # Run pipeline to generate ground-truth answer
            answer = _run_pipeline_on_image(img_path, img_type)
            if answer is None:
                stats["skipped_low_yield"] += 1
                continue

            # Build and write Gemini SFT record
            try:
                record = _build_gemini_sft_record(img_path, img_type, answer, patch_coords)
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                stats["written"] += 1
                logger.info(f"  ✓ Written record with {len(answer.get('items', []))} entities.")
            except Exception as e:
                logger.error(f"  ✗ Failed to build record for {filename}: {e}")
                stats["failed"] += 1

    # Summary
    logger.info("\n" + "="*55)
    logger.info("VLM Dataset Builder — Summary")
    logger.info("="*55)
    logger.info(f"  Total processed :  {stats['processed']}")
    logger.info(f"  Written records :  {stats['written']}")
    logger.info(f"  Skipped (low yield): {stats['skipped_low_yield']}")
    logger.info(f"  Failed          :  {stats['failed']}")
    logger.info(f"  Output file     :  {output_path}")
    logger.info(f"\n  → Upload to Gemini SFT API at:")
    logger.info(f"    https://console.cloud.google.com/vertex-ai/generative/language/tuning")

    return str(output_path)
