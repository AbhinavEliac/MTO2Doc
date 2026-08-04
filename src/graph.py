"""
LangGraph Workflow Definition — Optimized Topology.

Topology change (Option C):
  OLD: supervisor → [text | symbol | relation | geometry] → compiler
       (4 parallel VLM image calls)

  NEW: supervisor → [text_detection | unified_vision] → compiler
       text_detection  = PaddleOCR (local) + LLM text-only classification (1 cheap call)
       unified_vision  = 1 VLM image call for symbols + relations + geometry

Token savings vs old design:
  ~75% fewer image tokens per run (4 image calls → 1 image call)
"""

import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from src.state import GraphState
from src.agents.ingestion import IngestionAgent
from src.agents.context_loader import ContextLoaderAgent
from src.agents.supervisor import SupervisorAgent
from src.agents.parallel_vision import TextDetectionAgent, UnifiedVisionAgent
from src.agents.compiler import CompilerAgent
from src.agents.validation import ValidationAgent
from src.agents.completeness import CompletenessAgent
from src.agents.re_extractor import ReExtractorAgent
from src.agents.output_generator import OutputGeneratorAgent

logger = logging.getLogger(__name__)


def route_completeness(state: GraphState) -> str:
    """
    Conditional edge router that checks if there are missing items.
    Routes to focused re-extraction or to output generation.
    """
    missing = state.get("missing_entities", [])
    count = state.get("re_extraction_count", 0)
    max_retries = state.get("max_re_extractions", 3)

    if missing and count < max_retries:
        logger.info(
            f"Loop Router: Found {len(missing)} missing items. "
            f"Triggering Focused Re-Extraction (Attempt {count + 1}/{max_retries})."
        )
        return "re_extract"
    else:
        logger.info("Loop Router: No missing items (or max retries reached). Proceeding to Output Deliverables.")
        return "generate_outputs"


def create_workflow() -> StateGraph:
    """
    Assembles and compiles the StateGraph workflow with the optimized
    two-node parallel vision topology.
    """
    workflow = StateGraph(GraphState)

    # Instantiate agents
    ingestion_agent = IngestionAgent()
    context_loader_agent = ContextLoaderAgent()
    supervisor_agent = SupervisorAgent()

    # Optimized parallel vision nodes
    text_agent = TextDetectionAgent()          # PaddleOCR → LLM text-only
    unified_vision_agent = UnifiedVisionAgent()  # 1 image call: symbols + relations + geometry

    compiler_agent = CompilerAgent()
    validation_agent = ValidationAgent()
    completeness_agent = CompletenessAgent()
    re_extractor_agent = ReExtractorAgent()
    output_agent = OutputGeneratorAgent()

    # ── 1. Define graph nodes ──────────────────────────────────────────────────
    workflow.add_node("ingest", ingestion_agent.run)
    workflow.add_node("context_loader", context_loader_agent.run)
    workflow.add_node("supervisor", supervisor_agent.run)

    # Two parallel vision nodes (was four)
    workflow.add_node("text_detection", text_agent.run)
    workflow.add_node("unified_vision", unified_vision_agent.run)

    # Backend pipeline
    workflow.add_node("compiler", compiler_agent.run)
    workflow.add_node("validation", validation_agent.run)
    workflow.add_node("completeness", completeness_agent.run)
    workflow.add_node("re_extractor", re_extractor_agent.run)
    workflow.add_node("output_generator", output_agent.run)

    # ── 2. Define edges ────────────────────────────────────────────────────────
    workflow.set_entry_point("ingest")

    workflow.add_edge("ingest", "context_loader")
    workflow.add_edge("context_loader", "supervisor")

    # Fork to two parallel nodes (was four)
    workflow.add_edge("supervisor", "text_detection")
    workflow.add_edge("supervisor", "unified_vision")

    # Join at compiler
    workflow.add_edge("text_detection", "compiler")
    workflow.add_edge("unified_vision", "compiler")

    # Serial validation pipeline
    workflow.add_edge("compiler", "validation")
    workflow.add_edge("validation", "completeness")

    # Conditional re-extraction loop
    workflow.add_conditional_edges(
        "completeness",
        route_completeness,
        {
            "re_extract": "re_extractor",
            "generate_outputs": "output_generator"
        }
    )

    workflow.add_edge("re_extractor", "compiler")
    workflow.add_edge("output_generator", END)

    return workflow
