import os
import logging
from typing import List
from PIL import Image

logger = logging.getLogger(__name__)

def crop_normalized_box(image_path: str, box: List[float], output_path: str) -> bool:
    """
    Crops an image file using normalized bounding coordinates: [ymin, xmin, ymax, xmax].
    Each coordinate value is between 0.0 and 1.0.
    Saves the cropped output image to `output_path`.
    Returns True if successfully cropped, False otherwise.
    """
    if not os.path.exists(image_path):
        logger.warning(f"Image path '{image_path}' not found. Skipping physical crop.")
        return False
        
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            ymin, xmin, ymax, xmax = box
            
            # Map normalized [0, 1] floats to actual pixel coordinates
            left = int(xmin * width)
            top = int(ymin * height)
            right = int(xmax * width)
            bottom = int(ymax * height)
            
            # Bound coordinates to image size boundaries
            left = max(0, min(left, width - 1))
            top = max(0, min(top, height - 1))
            right = max(left + 1, min(right, width))
            bottom = max(top + 1, min(bottom, height))
            
            # Crop and save
            cropped = img.crop((left, top, right, bottom))
            cropped.save(output_path, "PNG")
            logger.info(f"Successfully cropped region {box} to '{output_path}'.")
            return True
            
    except Exception as e:
        logger.error(f"Failed to crop image '{image_path}' with box {box}: {e}")
        return False
