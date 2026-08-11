"""
Parallel Vision & Perception Agents — 3-Agent Parallel Perception Architecture.

3-AGENT PARALLEL PERCEPTION STAGE:
───────────────────────────────────
1. TextRecognitionAgent (text_recognition):
   • Specialized Text & Tag Recognition (Layer 1 OCR + Layer 2 Reasoning / Tag Parsing).
   • Supports PaddleOCR, PyMuPDF Vector Text, PaddleOCR-VL (0.9B), LlamaParse, Qwen 3.7-VL, Gemini, OpenAI.
   • Outputs: text_elements (equipment tags, line tags, instrument tags, valve tags, specs, notes, ratings).

2. SymbolRecognitionAgent (symbol_recognition):
   • Specialized ISA-5.1 & Multi-discipline Symbol Recognition (Object Detection & Bounding Boxes).
   • Supports GLM-OCR / RF-DETR pipelines, Roboflow workflows, and VLM Symbol Classification.
   • Outputs: symbols (symbol_type, inferred_tag, ymin, xmin, ymax, xmax).

3. PipelineRecognitionAgent (pipeline_recognition):
   • Specialized Line Tracing, Flow Directions & Connectivity Relationship Recognition.
   • Traces piping runs, electrical busbars, cable routes, signal loops, and topological links (INSTALLED_ON, CONNECTS_TO, MONITORS, FEEDS, EARTHED_TO).
   • Outputs: relations & geometry.
"""

import logging
import os
import re
import time
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field
from src.agents.base import BaseAgent
from src.state import GraphState
from src.utils.mock_data import MOCK_TEXT_ELEMENTS, MOCK_SYMBOLS, MOCK_RELATIONS

logger = logging.getLogger(__name__)


def _is_cuda_available() -> bool:
    """Returns True if a CUDA GPU is available (e.g. RTX 3050)."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Drawing-type-aware prompt builders
# ──────────────────────────────────────────────────────────────────────────────

_PID_TAG_CATEGORIES = (
    "  - EQUIPMENT_TAG: Compressors, motors, vessels, skids, coolers, filters "
    "(e.g., 26-KA-901, TK-101, P-101).\n"
    "  - LINE_TAG: Piping run descriptions with size, fluid service, spec class "
    "(e.g., 8\"-PV-26-9035-FC11S-08, 3\"-VA-26-9121-AC21-00).\n"
    "  - INSTRUMENT_TAG: Sensors, bubbles, transmitters, indicators "
    "(e.g., PIT-9062, TIT-9057, PDIT-9054).\n"
    "  - VALVE_TAG: Manual, control, check, gate, globe, needle valves "
    "(e.g., 26GB9178, HV-101, XV-201).\n"
    "  - PSV_TAG: Pressure Safety Valves (e.g., 26-PSV-9066A, PSV-101A).\n"
    "  - NOTE: Plain English notes, descriptions, labels (e.g., HIGH POINT, NOTE 35).\n"
    "  - RATING: Numeric specs like 150#, 2500#, pressure classes.\n"
)

_ELECTRICAL_TAG_CATEGORIES = (
    "  - PANEL_TAG: Distribution boards, MDBs, LDBs, switchgear panels "
    "(e.g., DB-01, MDB-A, LDB-3, EMDB, SMDB).\n"
    "  - LUMINAIRE_TAG: Light fittings, lamps, luminaires "
    "(e.g., L-01, LS-201, TL-101, FL-01).\n"
    "  - CIRCUIT_TAG: Electrical circuits, breakers, MCBs "
    "(e.g., C-101, CB-01, MCB-1, RCCB-3).\n"
    "  - ELEVATION_TAG: Elevation labels and level references "
    "(e.g., EL.101.445, TL 100.000, EL +103.000).\n"
    "  - EQUIPMENT_TAG: Generic equipment tags (e.g., AHU-01, FAN-01, AC-01).\n"
    "  - NOTE: Wiring notes, area labels, installation notes.\n"
    "  - RATING: Electrical ratings (e.g., 415V, 32A, 3Φ).\n"
)

_EARTHING_TAG_CATEGORIES = (
    "  - EARTH_BAR_TAG: Earthing bars and main earth terminals "
    "(e.g., EB-01, EBM-01, MEB).\n"
    "  - EARTH_PIT_TAG: Earth electrodes and earth pits "
    "(e.g., EP-01, EP-A, earth pit).\n"
    "  - BOND_CONDUCTOR_TAG: Bonding conductors and earth cables "
    "(e.g., BC-01, EC-01, earthing conductor).\n"
    "  - EQUIPMENT_TAG: Equipment being earthed (e.g., structural members, tanks, panels).\n"
    "  - ELEVATION_TAG: Elevation labels (e.g., EL.101.445, TL 100.000).\n"
    "  - NOTE: Installation notes, material specs (e.g., 50x6mm Copper Tape).\n"
    "  - RATING: Resistance values, conductor sizes (e.g., <1 Ohm, 95mm²).\n"
)

_SLD_TAG_CATEGORIES = (
    "  - PANEL_TAG: Switchgear, busbars, transformers, MVDBs, LVDBs "
    "(e.g., MVDB-01, LVDB-A, TR-01, MSB).\n"
    "  - CIRCUIT_TAG: Feeders, breakers, contactors "
    "(e.g., ACB-01, MCCB-3, VCB-01, feeder).\n"
    "  - EQUIPMENT_TAG: Motors, loads, generators (e.g., M-101, G-01).\n"
    "  - RATING: Electrical ratings (e.g., 11kV, 415V, 500kVA, 1250A).\n"
    "  - NOTE: Protection settings, fault levels, cable sizes.\n"
)

_GENERIC_TAG_CATEGORIES = (
    "  - EQUIPMENT_TAG: Any equipment with a tag number (e.g., TK-101, P-101, E-201).\n"
    "  - NOTE: Labels, descriptions, specifications.\n"
    "  - RATING: Numeric specifications.\n"
)

_SYMBOL_VOCAB: Dict[str, str] = {
    "PID": (
        "COMPRESSOR, MOTOR, COOLER, SKID, COALESCER, FILTER, SEPARATOR, VESSEL, PUMP, "
        "HEAT_EXCHANGER, TANK, INST_BUBBLE, PSV, PRV, GLOBE_VALVE, CHECK_VALVE, BALL_VALVE, "
        "GATE_VALVE, NEEDLE_VALVE, CONTROL_VALVE, BUTTERFLY_VALVE, PLUG_VALVE, SAFETY_VALVE, "
        "STRAINER, SPECTACLE_BLIND, FLANGE, NOZZLE, REDUCER, TEE"
    ),
    "PFD": (
        "VESSEL, HEAT_EXCHANGER, PUMP, COMPRESSOR, COLUMN, FURNACE, REACTOR, "
        "STREAM_ARROW, MIXER, SPLITTER"
    ),
    "ELECTRICAL_LAYOUT": (
        "LUMINAIRE, FLUORESCENT_FITTING, LED_FITTING, FLOODLIGHT, EMERGENCY_LIGHT, "
        "EXIT_SIGN, STREET_LIGHT, CEILING_FAN, EXHAUST_FAN, SOCKET_OUTLET, "
        "SWITCH, DISTRIBUTION_BOARD, CABLE_TRAY, CONDUIT, JUNCTION_BOX, "
        "TRANSFORMER, MOTOR, GENERATOR, UPS"
    ),
    "EARTHING_LAYOUT": (
        "EARTH_BAR, MAIN_EARTH_BAR, EARTH_PIT, EARTH_ELECTRODE, EARTH_ROD, "
        "BONDING_CONDUCTOR, EARTH_CABLE, TEST_LINK, EARTH_CLAMP, "
        "STRUCTURAL_COLUMN, TANK, VESSEL, PIPE_SUPPORT"
    ),
    "SLD": (
        "TRANSFORMER, BUSBAR, CIRCUIT_BREAKER, ISOLATOR, FUSE, CONTACTOR, "
        "MOTOR, GENERATOR, UPS, VFD, CAPACITOR_BANK, SURGE_ARRESTER, "
        "CURRENT_TRANSFORMER, VOLTAGE_TRANSFORMER, RELAY, METER"
    ),
    "HVAC_LAYOUT": (
        "AHU, FCU, VAV_BOX, SUPPLY_DIFFUSER, RETURN_GRILLE, EXHAUST_GRILLE, "
        "DUCTWORK, FLEXIBLE_DUCT, FIRE_DAMPER, VOLUME_CONTROL_DAMPER, "
        "CHILLER, COOLING_TOWER, PUMP, FAN, FILTER_BOX"
    ),
    "STRUCTURAL_LAYOUT": (
        "COLUMN, BEAM, SLAB, WALL, FOOTING, PILE_CAP, "
        "STAIRCASE, RAMP, OPENING, GRID_LINE, DIMENSION_LINE"
    ),
    "CABLE_SCHEDULE": (
        "CABLE_DRUM, CABLE_TRAY, CONDUIT, JUNCTION_BOX, TERMINATION_BOX, "
        "DISTRIBUTION_BOARD, MOTOR, PANEL"
    ),
    "ISOMETRIC": (
        "ELBOW_90, ELBOW_45, TEE, REDUCER, FLANGE, WELD, SUPPORT, "
        "VALVE, CHECK_VALVE, SPECTACLE_BLIND, FLOW_DIRECTION"
    ),
}


def _get_tag_categories(drawing_type: str) -> str:
    dt = drawing_type.upper()
    if dt in ('ELECTRICAL_LAYOUT',):
        return _ELECTRICAL_TAG_CATEGORIES
    if dt == 'EARTHING_LAYOUT':
        return _EARTHING_TAG_CATEGORIES
    if dt == 'SLD':
        return _SLD_TAG_CATEGORIES
    if dt in ('STRUCTURAL_LAYOUT', 'HVAC_LAYOUT', 'CABLE_SCHEDULE', 'ISOMETRIC', 'GENERIC'):
        return _GENERIC_TAG_CATEGORIES
    return _PID_TAG_CATEGORIES


def _get_symbol_vocab(drawing_type: str) -> str:
    dt = drawing_type.upper()
    return _SYMBOL_VOCAB.get(dt, _SYMBOL_VOCAB['PID'])


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────

class RawTextDetection(BaseModel):
    tag: str = Field(description="The detected text/tag string (e.g., 26-KA-902, 8\"-PV-26-9035-FC11S-08, DB-01)")
    classification: str = Field(description="Category (e.g., LINE_TAG, INSTRUMENT_TAG, EQUIPMENT_TAG, PANEL_TAG, LUMINAIRE_TAG, EARTH_BAR_TAG, NOTE, RATING)")
    value: str = Field(description="Cleaned textual value or description associated with the tag")
    rating: Optional[str] = Field(default=None, description="Pressure/temperature rating or electrical rating if explicitly labeled nearby")
    attributes: Optional[Dict[str, str]] = Field(
        default=None,
        description="Extracted dynamic specifications (e.g., design_pressure, design_temperature, flow_rate, material, duty, wattage, cable_size, conductor_size, resistance)"
    )

class RawTextList(BaseModel):
    items: List[RawTextDetection]


class RawSymbolDetection(BaseModel):
    symbol_type: str = Field(description="Type of symbol (e.g., COMPRESSOR, PUMP, VESSEL, BALL_VALVE, CHECK_VALVE, INST_BUBBLE, LUMINAIRE, EARTH_BAR)")
    inferred_tag: Optional[str] = Field(default=None, description="Nearby associated tag ID if readable directly")
    ymin: float = Field(description="Normalized ymin coordinate [0.0–1.0]")
    xmin: float = Field(description="Normalized xmin coordinate [0.0–1.0]")
    ymax: float = Field(description="Normalized ymax coordinate [0.0–1.0]")
    xmax: float = Field(description="Normalized xmax coordinate [0.0–1.0]")

class RawSymbolList(BaseModel):
    symbols: List[RawSymbolDetection] = Field(default_factory=list)


class RawRelation(BaseModel):
    source_tag: str = Field(description="Source object tag")
    target_tag: str = Field(description="Target object tag")
    rel_type: str = Field(description="Relationship (e.g., INSTALLED_ON, CONNECTS_TO, MONITORS, FEEDS, EARTHED_TO)")

class RawLineTrace(BaseModel):
    tag: str = Field(description="Line tag number or auto-label CV_PIPE_NN")
    grid_path: List[List[float]] = Field(description="List of coordinates [y, x] representing the line polyline path")

class RawGeometryLayout(BaseModel):
    traces: List[RawLineTrace] = Field(default_factory=list)
    sheet_grids: List[str] = Field(default_factory=list, description="Grid designations detected (e.g., B5, D10)")

class RawPipelineList(BaseModel):
    relations: List[RawRelation] = Field(default_factory=list)
    geometry: RawGeometryLayout = Field(default_factory=lambda: RawGeometryLayout(traces=[], sheet_grids=[]))


# ──────────────────────────────────────────────────────────────────────────────
# AGENT 1: Text Recognition Agent (OCR + Tag & Attribute Parsing)
# ──────────────────────────────────────────────────────────────────────────────

class TextRecognitionAgent(BaseAgent):
    """
    Dedicated Text Recognition Agent:
      • Layer 1 OCR: PaddleOCR, PyMuPDF Vector Text, PaddleOCR-VL (0.9B), LlamaParse, Qwen 3.7 VL
      • Layer 2 Reasoning Engine: Rule-Based Classifier | Deep VLM Reasoning Engine
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Text Recognition Agent (Layer 1 OCR + Layer 2 Reasoning)...")

        use_mocks = state.get("use_mocks", False)
        if use_mocks:
            logger.info("Demo Mock Fallbacks are ENABLED. Returning mock text elements.")
            return {"extracted_entities": {"text_elements": MOCK_TEXT_ELEMENTS}}

        meta = state.get("metadata", {})
        pages = meta.get("rasterized_pages", state.get("raw_documents", []))
        raw_documents = state.get("raw_documents", [])

        if not pages and not raw_documents:
            logger.error("No image pages available for text extraction.")
            return {"extracted_entities": {"text_elements": []}}

        raw_image = pages[0] if pages else raw_documents[0]
        original_doc = raw_documents[0] if raw_documents else raw_image

        local_mode = state.get("local_mode", False)
        ocr_engine = state.get("ocr_engine", "paddle").lower()
        reasoning_engine = state.get("reasoning_engine", "rule_based").lower()
        drawing_type = meta.get("drawing_type", "PID")

        llm_provider = state.get("llm_provider") or ("qwen" if reasoning_engine in ("qwen", "qwen_37") else "gemini")
        llm_model = state.get("llm_model")
        llm_api_key = state.get("llm_api_key")
        llm_base_url = state.get("llm_base_url")

        from src.utils.tag_classifier import classify_paddle_results

        logger.info(
            f"TextRecognitionAgent: drawing_type='{drawing_type}', "
            f"Layer 1 OCR='{ocr_engine}', Layer 2 Reasoning='{reasoning_engine}'"
        )

        # ── LAYER 1: OCR TEXT EXTRACTION ─────────────────────────────────────
        ocr_items: List[Dict[str, Any]] = []

        # Option A: Pathnovo ISA 5.1 Extraction Engine
        if ocr_engine in ("pathnovo_api", "pathnovo"):
            try:
                from src.utils.pathnovo_api import PathnovoAPIClient
                logger.info("Layer 1: Executing Pathnovo ISA 5.1 P&ID Extraction Engine...")
                p_client = PathnovoAPIClient(api_key=llm_api_key)
                res_p = p_client.extract_pid_data(image_path=raw_image, drawing_type=drawing_type)
                if res_p.get("text_elements"):
                    logger.info(f"Pathnovo ISA 5.1 Engine extracted {len(res_p['text_elements'])} text elements.")
                    return {"extracted_entities": {"text_elements": res_p["text_elements"]}}
            except Exception as p_err:
                logger.warning(f"Pathnovo Engine failed ({p_err}). Falling back to local OCR pipeline.")

        # Option B: PyMuPDF Vector Text Layer
        if (ocr_engine == "pdf_text" or ocr_engine == "paddle") and original_doc.lower().endswith('.pdf'):
            try:
                from src.utils.paddle_ocr import run_pdf_text_extraction
                logger.info("Layer 1: Checking PyMuPDF text layer extraction on original PDF...")
                pdf_items = run_pdf_text_extraction(original_doc)
                if len(pdf_items) > 20:
                    logger.info(f"Layer 1: PyMuPDF extracted {len(pdf_items)} vector text words.")
                    ocr_items = pdf_items
            except Exception as pdf_err:
                logger.warning(f"PyMuPDF vector text extraction failed ({pdf_err}).")

        # Option C: Local PaddleOCR / PaddleOCR-VL baseline (only if vector text layer returned nothing)
        if not ocr_items:
            try:
                from src.utils.preprocess import preprocess_for_ocr
                from src.utils.paddle_ocr import run_paddle_ocr
                processed_image = preprocess_for_ocr(raw_image)
                logger.info("Layer 1: Running local PaddleOCR / PaddleOCR-VL baseline engine...")
                paddle_items = run_paddle_ocr(processed_image)
                if paddle_items:
                    logger.info(f"Layer 1: PaddleOCR extracted {len(paddle_items)} text items.")
                    ocr_items = paddle_items
            except Exception as paddle_err:
                logger.warning(f"Local PaddleOCR extraction failed ({paddle_err}).")

        # Option D: Online Gemini / Qwen 2.5 / Qwen 3.7 VL / LlamaParse Vision OCR
        if ocr_engine in ("gemini_ocr", "qwen_ocr", "qwen_37_ocr", "llamaparse", "online_ocr"):
            logger.info(f"Layer 1: Running Online Vision OCR ({ocr_engine})...")
            try:
                prompt_ocr = (
                    "Extract all text labels, tag numbers, coordinates, and notes visible on this drawing.\n"
                    "Return a clean list of text items found on the drawing."
                )
                raw_ocr_res = self.invoke_text(
                    prompt=prompt_ocr,
                    image_path=raw_image,
                    provider="qwen" if ocr_engine in ("qwen_ocr", "qwen_37_ocr", "llamaparse") else "gemini",
                    model_name=llm_model,
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                )
                logger.info("Layer 1 Online OCR response received.")
                if raw_ocr_res and not ocr_items:
                    lines = [l.strip() for l in raw_ocr_res.splitlines() if l.strip()]
                    ocr_items = [{"text": line, "confidence": 0.9, "box": [0.5, 0.5, 0.5, 0.5]} for line in lines]
            except Exception as online_ocr_err:
                logger.warning(f"Online OCR engine failed ({online_ocr_err}).")

        # ── LAYER 2: REASONING & STRUCTURING ENGINE ───────────────────────────

        # Option A: Rule-Based Classifier (Local Offline Regex)
        if reasoning_engine == "rule_based" or (local_mode and reasoning_engine not in ("qwen", "qwen_37", "gemini", "openai")):
            logger.info("Layer 2: Executing Local Rule-Based Classifier (zero LLM tokens)...")
            structured = classify_paddle_results(ocr_items, drawing_type=drawing_type)
            logger.info(f"Layer 2: Rule-based classifier produced {len(structured)} structured items.")
            return {"extracted_entities": {"text_elements": structured}}

        # Option B: Online LLM Deep Reasoning Engine (Qwen 3.7 VL, Gemini, OpenAI, etc.)
        logger.info(f"Layer 2: Executing Online LLM Reasoning Engine using provider '{llm_provider}'...")
        try:
            from src.utils.paddle_ocr import format_paddle_results_for_llm
            raw_text_block = format_paddle_results_for_llm(ocr_items) if ocr_items else "No raw OCR text."
            tag_categories = _get_tag_categories(drawing_type)

            reasoning_prompt = (
                f"You are an expert engineering data parser and reasoning engine for {drawing_type.replace('_', ' ')} drawings.\n"
                "Below is the Layer 1 OCR output extracted from the drawing:\n"
                "  <text> | conf=<confidence> | pos=(<center_x>, <center_y>)\n\n"
                f"RAW OCR TEXT FROM LAYER 1:\n{raw_text_block}\n\n"
                "PERFORM DEEP REASONING & REFINEMENT:\n"
                "1. FIX OCR TYPOS: Correct misread letters/digits (e.g., P1T-9055 -> PIT-9055, 0B-01 -> DB-01, E8-01 -> EB-01).\n"
                "2. RECOMBINE SPLIT TEXT: Re-assemble tags that were split across multiple OCR lines.\n"
                "3. IDENTIFY MISPLACED DATA: Map nearby specifications (design pressure, design temp, wattage, rating, cable size, elevation, material, duty) into the parent tag's attributes dict.\n"
                "4. FIND MISSING TAGS/ENTITIES: Visually inspect the drawing image to find any missing tags or equipment referenced in callouts or note blocks.\n"
                "5. CLASSIFY & STRUCTURE: Map every entity into ONE of the following categories:\n"
                + tag_categories + "\n"
                "Return the cleaned, structured findings as a validated RawTextList JSON."
            )

            result = self.invoke_structured(
                schema=RawTextList,
                prompt=reasoning_prompt,
                system_instruction=(
                    "You are an AI engineering data reasoning engine. Your goal is to find missing data, "
                    "correct OCR errors, map misplaced attributes, and output clean structured JSON."
                ),
                image_path=raw_image,
                provider=llm_provider,
                model_name=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
            )

            extracted_items = [item.model_dump() for item in result.items]
            logger.info(f"Layer 2 Reasoning Engine ({llm_provider}): produced {len(extracted_items)} refined structured entities.")
            return {"extracted_entities": {"text_elements": extracted_items}}

        except Exception as llm_err:
            logger.warning(f"Layer 2 Reasoning Engine failed ({llm_err}). Falling back to local rule-based classifier.")
            structured = classify_paddle_results(ocr_items, drawing_type=drawing_type)
            return {"extracted_entities": {"text_elements": structured}}


# ──────────────────────────────────────────────────────────────────────────────
# AGENT 2: Symbol Recognition Agent (ISA-5.1 & Multi-Discipline Symbol Detection)
# ──────────────────────────────────────────────────────────────────────────────

class SymbolRecognitionAgent(BaseAgent):
    """
    Dedicated Symbol Recognition Agent:
      • Detects graphic component symbols & bounding boxes (ymin, xmin, ymax, xmax).
      • Supports VLM Multimodal Symbol Detector, GLM-OCR / RF-DETR pipelines, and Local Harvesters.
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Symbol Recognition Agent (ISA-5.1 & Graphic Symbol Detector)...")

        use_mocks = state.get("use_mocks", False)
        if use_mocks:
            logger.info("Demo Mock Fallbacks are ENABLED. Returning mock symbols.")
            return {"extracted_entities": {"symbols": MOCK_SYMBOLS}}

        meta = state.get("metadata", {})
        pages = meta.get("rasterized_pages", state.get("raw_documents", []))
        raw_documents = state.get("raw_documents", [])
        if not pages and not raw_documents:
            return {"extracted_entities": {"symbols": []}}

        raw_image = pages[0] if pages else raw_documents[0]
        local_mode = state.get("local_mode", False)
        symbol_engine = state.get("symbol_engine", "vlm").lower()

        llm_provider = state.get("llm_provider")
        llm_model = state.get("llm_model")
        llm_api_key = state.get("llm_api_key")
        llm_base_url = state.get("llm_base_url")

        symbols = []
        drawing_type = meta.get("drawing_type", "PID")
        symbol_vocab = _get_symbol_vocab(drawing_type)
        dt_label = drawing_type.replace('_', ' ')

        # Option A: Pathnovo ISA 5.1 Native Instrument & Symbol Parser
        if "pathnovo" in symbol_engine:
            try:
                from src.utils.pathnovo_api import PathnovoAPIClient
                logger.info("SymbolRecognitionAgent: Executing Pathnovo ISA 5.1 Symbol Parser...")
                p_client = PathnovoAPIClient(api_key=llm_api_key)
                res_p = p_client.extract_pid_data(image_path=raw_image, drawing_type=drawing_type)
                if res_p.get("symbols"):
                    logger.info(f"SymbolRecognitionAgent (pathnovo): extracted {len(res_p['symbols'])} symbols.")
                    symbols = res_p["symbols"]
            except Exception as p_err:
                logger.warning(f"Pathnovo Symbol Parser failed ({p_err}). Falling back to standard VLM pipeline.")

        # Option B: Trained YOLOv8 Symbol Detector (custom best.pt from training pipeline)
        elif symbol_engine == "yolo_trained":
            weights_path = (
                state.get("yolo_weights_path")
                or os.getenv("DEFAULT_YOLO_WEIGHTS", "")
            )
            if not weights_path or not os.path.exists(weights_path):
                logger.warning(
                    f"YOLOv8 weights not found at '{weights_path}'. "
                    "Falling back to heuristic harvester. "
                    "Run training first: python training/train.py yolo ..."
                )
            else:
                try:
                    from ultralytics import YOLO
                    from src.agents.base import BaseAgent as _BA

                    logger.info(f"SymbolRecognitionAgent: Loading trained YOLOv8 from '{weights_path}'...")
                    yolo_model = YOLO(weights_path)

                    # Encode image for inference
                    import numpy as np
                    from PIL import Image as _PilImage
                    with _PilImage.open(raw_image) as _img:
                        img_w, img_h = _img.size
                        _img_rgb = _img.convert("RGB")

                    results = yolo_model.predict(
                        source=str(raw_image),
                        conf=state.get("yolo_conf") or 0.25,
                        iou=state.get("yolo_iou") or 0.45,
                        imgsz=800,          # Match training imgsz
                        device="0" if _is_cuda_available() else "cpu",
                        verbose=False,
                    )

                    # YOLO class names from the training annotation_generator
                    from training.annotation_generator import SYMBOL_CLASSES

                    for result in results:
                        for box in result.boxes:
                            cls_id   = int(box.cls[0].item())
                            conf_val = float(box.conf[0].item())
                            # box.xyxyn → normalized [x1, y1, x2, y2]
                            x1n, y1n, x2n, y2n = box.xyxyn[0].tolist()
                            sym_type = SYMBOL_CLASSES[cls_id] if cls_id < len(SYMBOL_CLASSES) else "UNKNOWN"

                            symbols.append({
                                "symbol_type" : sym_type,
                                "inferred_tag": None,
                                "ymin"        : round(y1n, 4),
                                "xmin"        : round(x1n, 4),
                                "ymax"        : round(y2n, 4),
                                "xmax"        : round(x2n, 4),
                                "confidence"  : round(conf_val, 3),
                            })

                    logger.info(
                        f"SymbolRecognitionAgent (yolo_trained): detected {len(symbols)} symbols "
                        f"from '{os.path.basename(weights_path)}'."
                    )
                except ImportError:
                    logger.error(
                        "ultralytics not installed. Run: pip install ultralytics. "
                        "Falling back to heuristic harvester."
                    )
                except Exception as yolo_err:
                    logger.error(f"Trained YOLOv8 inference failed ({yolo_err}). Falling back to heuristic harvester.")

        # Option C: VLM or GLM-OCR / RF-DETR object detector
        elif not (local_mode or symbol_engine == "local"):

            prompt = (
                f"You are an expert industrial vision detector specializing in ISA-5.1 and engineering symbol recognition for {dt_label} drawings.\n"
                f"Identify all graphical component symbols present in this drawing image.\n\n"
                f"SYMBOL TAXONOMY VOCABULARY:\n  {symbol_vocab}\n\n"
                "FOR EACH DETECTED SYMBOL PROVIDE:\n"
                "  1. symbol_type: The exact symbol classification from the taxonomy vocabulary.\n"
                "  2. inferred_tag: Nearest readable tag number/ID (e.g., 26CB9131, PIT-9055, DB-01, EP-01) if visible nearby.\n"
                "  3. ymin, xmin, ymax, xmax: Normalized bounding box coordinates between 0.0 and 1.0.\n\n"
                "Return the list of detected symbols in structured JSON format."
            )

            try:
                result = self.invoke_structured(
                    schema=RawSymbolList,
                    prompt=prompt,
                    image_path=raw_image,
                    image_uri=meta.get("primary_page_uri"),
                    image_mime=meta.get("primary_page_mime", "image/png"),
                    provider=llm_provider,
                    model_name=llm_model,
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                )
                symbols = [s.model_dump() for s in result.symbols]
                logger.info(f"SymbolRecognitionAgent ({symbol_engine}): VLM extracted {len(symbols)} symbols.")
            except Exception as err:
                logger.error(f"SymbolRecognitionAgent VLM call failed ({err}). Using heuristic harvester.")

        # Option B: Heuristic symbol harvester from text elements in state
        texts = state.get("extracted_entities", {}).get("text_elements", [])
        existing_tags = {s.get("inferred_tag") for s in symbols if s.get("inferred_tag")}

        for t in texts:
            tag = t.get("tag")
            cls = t.get("classification")
            if not tag or tag in existing_tags:
                continue

            sym_type = None
            if cls == "EQUIPMENT_TAG":
                sym_type = "EQUIPMENT"
            elif cls == "VALVE_TAG":
                sym_type = "CHECK_VALVE" if ("CB" in tag.upper() or "CHECK" in tag.upper()) else "VALVE"
            elif cls == "INSTRUMENT_TAG":
                sym_type = "INST_BUBBLE"
            elif cls == "PSV_TAG":
                sym_type = "PSV"
            elif cls == "LUMINAIRE_TAG":
                sym_type = "LUMINAIRE"
            elif cls == "PANEL_TAG":
                sym_type = "PANEL"
            elif cls == "EARTH_BAR_TAG":
                sym_type = "EARTH_BAR"
            elif cls == "EARTH_PIT_TAG":
                sym_type = "EARTH_PIT"

            if sym_type:
                attrs = t.get("attributes") or {}
                px = float(attrs.get("pos_x", 0.5)) if attrs.get("pos_x") else 0.5
                py = float(attrs.get("pos_y", 0.5)) if attrs.get("pos_y") else 0.5
                symbols.append({
                    "symbol_type": sym_type,
                    "inferred_tag": tag,
                    "ymin": round(max(0.0, py - 0.02), 4),
                    "xmin": round(max(0.0, px - 0.02), 4),
                    "ymax": round(min(1.0, py + 0.02), 4),
                    "xmax": round(min(1.0, px + 0.02), 4),
                })

        logger.info(f"SymbolRecognitionAgent produced {len(symbols)} total graphical symbols.")
        return {"extracted_entities": {"symbols": symbols}}


# ──────────────────────────────────────────────────────────────────────────────
# AGENT 3: Pipeline Recognition Agent (Line Tracing, Flow Directions & Connectivity)
# ──────────────────────────────────────────────────────────────────────────────

class PipelineRecognitionAgent(BaseAgent):
    """
    Dedicated Pipeline & Connectivity Recognition Agent:
      • Traces piping runs, line sizes, electrical busbars, cable routes, and flow direction arrows.
      • Integrates OpenCV Computer Vision Line Tracer + Spatial Proximity Linker.
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Pipeline Recognition Agent (Connectivity & Line Tracing)...")

        use_mocks = state.get("use_mocks", False)
        if use_mocks:
            logger.info("Demo Mock Fallbacks are ENABLED. Returning mock pipeline relations.")
            return {
                "extracted_entities": {
                    "relations": MOCK_RELATIONS,
                    "geometry": {"traces": [], "sheet_grids": ["B5", "C9", "D10"]},
                }
            }

        meta = state.get("metadata", {})
        pages = meta.get("rasterized_pages", state.get("raw_documents", []))
        raw_documents = state.get("raw_documents", [])
        if not pages and not raw_documents:
            return {"extracted_entities": {"relations": [], "geometry": {}}}

        raw_image = pages[0] if pages else raw_documents[0]
        local_mode = state.get("local_mode", False)
        pipeline_engine = state.get("pipeline_engine", "cv_vlm_tracer").lower()

        llm_provider = state.get("llm_provider")
        llm_model = state.get("llm_model")
        llm_api_key = state.get("llm_api_key")
        llm_base_url = state.get("llm_base_url")

        drawing_type = meta.get("drawing_type", "PID")
        dt_label = drawing_type.replace('_', ' ')

        relations = []
        geometry = {"traces": [], "sheet_grids": ["A1", "B5", "C9", "D10"]}

        # Option A: Pathnovo ISA 5.1 Line & Loop Spec Tracer
        if "pathnovo" in pipeline_engine:
            try:
                from src.utils.pathnovo_api import PathnovoAPIClient
                logger.info("PipelineRecognitionAgent: Executing Pathnovo ISA 5.1 Line Tracer...")
                p_client = PathnovoAPIClient(api_key=llm_api_key)
                res_p = p_client.extract_pid_data(image_path=raw_image, drawing_type=drawing_type)
                if res_p.get("relations"):
                    logger.info(f"PipelineRecognitionAgent (pathnovo): extracted {len(res_p['relations'])} relations.")
                    relations = res_p["relations"]
            except Exception as p_err:
                logger.warning(f"Pathnovo Pipeline Tracer failed ({p_err}). Falling back to CV line tracer.")

        # Option B: Full Multimodal VLM Polyline Tracer or Hybrid CV + VLM
        elif not (local_mode or pipeline_engine == "proximity_tracer"):
            prompt = (
                f"You are an expert topological pipeline and electrical connectivity tracer analyzing a {dt_label} drawing.\n\n"
                "TASK 1 — TOPOLOGICAL RELATIONSHIPS:\n"
                "Extract source→target connectivity pairs:\n"
                "  - MONITORS: Instrument or sensor monitoring a line or equipment.\n"
                "  - INSTALLED_ON: Valve or fitting installed on a line run.\n"
                "  - CONNECTS_TO: Pipe, busbar, or cable connecting two pieces of equipment.\n"
                "  - FEEDS: Distribution panel or switchboard feeding a circuit or breaker.\n"
                "  - EARTHED_TO: Equipment grounded to an earth bar or earth pit.\n\n"
                "TASK 2 — GEOMETRY & SHEET GRIDS:\n"
                "List the border grid sector designations (e.g., A1, B5, C9, D10) and trace any named piping runs or cable routes.\n\n"
                "Return all findings in structured JSON format."
            )

            try:
                result = self.invoke_structured(
                    schema=RawPipelineList,
                    prompt=prompt,
                    image_path=raw_image,
                    image_uri=meta.get("primary_page_uri"),
                    image_mime=meta.get("primary_page_mime", "image/png"),
                    provider=llm_provider,
                    model_name=llm_model,
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                )
                relations = [r.model_dump() for r in result.relations]
                geometry = result.geometry.model_dump()
            except Exception as err:
                logger.error(f"PipelineRecognitionAgent VLM call failed ({err}). Falling back to CV line tracer.")

        # Option B: OpenCV Morphological Computer Vision & Spatial Line Tracer
        from src.utils.line_tracer import trace_lines_and_connections
        text_elements = state.get("extracted_entities", {}).get("text_elements", [])
        symbols = state.get("extracted_entities", {}).get("symbols", [])

        # Guarantee non-empty text_elements for line tracer even if running in parallel
        if not text_elements:
            try:
                from src.utils.paddle_ocr import run_paddle_ocr
                from src.utils.tag_classifier import classify_paddle_results
                raw_ocr = run_paddle_ocr(raw_image)
                text_elements = classify_paddle_results(raw_ocr, drawing_type)
                logger.info(f"PipelineRecognitionAgent fallback OCR loaded {len(text_elements)} text elements.")
            except Exception as e:
                logger.warning(f"PipelineRecognitionAgent fallback OCR failed: {e}")

        cv_res = trace_lines_and_connections(
            image_path=raw_image,
            text_elements=text_elements,
            symbols=symbols,
            drawing_type=drawing_type,
        )

        # Merge relations & line traces
        existing_rel_keys = {(r["source_tag"], r["target_tag"], r["rel_type"]) for r in relations}
        for cr in cv_res.get("relations", []):
            key = (cr["source_tag"], cr["target_tag"], cr["rel_type"])
            if key not in existing_rel_keys:
                existing_rel_keys.add(key)
                relations.append(cr)

        cv_geometry = cv_res.get("geometry", {})
        existing_trace_tags = {t.get("tag") for t in geometry.get("traces", []) if t.get("tag")}
        for tr in cv_geometry.get("traces", []):
            if tr.get("tag") not in existing_trace_tags:
                existing_trace_tags.add(tr.get("tag"))
                geometry.setdefault("traces", []).append(tr)

        logger.info(
            f"PipelineRecognitionAgent ({pipeline_engine}) produced {len(relations)} relations & "
            f"{len(geometry.get('traces', []))} physical line traces."
        )
        return {"extracted_entities": {"relations": relations, "geometry": geometry}}
