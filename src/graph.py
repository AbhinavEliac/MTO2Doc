"""
LangGraph Workflow Definition — 3-Agent Parallel Perception Topology.

Perception Topology:
  supervisor → [text_recognition | symbol_recognition | pipeline_recognition] → compiler

1. text_recognition     : Layer 1 OCR (PaddleOCR / PaddleOCR-VL / LlamaParse) + Layer 2 Tag & Spec Parsing
2. symbol_recognition   : ISA-5.1 & Multi-discipline Symbol Bounding Box Detection (RF-DETR / GLM-OCR / VLM)
3. pipeline_recognition : Piping Runs, Line Tracing, Busbars & Connectivity Relationships
"""

import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from src.state import GraphState
from src.agents.ingestion import IngestionAgent
from src.agents.context_loader import ContextLoaderAgent
from src.agents.supervisor import SupervisorAgent
from src.agents.parallel_vision import (
    TextRecognitionAgent,
    SymbolRecognitionAgent,
    PipelineRecognitionAgent,
)
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
    Assembles and compiles the StateGraph workflow with the 3-agent
    parallel perception topology.
    """
    workflow = StateGraph(GraphState)

    # Instantiate agents
    ingestion_agent = IngestionAgent()
    context_loader_agent = ContextLoaderAgent()
    supervisor_agent = SupervisorAgent()

    # 3 Parallel Perception Agents
    text_recognition_agent = TextRecognitionAgent()
    symbol_recognition_agent = SymbolRecognitionAgent()
    pipeline_recognition_agent = PipelineRecognitionAgent()

    compiler_agent = CompilerAgent()
    validation_agent = ValidationAgent()
    completeness_agent = CompletenessAgent()
    re_extractor_agent = ReExtractorAgent()
    output_agent = OutputGeneratorAgent()

    # ── 1. Define graph nodes ──────────────────────────────────────────────────
    workflow.add_node("ingest", ingestion_agent.run)
    workflow.add_node("context_loader", context_loader_agent.run)
    workflow.add_node("supervisor", supervisor_agent.run)

    # 3 Parallel Perception Nodes
    workflow.add_node("text_recognition", text_recognition_agent.run)
    workflow.add_node("symbol_recognition", symbol_recognition_agent.run)
    workflow.add_node("pipeline_recognition", pipeline_recognition_agent.run)

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

    # Fork to 3 parallel perception nodes
    workflow.add_edge("supervisor", "text_recognition")
    workflow.add_edge("supervisor", "symbol_recognition")
    workflow.add_edge("supervisor", "pipeline_recognition")

    # Join at compiler
    workflow.add_edge("text_recognition", "compiler")
    workflow.add_edge("symbol_recognition", "compiler")
    workflow.add_edge("pipeline_recognition", "compiler")

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
