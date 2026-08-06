"""
Pathnovo P&ID Extraction API Client — ISA 5.1 Instrument & Piping Standards.

Features:
  - Specifically trained on ISA 5.1 instrumentation standards.
  - Extracts instrument tag numbers, loop data, line sizes, piping specs, and valve ratings.
  - Generates structured ISA 5.1 symbols, text elements, and topological relations.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

PATHNOVO_API_URL = os.getenv("PATHNOVO_API_URL", "https://api.pathnovo.com/v1/pid/extract")


class PathnovoAPIClient:
    """
    Client for Pathnovo ISA 5.1 P&ID Extraction API.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("PATHNOVO_API_KEY", "")
        self.base_url = base_url or PATHNOVO_API_URL

    def extract_pid_data(
        self,
        image_path: str,
        drawing_type: str = "PID",
    ) -> Dict[str, Any]:
        """
        Sends drawing image to Pathnovo P&ID Extraction API.
        Returns dictionary with text_elements, symbols, and relations.
        """
        if not self.api_key:
            logger.info("PATHNOVO_API_KEY is not provided. Using Pathnovo ISA 5.1 Local Fallback Engine.")
            return self._local_isa51_extraction(image_path, drawing_type=drawing_type)

        if not os.path.exists(image_path):
            logger.error(f"Pathnovo: Image file not found: {image_path}")
            return {"text_elements": [], "symbols": [], "relations": []}

        try:
            logger.info(f"Invoking Pathnovo ISA 5.1 API ({self.base_url}) for image '{image_path}'...")

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            }

            with open(image_path, "rb") as f:
                files = {"file": (os.path.basename(image_path), f, "image/png")}
                data = {"standard": "ISA_5_1", "drawing_type": drawing_type}
                response = requests.post(self.base_url, headers=headers, files=files, data=data, timeout=60)

            if response.status_code == 200:
                res_json = response.json()
                logger.info("Pathnovo API extraction successful!")
                return self._parse_pathnovo_response(res_json)
            else:
                logger.warning(
                    f"Pathnovo API returned status code {response.status_code} ({response.text[:200]}). "
                    "Using Pathnovo ISA 5.1 Local Engine fallback."
                )
                return self._local_isa51_extraction(image_path, drawing_type=drawing_type)

        except Exception as err:
            logger.error(f"Pathnovo API call failed ({err}). Using Pathnovo ISA 5.1 Local Engine fallback.")
            return self._local_isa51_extraction(image_path, drawing_type=drawing_type)

    def _parse_pathnovo_response(self, res_json: Dict[str, Any]) -> Dict[str, Any]:
        """Maps Pathnovo API json response to SID-AI state structures."""
        text_elements = res_json.get("text_elements", [])
        symbols = res_json.get("symbols", [])
        relations = res_json.get("relations", [])
        return {
            "text_elements": text_elements,
            "symbols": symbols,
            "relations": relations,
        }

    def _local_isa51_extraction(
        self, image_path: str, drawing_type: str = "PID"
    ) -> Dict[str, Any]:
        """
        ISA 5.1 High-Accuracy Local Fallback Engine.
        Uses OCR text + ISA 5.1 rules to extract loop IDs, line sizes, and valve specs.
        """
        from src.utils.paddle_ocr import run_pdf_text_extraction, run_paddle_ocr
        from src.utils.tag_classifier import classify_paddle_results
        from src.utils.line_tracer import trace_lines_and_connections

        ocr_items = []
        if image_path.lower().endswith(".pdf"):
            ocr_items = run_pdf_text_extraction(image_path)
        if not ocr_items and os.path.exists(image_path):
            ocr_items = run_paddle_ocr(image_path)

        classified_texts = classify_paddle_results(ocr_items, drawing_type=drawing_type)

        # Build ISA 5.1 Symbols from classified instrument and valve tags
        symbols = []
        for t in classified_texts:
            tag = t.get("tag")
            cls = t.get("classification")
            attrs = t.get("attributes") or {}
            px = float(attrs.get("pos_x", 0.5)) if attrs.get("pos_x") else 0.5
            py = float(attrs.get("pos_y", 0.5)) if attrs.get("pos_y") else 0.5

            if cls == "INSTRUMENT_TAG":
                symbols.append({
                    "symbol_type": "INST_BUBBLE",
                    "inferred_tag": tag,
                    "ymin": max(0.0, py - 0.02),
                    "xmin": max(0.0, px - 0.02),
                    "ymax": min(1.0, py + 0.02),
                    "xmax": min(1.0, px + 0.02),
                })
            elif cls == "VALVE_TAG":
                v_type = "CHECK_VALVE" if ("CB" in tag.upper() or "CHECK" in tag.upper()) else "VALVE"
                symbols.append({
                    "symbol_type": v_type,
                    "inferred_tag": tag,
                    "ymin": max(0.0, py - 0.02),
                    "xmin": max(0.0, px - 0.02),
                    "ymax": min(1.0, py + 0.02),
                    "xmax": min(1.0, px + 0.02),
                })
            elif cls == "EQUIPMENT_TAG":
                symbols.append({
                    "symbol_type": "EQUIPMENT",
                    "inferred_tag": tag,
                    "ymin": max(0.0, py - 0.04),
                    "xmin": max(0.0, px - 0.04),
                    "ymax": min(1.0, py + 0.04),
                    "xmax": min(1.0, px + 0.04),
                })

        # Run OpenCV line tracer for ISA 5.1 line topology
        line_res = trace_lines_and_connections(
            image_path=image_path,
            text_elements=classified_texts,
            symbols=symbols,
            drawing_type=drawing_type,
        )

        return {
            "text_elements": classified_texts,
            "symbols": symbols,
            "relations": line_res.get("relations", []),
        }
