"""
Thread Manager for SID-AI.
Executes extraction workflows asynchronously in background threads,
supporting live progress reporting, cancellation, and SQLite persistence.
"""
import os
import time
import logging
import threading
import traceback
from typing import Dict, Any, Optional

from src.graph import create_workflow
from src.state import GraphState
from src.models import UniversalEngineeringGraph
from src.db import (
    create_thread,
    update_thread_status,
    add_log,
    get_thread,
    get_all_threads,
    delete_thread,
)

logger = logging.getLogger(__name__)

# Memory map for active thread cancellation events and thread objects
_ACTIVE_THREADS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def start_extraction_thread(thread_id: str, initial_state: GraphState, filename: str) -> str:
    """
    Spawns a background thread to execute the extraction workflow asynchronously.
    """
    config_dict = {
        "raw_documents": initial_state.get("raw_documents", []),
        "ocr_engine": initial_state.get("ocr_engine"),
        "reasoning_engine": initial_state.get("reasoning_engine"),
        "llm_provider": initial_state.get("llm_provider"),
        "llm_model": initial_state.get("llm_model"),
        "use_mocks": initial_state.get("use_mocks"),
        "local_mode": initial_state.get("local_mode"),
        "max_re_extractions": initial_state.get("max_re_extractions", 3),
    }

    create_thread(thread_id=thread_id, filename=filename, config_dict=config_dict)

    cancel_event = threading.Event()
    t = threading.Thread(
        target=_run_workflow_worker,
        args=(thread_id, initial_state, cancel_event),
        daemon=True,
    )

    with _LOCK:
        _ACTIVE_THREADS[thread_id] = {
            "thread": t,
            "cancel_event": cancel_event,
        }

    t.start()
    return thread_id


def cancel_extraction_thread(thread_id: str):
    """
    Interrupts and cancels a running thread immediately.
    """
    with _LOCK:
        active = _ACTIVE_THREADS.get(thread_id)
        if active:
            active["cancel_event"].set()

    update_thread_status(
        thread_id=thread_id,
        status="CANCELLED",
        progress=1.0,
        current_step="Cancelled by User",
        error_message="Process was manually interrupted by user.",
    )
    add_log(thread_id, "Cancellation", "Process was manually cancelled by user.", log_level="WARNING")


def is_thread_active(thread_id: str) -> bool:
    with _LOCK:
        active = _ACTIVE_THREADS.get(thread_id)
        if active and active["thread"].is_alive():
            return True
    return False


def _run_workflow_worker(thread_id: str, initial_state: GraphState, cancel_event: threading.Event):
    """
    Worker function executed in the background thread.
    """
    logger.info(f"Background worker started for thread '{thread_id}'")
    update_thread_status(
        thread_id=thread_id,
        status="RUNNING",
        progress=0.10,
        current_step="Initializing Workflow Graph",
    )
    add_log(thread_id, "Pipeline Started", "Initialized workflow state graph.")

    try:
        if cancel_event.is_set():
            return

        workflow = create_workflow()
        app = workflow.compile()

        step_progress_map = {
            "ingest": (0.20, "Document Ingestion & Page Rasterization"),
            "context_loader": (0.30, "Loading Reference Context & Specs"),
            "supervisor": (0.40, "Supervisor Agent Strategy Dispatch"),
            "text_detection": (0.55, "Layer 1 OCR & Layer 2 Reasoning Engine"),
            "unified_vision": (0.65, "Unified Vision Symbol & Geometry Analysis"),
            "compiler": (0.75, "Universal Engineering Object Compiler"),
            "validation": (0.85, "Quality Assurance Rules Validation"),
            "completeness": (0.90, "Evaluating Graph Completeness"),
            "re_extractor": (0.93, "Focused Visual Re-Extraction"),
            "output_generator": (0.98, "Generating Excel, XML, JSON & CSV Deliverables"),
        }

        current_state = dict(initial_state)

        for output in app.stream(initial_state):
            if cancel_event.is_set():
                logger.info(f"Cancellation detected for thread '{thread_id}'")
                update_thread_status(
                    thread_id=thread_id,
                    status="CANCELLED",
                    progress=1.0,
                    current_step="Cancelled by User",
                    error_message="Process was manually interrupted by user.",
                )
                add_log(thread_id, "Cancellation", "Process execution cancelled by user.", log_level="WARNING")
                return

            for node_name, node_state_update in output.items():
                if isinstance(node_state_update, dict):
                    current_state.update(node_state_update)

                prog, desc = step_progress_map.get(node_name, (0.50, f"Running node {node_name}"))
                logger.info(f"Thread '{thread_id}' -> Node '{node_name}' ({prog*100:.0f}%): {desc}")

                meta = current_state.get("metadata", {})
                dt = meta.get("drawing_type")
                disc = meta.get("discipline")

                update_thread_status(
                    thread_id=thread_id,
                    status="RUNNING",
                    progress=prog,
                    current_step=desc,
                    drawing_type=dt,
                    discipline=disc,
                )
                add_log(thread_id, node_name.replace("_", " ").title(), f"Completed stage: {desc}")

        if cancel_event.is_set():
            return

        final_meta = current_state.get("metadata", {})
        final_graph = current_state.get("engineering_graph")

        serializable_state = dict(current_state)
        serializable_state["llm_api_key"] = None  # Sanitize API keys from DB
        if final_graph and isinstance(final_graph, UniversalEngineeringGraph):
            serializable_state["engineering_graph"] = final_graph.model_dump()

        update_thread_status(
            thread_id=thread_id,
            status="COMPLETED",
            progress=1.0,
            current_step="Completed Successfully",
            result_dict=serializable_state,
            drawing_type=final_meta.get("drawing_type", "GENERIC"),
            discipline=final_meta.get("discipline", "Unknown"),
        )
        add_log(thread_id, "Completed", "Extraction pipeline finished successfully. Deliverables generated.")
        logger.info(f"Thread '{thread_id}' completed successfully.")

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Thread '{thread_id}' failed: {e}\n{tb}")
        update_thread_status(
            thread_id=thread_id,
            status="FAILED",
            progress=1.0,
            current_step="Execution Failed",
            error_message=str(e),
            error_traceback=tb,
        )
        add_log(thread_id, "Error", f"Execution failed: {e}", log_level="ERROR")

    finally:
        with _LOCK:
            _ACTIVE_THREADS.pop(thread_id, None)
