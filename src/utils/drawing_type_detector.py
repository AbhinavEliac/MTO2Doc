"""
Drawing Type Detector — Universal Engineering Drawing Classification.

Strategy:
  1. Scan title block text for explicit type keywords (highest confidence).
  2. Score OCR tokens against per-discipline vocabulary dictionaries.
  3. Return the best-scoring DrawingType enum value.

Supported types:
  PID                — Piping & Instrumentation Diagram
  PFD                — Process Flow Diagram
  ELECTRICAL_LAYOUT  — Lighting / Power / General Electrical Layout
  EARTHING_LAYOUT    — Earthing / Grounding Layout
  SLD                — Single Line Diagram
  HVAC_LAYOUT        — HVAC / Mechanical Ventilation Layout
  STRUCTURAL_LAYOUT  — Structural / Civil Layout
  ISOMETRIC          — Pipe isometric drawing
  CABLE_SCHEDULE     — Cable routing / tray schedule
  GENERIC            — Fallback for anything not recognised
"""
from __future__ import annotations

import re
import logging
from enum import Enum
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Drawing Type Enum
# ──────────────────────────────────────────────────────────────────────────────

class DrawingType(str, Enum):
    PID                = "PID"
    PFD                = "PFD"
    ELECTRICAL_LAYOUT  = "ELECTRICAL_LAYOUT"
    EARTHING_LAYOUT    = "EARTHING_LAYOUT"
    SLD                = "SLD"
    HVAC_LAYOUT        = "HVAC_LAYOUT"
    STRUCTURAL_LAYOUT  = "STRUCTURAL_LAYOUT"
    ISOMETRIC          = "ISOMETRIC"
    CABLE_SCHEDULE     = "CABLE_SCHEDULE"
    GENERIC            = "GENERIC"


# ──────────────────────────────────────────────────────────────────────────────
# Title-block keyword triggers (highest priority — one match wins)
# ──────────────────────────────────────────────────────────────────────────────

_TITLE_KEYWORDS: List[tuple[re.Pattern, DrawingType]] = [
    # P&ID / PFD
    (re.compile(r'\bP\s*&\s*I\s*D\b|\bPIPING\s+(AND\s+)?INSTRUMENTATION\b', re.IGNORECASE), DrawingType.PID),
    (re.compile(r'\bPROCESS\s+FLOW\s+(DIAGRAM|CHART)\b|\bPFD\b', re.IGNORECASE), DrawingType.PFD),
    # Electrical & Earthing
    (re.compile(r'\bEARTHING\b|\bGROUNDING\b|\bEARTH\s+LAYOUT\b|\bEARTH\s+GRID\b|\bBONDING\b', re.IGNORECASE), DrawingType.EARTHING_LAYOUT),
    (re.compile(r'\bSINGLE\s+LINE\s+(DIAGRAM|SCHEMATIC)\b|\bSLD\b|\bONE\s+LINE\b', re.IGNORECASE), DrawingType.SLD),
    (re.compile(r'\bLIGHTING\b|\bELECTRICAL\s+LAYOUT\b|\bPOWER\s+LAYOUT\b|\bLUMINAIRE\b|\bLIGHTING\s+LAYOUT\b', re.IGNORECASE), DrawingType.ELECTRICAL_LAYOUT),
    (re.compile(r'\bCABLE\s+(SCHEDULE|TRAY|ROUTING|LAYOUT)\b', re.IGNORECASE), DrawingType.CABLE_SCHEDULE),
    # HVAC
    (re.compile(r'\bHVAC\b|\bVENTILATION\s+LAYOUT\b|\bAIR\s+HANDLING\b|\bDUCT\s+LAYOUT\b', re.IGNORECASE), DrawingType.HVAC_LAYOUT),
    # Structural / Civil
    (re.compile(r'\bSTRUCTURAL\s+LAYOUT\b|\bFRAMING\s+PLAN\b|\bFOUNDATION\s+PLAN\b|\bCIVIL\s+LAYOUT\b', re.IGNORECASE), DrawingType.STRUCTURAL_LAYOUT),
    # Isometric
    (re.compile(r'\bISOMETRIC\b|\bISO\s+DRAWING\b|\bPIPE\s+ISO\b', re.IGNORECASE), DrawingType.ISOMETRIC),
]

# ──────────────────────────────────────────────────────────────────────────────
# Token-level vocabulary scores (used when title-block match fails)
# ──────────────────────────────────────────────────────────────────────────────

_VOCAB_SCORES: Dict[DrawingType, Dict[str, int]] = {
    DrawingType.PID: {
        # Instruments
        'pit': 4, 'tit': 4, 'fit': 4, 'lit': 4, 'ait': 4, 'pdit': 4,
        'psv': 4, 'prv': 3, 'pdt': 3, 'pt': 2, 'ti': 2, 'fi': 2, 'li': 2,
        'pict': 3, 'frc': 3, 'vsd': 3,
        # Line tags
        'fc11s': 5, 'ac21s': 5, 'gc11s': 5,
        # Keywords
        'compressor': 3, 'separator': 3, 'cooler': 3, 'vessel': 3,
        'scrubber': 3, 'exchanger': 3, 'glycol': 2,
        'flare': 3, 'header': 2, 'nozzle': 2, 'drain': 2,
        'coalescer': 3, 'skid': 2,
    },
    DrawingType.PFD: {
        'stream': 5, 'mass balance': 5, 'flow rate': 4, 'temperature': 3,
        'pressure': 3, 'mole': 4, 'composition': 4, 'pfd': 6,
        'heat duty': 4, 'enthalpy': 4,
    },
    DrawingType.ELECTRICAL_LAYOUT: {
        # Luminaires & lighting
        'luminaire': 6, 'lighting': 5, 'light': 3,
        'fluorescent': 5, 'led': 3, 'fitting': 3, 'fixture': 3,
        # Panels / DB
        'db': 3, 'mdb': 5, 'ldb': 5, 'distribution board': 6,
        'panel': 3, 'mcb': 5, 'rccb': 5, 'acb': 5,
        # Electrical
        'socket': 4, 'outlet': 3, 'switch': 3, 'conduit': 4,
        'cable tray': 5, 'wiring': 4, 'circuit': 3,
        'kw': 2, 'kvah': 3, 'amps': 3, 'voltage': 3,
        # Layout keywords
        'electrical layout': 8, 'power layout': 7,
        'el.': 3, 'tl.': 3,  # elevation labels
    },
    DrawingType.EARTHING_LAYOUT: {
        'earthing': 8, 'grounding': 8, 'earth': 5,
        'earth bar': 8, 'earth pit': 8, 'earth rod': 7,
        'bonding': 6, 'conductor': 4, 'equipotential': 7,
        'copper tape': 6, 'copper conductor': 6,
        'earth electrode': 7, 'test link': 5,
        'eb': 4, 'ep': 4, 'bc': 3,
    },
    DrawingType.SLD: {
        'busbar': 7, 'bus bar': 7, 'transformer': 5, 'incomer': 6,
        'feeder': 5, 'breaker': 4, 'mccb': 6, 'vcb': 5, 'acb': 4,
        'relay': 4, 'ct': 3, 'pt': 3, 'mvdb': 7, 'lvdb': 7,
        'single line': 8, 'sld': 8, 'switchgear': 6,
        'kv': 4, 'mva': 5, 'fault level': 5,
    },
    DrawingType.HVAC_LAYOUT: {
        'ahu': 7, 'air handling unit': 8, 'vav': 6, 'fcu': 6,
        'diffuser': 6, 'grille': 5, 'duct': 5, 'ductwork': 6,
        'chiller': 5, 'cooling tower': 5, 'supply air': 5, 'return air': 5,
        'exhaust': 4, 'hvac': 8, 'ventilation': 5, 'cfm': 4, 'l/s': 3,
    },
    DrawingType.STRUCTURAL_LAYOUT: {
        'column': 4, 'beam': 4, 'slab': 5, 'footing': 5,
        'foundation': 5, 'rebar': 5, 'reinforcement': 5,
        'grid': 3, 'level': 2, 'elevation': 3,
        'structural': 6, 'framing': 6, 'civil': 4,
        'concrete': 4, 'steel': 3,
    },
    DrawingType.ISOMETRIC: {
        'isometric': 8, 'iso': 5, 'spool': 7,
        'elbow': 5, 'flange': 4, 'tee': 4, 'reducer': 4,
        'pipe support': 6, 'weld': 4, 'bw': 3,
        'north': 3, 'east': 3, 'up': 2,
    },
    DrawingType.CABLE_SCHEDULE: {
        'cable': 5, 'cable no': 7, 'cable schedule': 9, 'route': 4,
        'from panel': 5, 'to panel': 5, 'core': 4, 'mm2': 5,
        'armoured': 5, 'xlpe': 5, 'pvc': 3, 'length': 3,
        'tray': 4, 'conduit': 4, 'drum': 4,
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Main detection function
# ──────────────────────────────────────────────────────────────────────────────

def detect_drawing_type(
    ocr_items: Optional[List[Dict[str, Any]]] = None,
    title_text: Optional[str] = None,
    filename: Optional[str] = None,
) -> DrawingType:
    """
    Detect the drawing type from available signals.

    Args:
        ocr_items:  Raw OCR items (list of dicts with 'text' key) from PaddleOCR/PyMuPDF.
        title_text: Pre-extracted title string from the title block (if known).
        filename:   Original filename — used as last-resort hint.

    Returns:
        DrawingType enum member.
    """
    # 1. Build a combined text corpus
    corpus_parts: List[str] = []
    if title_text:
        corpus_parts.append(title_text)
    if filename:
        corpus_parts.append(filename.replace('_', ' ').replace('-', ' '))
    if ocr_items:
        for item in ocr_items:
            t = item.get('text', '')
            conf = item.get('confidence', 1.0)
            if conf >= 0.25 and t:
                corpus_parts.append(t)

    full_corpus = ' '.join(corpus_parts)

    # ── Pass 1: Title-block keyword exact match (high confidence) ────────────
    title_corpus = ' '.join(filter(None, [title_text, filename or '']))
    for pattern, dtype in _TITLE_KEYWORDS:
        if pattern.search(title_corpus):
            logger.info(f"Drawing type '{dtype.value}' detected via title-block keyword match.")
            return dtype

    # ── Pass 2: Full-corpus keyword match ─────────────────────────────────────
    for pattern, dtype in _TITLE_KEYWORDS:
        if pattern.search(full_corpus):
            logger.info(f"Drawing type '{dtype.value}' detected via full-corpus keyword match.")
            return dtype

    # ── Pass 3: Vocabulary scoring ────────────────────────────────────────────
    lower_corpus = full_corpus.lower()
    scores: Dict[DrawingType, int] = {dt: 0 for dt in DrawingType}

    for dtype, vocab in _VOCAB_SCORES.items():
        for token, weight in vocab.items():
            if token in lower_corpus:
                scores[dtype] += weight

    # Find the winner
    best_type = max(scores, key=lambda dt: scores[dt])
    best_score = scores[best_type]

    if best_score >= 5:  # Minimum confidence threshold
        logger.info(
            f"Drawing type '{best_type.value}' detected via vocabulary scoring "
            f"(score={best_score}). Runner-up scores: "
            + ', '.join(f"{dt.value}:{scores[dt]}" for dt in sorted(scores, key=lambda x: -scores[x])[:3])
        )
        return best_type

    logger.warning(
        f"Could not confidently detect drawing type (best_score={best_score}). "
        f"Defaulting to GENERIC."
    )
    return DrawingType.GENERIC


# ──────────────────────────────────────────────────────────────────────────────
# Human-readable labels and UI metadata per drawing type
# ──────────────────────────────────────────────────────────────────────────────

DRAWING_TYPE_LABELS: Dict[DrawingType, Dict[str, str]] = {
    DrawingType.PID: {
        "label": "Piping & Instrumentation Diagram (P&ID)",
        "discipline": "Process",
        "icon": "⚙️",
    },
    DrawingType.PFD: {
        "label": "Process Flow Diagram (PFD)",
        "discipline": "Process",
        "icon": "🔄",
    },
    DrawingType.ELECTRICAL_LAYOUT: {
        "label": "Electrical Layout Drawing",
        "discipline": "Electrical",
        "icon": "💡",
    },
    DrawingType.EARTHING_LAYOUT: {
        "label": "Earthing / Grounding Layout",
        "discipline": "Electrical",
        "icon": "⏚",
    },
    DrawingType.SLD: {
        "label": "Single Line Diagram (SLD)",
        "discipline": "Electrical",
        "icon": "⚡",
    },
    DrawingType.HVAC_LAYOUT: {
        "label": "HVAC / Ventilation Layout",
        "discipline": "Mechanical",
        "icon": "💨",
    },
    DrawingType.STRUCTURAL_LAYOUT: {
        "label": "Structural / Civil Layout",
        "discipline": "Civil/Structural",
        "icon": "🏗️",
    },
    DrawingType.ISOMETRIC: {
        "label": "Pipe Isometric Drawing",
        "discipline": "Process/Piping",
        "icon": "📐",
    },
    DrawingType.CABLE_SCHEDULE: {
        "label": "Cable Schedule / Routing",
        "discipline": "Electrical",
        "icon": "🔌",
    },
    DrawingType.GENERIC: {
        "label": "Engineering Drawing (Generic)",
        "discipline": "Multi-discipline",
        "icon": "📋",
    },
}
