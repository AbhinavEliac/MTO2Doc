"""
SID-AI Training CLI — Master Entry Point.

Subcommands:
    vlm      — Strategy A: Generate Gemini SFT JSONL dataset from all images
    annotate — Strategy B Step 1: Generate YOLO + COCO annotations from patches
    yolo     — Strategy B Step 2: Launch YOLOv8 training on RTX 3050
    corpus   — Strategy C: Run full pipeline on all images, build training corpus

Usage Examples:
    # Generate Gemini SFT fine-tuning dataset (all images)
    python training/train.py vlm --dataset C:/Users/ADMIN/Downloads/pid_aug_dataset/claude

    # Generate only 5 samples (test run)
    python training/train.py vlm --dataset C:/path/to/dataset --limit 5

    # Generate YOLO bounding box annotations from patches
    python training/train.py annotate --dataset C:/path/to/dataset

    # Launch YOLOv8 training on RTX 3050 (run annotate first)
    python training/train.py yolo --annotations training/outputs/annotations --epochs 100

    # Build full pipeline corpus (run full pipeline on all full-page images)
    python training/train.py corpus --dataset C:/path/to/dataset --ocr-engine paddle

    # Full run: annotate + yolo in sequence
    python training/train.py annotate --dataset C:/path/to/dataset
    python training/train.py yolo --annotations training/outputs/annotations
"""

import argparse
import logging
import sys
import os
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Logging Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("sid_ai.training")


def cmd_vlm(args):
    """Strategy A: Generate Gemini SFT JSONL dataset."""
    logger.info("Starting Strategy A: VLM Fine-tuning Dataset Builder")
    logger.info(f"  Dataset : {args.dataset}")
    logger.info(f"  Limit   : {args.limit or 'all'}")
    
    from training.vlm_dataset_builder import build_vlm_dataset
    output_path = build_vlm_dataset(
        dataset_dir=args.dataset,
        limit=args.limit,
    )
    logger.info(f"\n✅ VLM dataset ready: {output_path}")
    logger.info("   → Upload to Gemini SFT: https://console.cloud.google.com/vertex-ai/generative/language/tuning")


def cmd_annotate(args):
    """Strategy B Step 1: Generate YOLO + COCO annotations."""
    logger.info("Starting Strategy B-1: Object Detection Annotation Generator")
    logger.info(f"  Dataset  : {args.dataset}")
    logger.info(f"  Provider : {args.provider or 'default (gemini)'}")
    logger.info(f"  Model    : {args.model or 'default'}")
    logger.info(f"  Limit    : {args.limit or 'all'}")
    
    from training.annotation_generator import generate_annotations
    ann_dir, coco_path = generate_annotations(
        dataset_dir=args.dataset,
        limit=args.limit,
        provider=args.provider,
        model_name=args.model,
    )
    logger.info(f"\n✅ Annotations ready at: {ann_dir}")
    logger.info(f"   COCO JSON: {coco_path}")
    logger.info(f"   → Now run: python training/train.py yolo --annotations {ann_dir}")



def cmd_yolo(args):
    """Strategy B Step 2: Launch YOLOv8 training on RTX 3050."""
    logger.info("Starting Strategy B-2: YOLOv8 Training Launcher (RTX 3050)")
    logger.info(f"  Annotations : {args.annotations}")
    logger.info(f"  Epochs      : {args.epochs}")
    logger.info(f"  Batch size  : {args.batch}")
    logger.info(f"  Model       : {args.model}")
    logger.info(f"  Fresh run   : {args.fresh}")
    
    from training.yolo_train_launcher import launch_yolo_training
    best_weights = launch_yolo_training(
        annotations_dir=args.annotations,
        epochs=args.epochs,
        batch=args.batch,
        model=args.model,
        fresh=args.fresh,
    )
    logger.info(f"\n✅ Training complete. Best weights: {best_weights}")
    logger.info(f"   → To use in SID-AI: set YOLO_WEIGHTS_PATH={best_weights}")


def cmd_corpus(args):
    """Strategy C: Run full pipeline on all images, build corpus."""
    logger.info("Starting Strategy C: Full Pipeline Corpus Builder")
    logger.info(f"  Dataset       : {args.dataset}")
    logger.info(f"  Limit         : {args.limit or 'all'}")
    logger.info(f"  OCR engine    : {args.ocr_engine}")
    logger.info(f"  Reasoning     : {args.reasoning_engine}")
    
    from training.corpus_builder import build_corpus
    corpus_dir = build_corpus(
        dataset_dir=args.dataset,
        limit=args.limit,
        ocr_engine=args.ocr_engine,
        reasoning_engine=args.reasoning_engine,
    )
    logger.info(f"\n✅ Corpus built at: {corpus_dir}")
    logger.info(f"   → See corpus_summary.json for aggregate metrics")


def main():
    parser = argparse.ArgumentParser(
        description="SID-AI Training CLI — P&ID Model Training & Dataset Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── vlm subcommand ──────────────────────────────────────────────────────────
    p_vlm = subparsers.add_parser(
        "vlm",
        help="Strategy A: Generate Gemini SFT JSONL dataset from all images"
    )
    p_vlm.add_argument(
        "--dataset", required=True,
        help="Path to dataset root dir (must contain manifest.csv)"
    )
    p_vlm.add_argument(
        "--limit", type=int, default=None,
        help="Max images to process (omit for all)"
    )
    p_vlm.set_defaults(func=cmd_vlm)

    # ── annotate subcommand ─────────────────────────────────────────────────────
    p_ann = subparsers.add_parser(
        "annotate",
        help="Strategy B Step 1: Generate YOLO + COCO annotations from patch images"
    )
    p_ann.add_argument(
        "--dataset", required=True,
        help="Path to dataset root dir (must contain manifest.csv + patches/)"
    )
    p_ann.add_argument(
        "--provider", default=None,
        choices=["gemini", "qwen", "openrouter", "openai"],
        help="LLM provider for symbol extraction (default: gemini; use openrouter/qwen or openai to avoid Gemini free-tier daily quota)"
    )
    p_ann.add_argument(
        "--model", default=None,
        help="Specific model name (e.g. qwen/qwen2.5-vl-72b-instruct or gpt-4o)"
    )
    p_ann.add_argument(
        "--limit", type=int, default=None,
        help="Max patches to annotate (omit for all)"
    )

    p_ann.set_defaults(func=cmd_annotate)

    # ── yolo subcommand ─────────────────────────────────────────────────────────
    p_yolo = subparsers.add_parser(
        "yolo",
        help="Strategy B Step 2: Launch YOLOv8 training on RTX 3050 GPU"
    )
    p_yolo.add_argument(
        "--annotations", required=True,
        help="Path to annotations dir (output of 'annotate' subcommand)"
    )
    p_yolo.add_argument(
        "--epochs", type=int, default=50,
        help="Number of training epochs (default: 50)"
    )
    p_yolo.add_argument(
        "--batch", type=int, default=8,
        help="Batch size for RTX 3050 4GB VRAM (default: 8)"
    )
    p_yolo.add_argument(
        "--model", default="yolov8m.pt",
        choices=["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"],
        help="YOLOv8 model variant (default: yolov8m — best for 4GB VRAM)"
    )
    p_yolo.add_argument(
        "--fresh", action="store_true",
        help="Start training fresh from epoch 1, archiving any previous training run"
    )
    p_yolo.set_defaults(func=cmd_yolo)

    # ── corpus subcommand ───────────────────────────────────────────────────────
    p_corpus = subparsers.add_parser(
        "corpus",
        help="Strategy C: Run full SID-AI pipeline on all images to build training corpus"
    )
    p_corpus.add_argument(
        "--dataset", required=True,
        help="Path to dataset root dir (must contain manifest.csv + full_page/)"
    )
    p_corpus.add_argument(
        "--limit", type=int, default=None,
        help="Max full-page images to process (omit for all)"
    )
    p_corpus.add_argument(
        "--ocr-engine", default="paddle",
        choices=["paddle", "gemini_ocr", "llamaparse", "pathnovo", "pdf_text"],
        help="Layer 1 OCR engine (default: paddle — local, no API cost)"
    )
    p_corpus.add_argument(
        "--reasoning-engine", default="gemini",
        choices=["gemini", "rule_based", "qwen", "qwen_37", "openai"],
        help="Layer 2 reasoning engine (default: gemini)"
    )
    p_corpus.set_defaults(func=cmd_corpus)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
