"""
Image Preprocessing Utilities for P&ID Diagrams.

Applies resize, denoise, and contrast enhancement before feeding images
to any OCR model or VLM, dramatically reducing input token count and
improving small-text detection accuracy.
"""
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_MAX_WIDTH = 2048  # Safe upper bound for VLM image inputs


def preprocess_for_ocr(image_path: str, output_path: Optional[str] = None) -> str:
    """
    Preprocess a P&ID drawing image for OCR:
    - Convert to RGB (drop alpha channel)
    - Resize to max 2048px wide (keeps token count low for VLMs)
    - Apply mild CLAHE contrast enhancement (improves small-text detection)
    - Denoise with a fast Non-Local Means filter
    - Save and return the output path

    Args:
        image_path: Absolute path to the input image.
        output_path: Optional explicit output path. Defaults to <name>_preprocessed.png.

    Returns:
        Path to the preprocessed image file.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning(f"preprocess_for_ocr: cv2 could not read '{image_path}'. Returning original.")
            return image_path

        # --- Step 1: Resize to max width while preserving aspect ratio ---
        h, w = img.shape[:2]
        if w > _MAX_WIDTH:
            scale = _MAX_WIDTH / w
            new_w = _MAX_WIDTH
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            logger.info(f"preprocess_for_ocr: Resized from ({w}x{h}) to ({new_w}x{new_h})")

        # --- Step 2: Mild CLAHE contrast enhancement on Luminance channel ---
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # --- Step 3: Fast denoising ---
        img = cv2.fastNlMeansDenoisingColored(img, None, h=5, hColor=5, templateWindowSize=7, searchWindowSize=21)

        # --- Step 4: Save output ---
        if output_path is None:
            base, ext = os.path.splitext(image_path)
            output_path = base + "_preprocessed.png"

        cv2.imwrite(output_path, img)
        logger.info(f"preprocess_for_ocr: Preprocessed image saved to '{output_path}'")
        return output_path

    except Exception as e:
        logger.error(f"preprocess_for_ocr failed ({e}). Returning original path.")
        return image_path


def get_image_dimensions(image_path: str) -> Tuple[int, int]:
    """Returns (width, height) of an image using OpenCV."""
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is not None:
            h, w = img.shape[:2]
            return w, h
    except Exception:
        pass
    return 0, 0
