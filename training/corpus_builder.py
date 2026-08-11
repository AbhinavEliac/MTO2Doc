"""
Strategy C: Full Pipeline Corpus Builder.

Runs the complete SID-AI LangGraph pipeline on every full-page image in the
P&ID augmented dataset and serializes the structured outputs (engineering_graph,
validation_reports, deliverables) to JSON files. The resulting corpus can be
used for model evaluation, training data analysis, or downstream fine-tuning.

Usage:
    python training/train.py corpus --dataset C:/path/to/pid_aug_dataset/claude
    python training/train.py corpus --dataset C:/path/to/pid_aug_dataset/claude --limit 3
"""

import os
import sys
import json
import csv
import logging
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def _serialize_state(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts the final GraphState to a JSON-serializable dict.
    Handles Pydantic models (UniversalEngineeringGraph) via .model_dump().
    """
    result = {}
    for key, value in final_state.items():
        try:
            if hasattr(value, "model_dump"):
                result[key] = value.model_dump()
            elif isinstance(value, (str, int, float, bool, type(None))):
                result[key] = value
            elif isinstance(value, (list, dict)):
                result[key] = value
            else:
                result[key] = str(value)
        except Exception:
            result[key] = f"<non-serializable: {type(value).__name__}>"
    return result


def _extract_quality_metrics(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts extraction quality metrics from a final pipeline state."""
    graph = final_state.get("engineering_graph")
    graph_dump = graph.model_dump() if hasattr(graph, "model_dump") else (graph or {})

    return {
        "equipment_count"   : len(graph_dump.get("equipment", [])),
        "lines_count"       : len(graph_dump.get("lines", [])),
        "instruments_count" : len(graph_dump.get("instruments", [])),
        "valves_count"      : len(graph_dump.get("valves", [])),
        "relationships_count": len(graph_dump.get("relationships", [])),
        "validation_issues" : len(final_state.get("validation_reports", [])),
        "missing_entities"  : len(final_state.get("missing_entities", [])),
        "re_extraction_loops": final_state.get("re_extraction_count", 0),
        "revision_events"   : len(final_state.get("revision_history", [])),
    }


def build_corpus(
    dataset_dir: str,
    limit: Optional[int] = None,
    ocr_engine: str = "paddle",
    reasoning_engine: str = "gemini",
) -> str:
    """
    Main entry: runs the full pipeline on every full-page image in the dataset.
    Saves per-image JSON outputs and a corpus_summary.json.

    Args:
        dataset_dir: Path to dataset root (containing manifest.csv + full_page/)
        limit: Max images to process (for testing)
        ocr_engine: Layer 1 OCR engine ('paddle', 'gemini_ocr', 'llamaparse')
        reasoning_engine: Layer 2 reasoning engine ('gemini', 'rule_based')

    Returns:
        Path to corpus output directory.
    """
    dataset_path  = Path(dataset_dir)
    manifest_path = dataset_path / "manifest.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.csv not found at: {manifest_path}")

    # Output directories
    output_dir = Path(__file__).parent / "outputs" / "corpus"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Import SID-AI workflow
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.graph import create_workflow
    from src.state import GraphState
    from src.config import (
        TEXT_AGENT_MAX_TOKENS, SYMBOL_AGENT_MAX_TOKENS,
        PIPELINE_AGENT_MAX_TOKENS, COMPILER_MAX_TOKENS,
    )

    workflow = create_workflow()
    app = workflow.compile()

    # Read full_page entries from manifest
    full_page_entries = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["type"] == "full_page":
                full_page_entries.append(row)

    if limit:
        full_page_entries = full_page_entries[:limit]

    logger.info(f"=== Pipeline Corpus Builder ===")
    logger.info(f"Dataset     : {dataset_path}")
    logger.info(f"Images      : {len(full_page_entries)} full-page drawings")
    logger.info(f"OCR Engine  : {ocr_engine}")
    logger.info(f"Reasoning   : {reasoning_engine}")
    logger.info(f"Output dir  : {output_dir}")

    corpus_summary = {
        "generated_at"    : datetime.now().isoformat(),
        "dataset_dir"     : str(dataset_path),
        "ocr_engine"      : ocr_engine,
        "reasoning_engine": reasoning_engine,
        "total_images"    : len(full_page_entries),
        "results"         : []
    }
    stats = {"success": 0, "failed": 0, "skipped": 0}

    for i, entry in enumerate(full_page_entries):
        filename = entry["filename"]
        img_path = str(dataset_path / "full_page" / filename)

        if not os.path.exists(img_path):
            logger.warning(f"[{i+1}/{len(full_page_entries)}] Image not found: {img_path} — skipping.")
            stats["skipped"] += 1
            corpus_summary["results"].append({
                "filename": filename, "status": "skipped", "reason": "file_not_found"
            })
            continue

        logger.info(f"\n[{i+1}/{len(full_page_entries)}] Running pipeline on: {filename}")

        # Build initial state
        initial_state: GraphState = {
            "raw_documents"      : [img_path],
            "metadata"           : {},
            "engineering_context": {},
            "extracted_entities" : {
                "text_elements": [], "symbols": [], "relations": [], "geometry": {}
            },
            "engineering_graph"  : None,
            "validation_reports" : [],
            "missing_entities"   : [],
            "revision_history"   : [],
            "deliverables"       : {},
            "re_extraction_count": 0,
            "max_re_extractions" : 2,
            "re_extracted_targets": [],
            "ocr_engine"         : ocr_engine,
            "reasoning_engine"   : reasoning_engine,
            "use_mocks"          : False,
            "local_mode"         : ocr_engine == "paddle",
        }

        try:
            final_state = app.invoke(initial_state)
            quality     = _extract_quality_metrics(final_state)
            serialized  = _serialize_state(final_state)

            # Write per-image JSON
            stem       = Path(filename).stem
            out_path   = output_dir / f"{stem}_output.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({
                    "source_image" : img_path,
                    "quality_metrics": quality,
                    "pipeline_output": serialized,
                }, f, indent=2, ensure_ascii=False)

            logger.info(f"  ✓ Success — Equipment:{quality['equipment_count']} "
                        f"Lines:{quality['lines_count']} "
                        f"Instruments:{quality['instruments_count']} "
                        f"Valves:{quality['valves_count']}")
            stats["success"] += 1

            corpus_summary["results"].append({
                "filename"   : filename,
                "status"     : "success",
                "output_file": str(out_path),
                **quality,
            })

        except Exception as e:
            logger.error(f"  ✗ Pipeline failed for {filename}: {e}")
            logger.debug(traceback.format_exc())
            stats["failed"] += 1
            corpus_summary["results"].append({
                "filename": filename, "status": "failed", "error": str(e)
            })

    # Compute aggregate metrics
    successful = [r for r in corpus_summary["results"] if r["status"] == "success"]
    if successful:
        corpus_summary["aggregate"] = {
            "avg_equipment"   : sum(r["equipment_count"]    for r in successful) / len(successful),
            "avg_lines"       : sum(r["lines_count"]        for r in successful) / len(successful),
            "avg_instruments" : sum(r["instruments_count"]  for r in successful) / len(successful),
            "avg_valves"      : sum(r["valves_count"]       for r in successful) / len(successful),
            "avg_relationships": sum(r["relationships_count"] for r in successful) / len(successful),
            "avg_val_issues"  : sum(r["validation_issues"]  for r in successful) / len(successful),
            "success_rate"    : stats["success"] / len(full_page_entries),
        }

    # Write corpus summary
    summary_path = output_dir / "corpus_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(corpus_summary, f, indent=2, ensure_ascii=False)

    logger.info("\n" + "="*55)
    logger.info("Pipeline Corpus Builder — Summary")
    logger.info("="*55)
    logger.info(f"  Successful    : {stats['success']}")
    logger.info(f"  Failed        : {stats['failed']}")
    logger.info(f"  Skipped       : {stats['skipped']}")
    if successful:
        agg = corpus_summary["aggregate"]
        logger.info(f"  Avg Equipment : {agg['avg_equipment']:.1f}")
        logger.info(f"  Avg Lines     : {agg['avg_lines']:.1f}")
        logger.info(f"  Avg Instruments: {agg['avg_instruments']:.1f}")
        logger.info(f"  Success rate  : {agg['success_rate']*100:.0f}%")
    logger.info(f"  Summary file  : {summary_path}")

    return str(output_dir)
