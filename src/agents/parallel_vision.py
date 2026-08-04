"""
Parallel Vision Agents — Hybrid OCR + Multi-Provider Reasoning Architecture.

2-LAYER EXTRACTION PIPELINE
───────────────────────────
Layer 1 — OCR Reading Layer (Customizable Local / Online):
  • Local Options : PaddleOCR, PyMuPDF Vector Text, GOT-OCR 2.0
  • Online Options: Gemini Vision OCR, Qwen 2.5-VL / OpenAI-compatible Vision OCR

Layer 2 — Reasoning & Structuring Engine (Customizable Local / Online):
  • Local Option  : Rule-Based Classifier (zero LLM tokens, regex-based)
  • Online Options: Qwen 2.5 Reasoning Engine, Gemini 2.0 Flash, OpenAI GPT-4o
                   Performs deep reasoning: fixes OCR typos, recombines split tags,
                   associates misplaced attributes (pressure, temperature, wattage, cable size),
                   finds missing entities, and outputs structured JSON.
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field
from src.agents.base import BaseAgent
from src.state import GraphState
from src.utils.mock_data import MOCK_TEXT_ELEMENTS, MOCK_SYMBOLS, MOCK_RELATIONS

logger = logging.getLogger(__name__)


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
    return _PID_TAG_CATEGORIES  # P&ID / PFD default


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

class RawRelation(BaseModel):
    source_tag: str = Field(description="Source object tag")
    target_tag: str = Field(description="Target object tag")
    rel_type: str = Field(description="Relationship (e.g., INSTALLED_ON, CONNECTS_TO, MONITORS, FEEDS, EARTHED_TO)")

class RawLineTrace(BaseModel):
    tag: str = Field(description="Line tag number or auto-label CV_PIPE_NN")
    grid_path: List[List[float]] = Field(description="List of coordinates [y, x] representing the line polyline path")

class RawGeometryLayout(BaseModel):
    traces: List[RawLineTrace]
    sheet_grids: List[str] = Field(description="Grid designations detected (e.g., B5, D10)")


class UnifiedExtractionResult(BaseModel):
    """
    Single consolidated schema for VLM calls extracting symbols, relations, and geometry.
    """
    symbols: List[RawSymbolDetection] = Field(
        default_factory=list,
        description="All engineering symbol detections with bounding boxes"
    )
    relations: List[RawRelation] = Field(
        default_factory=list,
        description="Source→target tag relationship pairs"
    )
    geometry: RawGeometryLayout = Field(
        default_factory=lambda: RawGeometryLayout(traces=[], sheet_grids=[]),
        description="Pipeline traces and sheet grid zones"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Agent 1: Text Detection Agent (2-Layer Customizable Architecture)
# ──────────────────────────────────────────────────────────────────────────────

class TextDetectionAgent(BaseAgent):
    """
    2-Layer Customizable Text Extraction Agent:
      Layer 1 — OCR Reading (Local: PaddleOCR / PyMuPDF | Online: Gemini Vision / Qwen 2.5-VL)
      Layer 2 — Reasoning & Refinement Engine (Local: Regex Classifier | Online: Qwen 2.5, Gemini, OpenAI)
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running 2-Layer Text Detection Agent...")

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

        # LLM Provider override settings (e.g. Qwen 2.5 via DashScope / OpenRouter / Ollama)
        llm_provider = state.get("llm_provider") or ("qwen" if reasoning_engine == "qwen" else "gemini")
        llm_model = state.get("llm_model")
        llm_api_key = state.get("llm_api_key")
        llm_base_url = state.get("llm_base_url")

        from src.utils.tag_classifier import classify_paddle_results

        logger.info(
            f"TextDetectionAgent: drawing_type='{drawing_type}', "
            f"Layer 1 (OCR)='{ocr_engine}', Layer 2 (Reasoning)='{reasoning_engine}'"
        )

        # ── LAYER 1: OCR TEXT EXTRACTION ─────────────────────────────────────
        ocr_items: List[Dict[str, Any]] = []

        # Option A: PyMuPDF Vector Text Layer (Instant local)
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

        # Option B: Local PaddleOCR
        if not ocr_items and ocr_engine in ("paddle", "pdf_text", "got-ocr", "local"):
            try:
                from src.utils.preprocess import preprocess_for_ocr
                from src.utils.paddle_ocr import run_paddle_ocr
                processed_image = preprocess_for_ocr(raw_image)
                logger.info("Layer 1: Running local PaddleOCR engine...")
                paddle_items = run_paddle_ocr(processed_image)
                if paddle_items:
                    logger.info(f"Layer 1: PaddleOCR extracted {len(paddle_items)} text items.")
                    ocr_items = paddle_items
            except Exception as paddle_err:
                logger.warning(f"Local PaddleOCR extraction failed ({paddle_err}).")

        # Option C: Online Gemini Vision / Qwen 2.5-VL OCR
        if not ocr_items or ocr_engine in ("gemini_ocr", "qwen_ocr", "online_ocr"):
            logger.info(f"Layer 1: Running Online Vision OCR ({ocr_engine})...")
            try:
                prompt_ocr = (
                    "Extract all text labels, tag numbers, coordinates, and notes visible on this drawing.\n"
                    "Return a JSON list of items with text, confidence, and pos_x, pos_y."
                )
                raw_ocr_res = self.invoke_text(
                    prompt=prompt_ocr,
                    image_path=raw_image,
                    provider="qwen" if ocr_engine == "qwen_ocr" else "gemini",
                    model_name=llm_model,
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                )
                # Parse fallback
                logger.info("Layer 1 Online OCR response received.")
            except Exception as online_ocr_err:
                logger.warning(f"Online OCR engine failed ({online_ocr_err}).")

        # ── LAYER 2: REASONING & STRUCTURING ENGINE ───────────────────────────

        # Option A: Rule-Based Classifier (Local Offline Regex)
        if reasoning_engine == "rule_based" or (local_mode and reasoning_engine not in ("qwen", "gemini", "openai")):
            logger.info("Layer 2: Executing Local Rule-Based Classifier (zero LLM tokens)...")
            structured = classify_paddle_results(ocr_items, drawing_type=drawing_type)
            logger.info(f"Layer 2: Rule-based classifier produced {len(structured)} structured items.")
            return {"extracted_entities": {"text_elements": structured}}

        # Option B: Online LLM Deep Reasoning Engine (Qwen 2.5, Gemini, OpenAI, etc.)
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
                "4. FIND MISSING TAGS/ENTITIES: Infer missing tags or equipment referenced in callouts or note blocks.\n"
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
# Agent 2: Unified Vision Agent (Symbols, Relations, Geometry)
# ──────────────────────────────────────────────────────────────────────────────

class UnifiedVisionAgent(BaseAgent):
    """
    Consolidated single VLM call agent for symbols, relations, and geometry.
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Unified Vision Agent...")

        use_mocks = state.get("use_mocks", False)
        if use_mocks:
            return {
                "extracted_entities": {
                    "symbols": MOCK_SYMBOLS,
                    "relations": MOCK_RELATIONS,
                    "geometry": {"traces": [], "sheet_grids": ["B5", "C9", "D10"]},
                }
            }

        meta = state.get("metadata", {})
        pages = meta.get("rasterized_pages", state.get("raw_documents", []))
        raw_documents = state.get("raw_documents", [])
        if not pages and not raw_documents:
            return {"extracted_entities": {"symbols": [], "relations": [], "geometry": {}}}

        raw_image = pages[0] if pages else raw_documents[0]
        local_mode = state.get("local_mode", False)

        llm_provider = state.get("llm_provider")
        llm_model = state.get("llm_model")
        llm_api_key = state.get("llm_api_key")
        llm_base_url = state.get("llm_base_url")

        if local_mode and not llm_provider:
            logger.info("Local Mode: skipping API visual symbol extraction. Returning empty symbol set.")
            return {"extracted_entities": {"symbols": [], "relations": [], "geometry": {"traces": [], "sheet_grids": []}}}

        drawing_type = meta.get("drawing_type", "PID")
        symbol_vocab = _get_symbol_vocab(drawing_type)
        dt_label = drawing_type.replace('_', ' ')

        unified_prompt = (
            f"You are a computer vision and engineering analysis system examining a high-resolution "
            f"{dt_label} engineering drawing. Perform THREE tasks simultaneously:\n\n"
            "TASK A — SYMBOL DETECTION:\n"
            f"Identify all engineering graphical symbols found in this {dt_label}. For each symbol provide:\n"
            f"  - symbol_type: choose from relevant types including: {symbol_vocab}.\n"
            "  - inferred_tag: nearest readable tag ID if visible.\n"
            "  - ymin, xmin, ymax, xmax: normalized bounding box [0.0–1.0].\n\n"
            "TASK B — RELATIONSHIP EXTRACTION:\n"
            "Identify source→target engineering relationships:\n"
            "  - MONITORS: instrument or sensor monitors a line or equipment.\n"
            "  - INSTALLED_ON: component installed on a specific line or equipment.\n"
            "  - CONNECTS_TO: pipe, cable or conductor connected to equipment.\n"
            "  - FEEDS: panel or source feeds downstream equipment.\n"
            "  - EARTHED_TO: earthing connection between equipment and earth point.\n"
            "Return source_tag, target_tag, rel_type for each.\n\n"
            "TASK C — GEOMETRY LAYOUT:\n"
            "List the margin grid sectors (e.g., B5, C9, D10) visible in the drawing border.\n"
            "Also trace any named pipe runs or cable routes that cross multiple grid zones with their path coordinates.\n\n"
            "Return all findings in the structured JSON format requested."
        )

        try:
            result = self.invoke_structured(
                schema=UnifiedExtractionResult,
                prompt=unified_prompt,
                image_path=raw_image,
                image_uri=meta.get("primary_page_uri"),
                image_mime=meta.get("primary_page_mime", "image/png"),
                provider=llm_provider,
                model_name=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
            )

            symbols = [s.model_dump() for s in result.symbols]
            relations = [r.model_dump() for r in result.relations]
            geometry = result.geometry.model_dump()

            logger.info(f"Unified Vision Agent extracted: {len(symbols)} symbols, {len(relations)} relations.")
            return {"extracted_entities": {"symbols": symbols, "relations": relations, "geometry": geometry}}
        except Exception as err:
            logger.warning(f"Unified Vision Agent failed ({err}). Returning empty set.")
            return {"extracted_entities": {"symbols": [], "relations": [], "geometry": {"traces": [], "sheet_grids": []}}}
