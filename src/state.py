from typing import List, Dict, Any, TypedDict, Optional, Annotated, Set
from src.models import UniversalEngineeringGraph

def merge_entities(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Reducer function that merges extracted entity collections from parallel agents.
    """
    if left is None:
        left = {}
    if right is None:
        right = {}
        
    merged = left.copy()
    for key, value in right.items():
        if key in merged:
            if isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        else:
            merged[key] = value
    return merged

class GraphState(TypedDict):
    """
    Stores documents, metadata, engineering context, extracted entities, engineering
    graph, deliverables, validation reports, missing entities, revision history and final
    outputs.
    """
    # Raw inputs
    raw_documents: List[str]
    
    # Metadata extracted by Ingestion Agent
    metadata: Dict[str, Any]
    
    # Context loaded by Knowledge Loader (legends, client spec overrides)
    engineering_context: Dict[str, Any]
    
    # Temporary raw extraction lists from parallel visual agents
    extracted_entities: Annotated[Dict[str, Any], merge_entities]
    
    # Compiled, master structured Universal Engineering Graph
    engineering_graph: UniversalEngineeringGraph
    
    # Reports from Validation Agent (engineering consistency errors, duplicate tags, etc.)
    validation_reports: List[Dict[str, Any]]
    
    # Regions and item types identified as missing by Completeness Checker
    missing_entities: List[Dict[str, Any]]
    
    # History logs detailing incremental merges and re-extractions
    revision_history: List[Dict[str, Any]]
    
    # Paths to generated deliverables (Excel, CSV, JSON, XML formats)
    deliverables: Dict[str, str]
    
    # Loop counters for focused re-extraction attempts
    re_extraction_count: int
    max_re_extractions: int
    
    # Selected Layer 1 OCR Engine choice ('paddle', 'pdf_text', 'paddle_vl', 'llamaparse', 'gemini_ocr', 'qwen_ocr', 'qwen_37_ocr')
    ocr_engine: Optional[str]
    
    # Selected Layer 2 Reasoning Engine choice ('rule_based', 'qwen', 'qwen_37', 'gemini', 'openai')
    reasoning_engine: Optional[str]

    # Selected Symbol Recognition Engine choice ('vlm', 'glm_rfdetr', 'local', 'yolo_trained')
    symbol_engine: Optional[str]

    # Selected Pipeline Recognition Engine choice ('cv_vlm_tracer', 'vlm_tracer', 'proximity_tracer')
    pipeline_engine: Optional[str]
    
    # Custom Provider LLM Settings (for Qwen 2.5, Gemini, OpenAI, Ollama, Groq, vLLM)
    llm_provider: Optional[str]
    llm_model: Optional[str]
    llm_api_key: Optional[str]
    llm_base_url: Optional[str]
    
    # Toggle to load fallback mock databases on rate limits
    use_mocks: Optional[bool]
    
    # When True: run entire pipeline locally with zero LLM API calls.
    local_mode: Optional[bool]
    
    # List of tags already sent for re-extraction to prevent infinite validation loops
    re_extracted_targets: List[str]

    # Path to custom trained YOLOv8 weights (best.pt) for symbol detection
    # Set when symbol_engine='yolo_trained'. Falls back to DEFAULT_YOLO_WEIGHTS env var.
    yolo_weights_path: Optional[str]

    # YOLOv8 inference thresholds (tunable from Streamlit sidebar)
    yolo_conf: Optional[float]   # confidence threshold (default 0.25)
    yolo_iou: Optional[float]    # NMS IoU threshold (default 0.45)

    # Defect 1 Fix: OCR token set built from primary PDF \u2014 used by provenance filter
    # in CompilerAgent to drop cross-document contaminated relationship edges.
    ocr_token_set: Optional[Set[str]]

