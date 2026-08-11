"""
Strategy B — Part 2: YOLOv8 Training Launcher.

Launches YOLOv8 object detection training on the annotated P&ID symbol dataset.
Configured for NVIDIA RTX 3050 (4GB VRAM) with CUDA acceleration.

Usage:
    python training/train.py yolo --annotations training/outputs/annotations
    python training/train.py yolo --annotations training/outputs/annotations --epochs 100
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── RTX 3050 Optimal Hyperparameters ──────────────────────────────────────────
#
# RTX 3050 has 4GB VRAM. These settings are tuned to maximize utilisation
# while avoiding OOM errors on a 4GB VRAM budget:
#   - batch=8    : safe for 1000x800 patches on 4GB VRAM
#   - imgsz=800  : matches patch height (wider dimension)
#   - workers=4  : good for 8-core consumer CPUs
#   - amp=True   : Automatic Mixed Precision (FP16) saves ~50% VRAM
#   - cache=True : caches images to RAM for faster I/O

RTX3050_CONFIG = {
    "model"     : "yolov8m.pt",    # YOLOv8-Medium: best accuracy/speed on 4GB VRAM
    "epochs"    : 50,
    "batch"     : 8,
    "imgsz"     : 800,
    "device"    : "0",             # CUDA device 0 (RTX 3050)
    "workers"   : 4,
    "amp"       : True,            # Automatic Mixed Precision (FP16)
    "cache"     : True,            # Cache images in RAM
    "patience"  : 0,               # Set 0 to disable EarlyStopping and train ALL requested epochs
    "lr0"       : 0.01,            # Initial learning rate
    "lrf"       : 0.01,            # Final LR fraction
    "momentum"  : 0.937,
    "weight_decay": 0.0005,
    "warmup_epochs": 3,
    "box"       : 7.5,             # Box loss gain (higher → better bbox regression)
    "cls"       : 0.5,             # Classification loss gain
    "dfl"       : 1.5,             # Distribution focal loss gain
    "augment"   : True,            # Enable YOLOv8 built-in augmentation
    "degrees"   : 5.0,             # Rotation augmentation ±5° (matches dataset's ±2° + more)
    "translate" : 0.1,
    "scale"     : 0.2,
    "shear"     : 2.0,
    "perspective": 0.001,
    "flipud"    : 0.0,             # No vertical flip (P&ID symbols are orientation-sensitive)
    "fliplr"    : 0.3,
    "mosaic"    : 0.8,
    "mixup"     : 0.1,
}



def _check_cuda_available() -> bool:
    """Check if CUDA/torch is available for GPU training."""
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info(f"GPU detected: {device_name} ({vram_gb:.1f} GB VRAM)")
            return True
        else:
            logger.warning("CUDA not available. Training will run on CPU (very slow).")
            return False
    except ImportError:
        logger.warning("PyTorch not installed. Training will use CPU.")
        return False


def _check_ultralytics() -> bool:
    """Verify ultralytics is installed."""
    try:
        import ultralytics
        logger.info(f"Ultralytics YOLOv8 version: {ultralytics.__version__}")
        return True
    except ImportError:
        logger.error("ultralytics not installed. Run: pip install ultralytics")
        return False


def launch_yolo_training(
    annotations_dir: str,
    epochs: int = 50,
    batch: int = 8,
    model: str = "yolov8m.pt",
    project_name: str = "pid_symbol_detector",
) -> str:
    """
    Launches YOLOv8 training on the annotated P&ID symbol dataset.

    Args:
        annotations_dir: Path to annotations directory (must contain data.yaml)
        epochs: Number of training epochs
        batch: Batch size (8 recommended for RTX 3050 4GB)
        model: YOLOv8 model variant (yolov8n/s/m/l/x)
        project_name: Training run project name

    Returns:
        Path to trained weights (best.pt)
    """
    if not _check_ultralytics():
        raise RuntimeError("ultralytics not installed. Run: pip install ultralytics")

    ann_path = Path(annotations_dir)
    yaml_path = ann_path / "data.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"data.yaml not found at {yaml_path}. "
            "Run annotation generation first: python training/train.py annotate ..."
        )

    # Check dataset has images
    train_imgs = list((ann_path / "images" / "train").glob("*.png"))
    val_imgs   = list((ann_path / "images" / "val").glob("*.png"))
    logger.info(f"Dataset: {len(train_imgs)} train / {len(val_imgs)} val images")

    if not train_imgs:
        raise ValueError("No training images found. Run annotation generation first.")

    # Output directory
    output_dir = Path(__file__).parent / "outputs" / "yolo_runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if last.pt exists for resuming training from epoch 21
    last_ckpt = output_dir / project_name / "weights" / "last.pt"

    resume_flag = False
    if last_ckpt.exists():
        logger.info(f"Checkpoint found at '{last_ckpt}' — resuming training from last epoch...")
        model_to_load = str(last_ckpt)
        resume_flag = True
    else:
        model_to_load = model

    # Check GPU availability
    cuda_ok = _check_cuda_available()
    device = RTX3050_CONFIG["device"] if cuda_ok else "cpu"

    logger.info("=== YOLOv8 Training Launcher (RTX 3050 Optimized) ===")


    logger.info(f"Model    : {model_to_load}")
    logger.info(f"Epochs   : {epochs}")
    logger.info(f"Batch    : {batch}")
    logger.info(f"Device   : {device} ({'CUDA/GPU' if cuda_ok else 'CPU — slow!'})")
    logger.info(f"AMP (FP16): {RTX3050_CONFIG['amp']}")
    logger.info(f"Img size : {RTX3050_CONFIG['imgsz']}")
    logger.info(f"Patience : {RTX3050_CONFIG['patience']} (0 = disabled, train all {epochs} epochs)")
    logger.info(f"Project  : {output_dir / project_name}")

    # Launch YOLO training via Python API
    try:
        from ultralytics import YOLO

        yolo_model = YOLO(model_to_load)

        train_results = yolo_model.train(
            data        = str(yaml_path),
            epochs      = epochs,
            batch       = batch,
            imgsz       = RTX3050_CONFIG["imgsz"],
            device      = device,
            workers     = RTX3050_CONFIG["workers"],
            amp         = RTX3050_CONFIG["amp"],
            cache       = RTX3050_CONFIG["cache"],
            patience    = RTX3050_CONFIG["patience"],
            resume      = resume_flag,

            lr0         = RTX3050_CONFIG["lr0"],
            lrf         = RTX3050_CONFIG["lrf"],
            momentum    = RTX3050_CONFIG["momentum"],
            weight_decay= RTX3050_CONFIG["weight_decay"],
            warmup_epochs= RTX3050_CONFIG["warmup_epochs"],
            box         = RTX3050_CONFIG["box"],
            cls         = RTX3050_CONFIG["cls"],
            dfl         = RTX3050_CONFIG["dfl"],
            degrees     = RTX3050_CONFIG["degrees"],
            translate   = RTX3050_CONFIG["translate"],
            scale       = RTX3050_CONFIG["scale"],
            shear       = RTX3050_CONFIG["shear"],
            perspective = RTX3050_CONFIG["perspective"],
            flipud      = RTX3050_CONFIG["flipud"],
            fliplr      = RTX3050_CONFIG["fliplr"],
            mosaic      = RTX3050_CONFIG["mosaic"],
            mixup       = RTX3050_CONFIG["mixup"],
            augment     = RTX3050_CONFIG["augment"],
            project     = str(output_dir),
            name        = project_name,
            exist_ok    = True,
            verbose     = True,
        )

        # Run validation
        logger.info("\n=== Running Validation on Best Weights ===")
        val_results = yolo_model.val()
        
        best_weights = output_dir / project_name / "weights" / "best.pt"
        logger.info("\n" + "="*55)
        logger.info("YOLOv8 Training — Complete")
        logger.info("="*55)
        logger.info(f"  mAP50         : {val_results.box.map50:.4f}")
        logger.info(f"  mAP50-95      : {val_results.box.map:.4f}")
        logger.info(f"  Best weights  : {best_weights}")
        logger.info(f"\n  → To use in SID-AI pipeline, set:")
        logger.info(f"    symbol_engine=local in your run config")
        logger.info(f"    YOLO_WEIGHTS_PATH={best_weights}")

        return str(best_weights)

    except Exception as e:
        logger.error(f"YOLOv8 training failed: {e}")
        raise
