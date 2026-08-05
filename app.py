"""
SID-AI — Universal Engineering Drawing Intelligence Dashboard.

Supports thread persistence in SQLite, background extraction execution,
live progress tracking, cancel functionality, and historical error logs.
"""
import os
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import streamlit as st
import pandas as pd
from PIL import Image

from src.models import UniversalEngineeringGraph
from src.state import GraphState
from src.db import (
    init_db,
    get_all_threads,
    get_thread,
    delete_thread,
)
from src.thread_manager import (
    start_extraction_thread,
    cancel_extraction_thread,
    is_thread_active,
)

logger = logging.getLogger(__name__)

def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "N/A"
    sec = int(seconds)
    if sec < 60:
        return f"{seconds:.1f}s"
    m = sec // 60
    s = sec % 60
    return f"{m:02d}m {s:02d}s"

# Initialize SQLite Database on app load
init_db()

# ─── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SID-AI | Universal Engineering Drawing Intelligence",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Premium Styling ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-title {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
        font-weight: 400;
    }
    .metric-card {
        background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%);
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 5px solid #1a73e8;
        box-shadow: 0 2px 8px rgba(26,115,232,0.08);
        margin-bottom: 10px;
    }
    .metric-val {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a1a2e;
    }
    .metric-lbl {
        font-size: 0.78rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
    }
    .dtype-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        color: white;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 12px;
    }
    .discipline-chip {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a1a2e;
        border-bottom: 2px solid #e8f0fe;
        padding-bottom: 8px;
        margin: 24px 0 16px 0;
    }
    .thread-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
    }
    .status-completed { color: #2e7d32; font-weight: 600; }
    .status-running { color: #1565c0; font-weight: 600; }
    .status-failed { color: #c62828; font-weight: 600; }
    .status-cancelled { color: #e65100; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ─── App Header ────────────────────────────────────────────────────────────────
st.markdown("<div class='main-title'>⚙️ SID-AI</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Universal Engineering Drawing Intelligence — "
    "P&ID · Electrical · Earthing · SLD · HVAC · Structural · and more</div>",
    unsafe_allow_html=True,
)

# Fetch all saved threads from SQLite
all_threads = get_all_threads()

# Initialize session state for selected thread
if "active_thread_id" not in st.session_state and all_threads:
    st.session_state["active_thread_id"] = all_threads[0]["thread_id"]

# ─── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ 2-Layer Extraction Pipeline")

max_retries = st.sidebar.slider(
    "Maximum Re-Extraction Cycles",
    min_value=0, max_value=5, value=3,
    help="Number of times the supervisor crops and re-scans suspect areas.",
)

st.sidebar.markdown("### 🔤 Layer 1: OCR Reading Layer")
ocr_option = st.sidebar.selectbox(
    "1st Layer: OCR Text Engine",
    options=[
        "PaddleOCR (Local / Offline)",
        "PyMuPDF Vector Text (Local / Offline)",
        "Gemini Vision OCR (Online API)",
        "Qwen 2.5-VL / Vision API (Online)",
        "Qwen 3.7-VL / OpenRouter (Online)",
    ],
    index=0,
    help="Select the 1st layer OCR engine. PaddleOCR & PyMuPDF run locally offline.",
)
ocr_engine_map = {
    "PaddleOCR (Local / Offline)": "paddle",
    "PyMuPDF Vector Text (Local / Offline)": "pdf_text",
    "Gemini Vision OCR (Online API)": "gemini_ocr",
    "Qwen 2.5-VL / Vision API (Online)": "qwen_ocr",
    "Qwen 3.7-VL / OpenRouter (Online)": "qwen_37_ocr",
}
ocr_engine = ocr_engine_map.get(ocr_option, "paddle")

st.sidebar.markdown("### 🧠 Layer 2: Reasoning & Refinement Engine")
reasoning_option = st.sidebar.selectbox(
    "2nd Layer: Reasoning & Structuring",
    options=[
        "Rule-Based Regex Classifier (Local / Offline)",
        "Qwen 2.5 Reasoning Engine (OpenRouter / API)",
        "Qwen 3.7 Reasoning Engine (OpenRouter / API)",
        "Gemini 2.0 Flash Engine (Online / API)",
        "OpenAI GPT-4o Engine (Online / API)",
    ],
    index=1,
    help="Select the 2nd layer reasoning engine. Online engines fix OCR typos, find missing tags, map misplaced data, and generate clean JSON.",
)
reasoning_engine_map = {
    "Rule-Based Regex Classifier (Local / Offline)": "rule_based",
    "Qwen 2.5 Reasoning Engine (OpenRouter / API)": "qwen",
    "Qwen 3.7 Reasoning Engine (OpenRouter / API)": "qwen_37",
    "Gemini 2.0 Flash Engine (Online / API)": "gemini",
    "OpenAI GPT-4o Engine (Online / API)": "openai",
}
reasoning_engine = reasoning_engine_map.get(reasoning_option, "qwen")

llm_provider = "gemini"
llm_api_key = None
llm_base_url = None
llm_model = None

if reasoning_engine in ("qwen", "qwen_37", "openai") or ocr_engine in ("qwen_ocr", "qwen_37_ocr"):
    llm_provider = "qwen" if ("Qwen" in reasoning_option or "qwen" in ocr_engine) else "openai"
    with st.sidebar.expander(f"🔧 {llm_provider.upper()} / OpenRouter Settings", expanded=True):
        default_key = os.getenv("OPENROUTER_API_KEY", os.getenv("QWEN_API_KEY", os.getenv("OPENAI_API_KEY", "")))
        llm_api_key = st.text_input(
            "API Key",
            value=default_key,
            type="password",
            help="OpenRouter API Key (sk-or-v1-...) or OpenAI / DashScope key.",
        )
        default_endpoint = os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1") if llm_provider == "qwen" else "https://api.openai.com/v1"
        llm_base_url = st.text_input(
            "Base URL / Endpoint",
            value=default_endpoint,
            help="Custom endpoint URL (e.g. OpenRouter https://openrouter.ai/api/v1, DashScope, or local Ollama/vLLM)",
        )
        default_model = "qwen/qwen-3.7-vl" if ("3.7" in ocr_option or "3.7" in reasoning_option) else os.getenv("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct")
        llm_model = st.text_input(
            "Model Name",
            value=default_model,
            help="Model identifier e.g. qwen/qwen-3.7-vl, qwen/qwen-2.5-72b-instruct, qwen/qwen-2.5-vl-72b-instruct",
        )
elif reasoning_engine == "gemini":
    llm_provider = "gemini"
    llm_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

use_mocks = st.sidebar.checkbox(
    "Enable Demo Mock Fallbacks",
    value=False,
    help="Fall back to static mock data if rate limits or API errors occur.",
)

local_mode = st.sidebar.checkbox(
    "🔌 Force Full Offline Mode",
    value=False,
    help="Force local offline execution (PaddleOCR + Regex Classifier, zero API calls).",
)

if local_mode:
    st.sidebar.info("🔌 Full Offline Mode forced — PaddleOCR + Regex Classifier. Zero API tokens.")

st.sidebar.markdown("---")
st.sidebar.markdown("## 🧵 Generation Threads")

if all_threads:
    with st.sidebar.container(height=260):
        for t in all_threads:
            tid = t["thread_id"]
            status = t["status"]
            fname = t.get("filename", "Drawing")
            dt_label = t.get("drawing_type", "GENERIC")
            created = t.get("created_at", "")[:19].replace("T", " ")

            status_icon = "🟢" if status == "COMPLETED" else "🔵" if status == "RUNNING" else "❌" if status == "FAILED" else "⛔"
            prog_str = f" ({int(t.get('progress', 0)*100)}%)" if status == "RUNNING" else ""

            col_t1, col_t2 = st.columns([0.78, 0.22])
            with col_t1:
                button_label = f"{status_icon} {fname[:16]}...{prog_str}"
                is_active = (st.session_state.get("active_thread_id") == tid)
                if st.button(
                    button_label,
                    key=f"btn_thread_{tid}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    help=f"Type: {dt_label} | Status: {status} | Created: {created}",
                ):
                    st.session_state["active_thread_id"] = tid
                    st.rerun()

            with col_t2:
                if st.button("🗑️", key=f"del_thread_{tid}", help=f"Delete thread '{fname}' and its log"):
                    delete_thread(tid)
                    if st.session_state.get("active_thread_id") == tid:
                        remaining = [x for x in all_threads if x["thread_id"] != tid]
                        st.session_state["active_thread_id"] = remaining[0]["thread_id"] if remaining else None
                    st.rerun()
else:
    st.sidebar.info("No previous extraction threads found.")

# ─── Main Content Tabs: Dashboard vs History ───────────────────────────────────
tab_main_dashboard, tab_main_history = st.tabs([
    "📊 Current Extraction Dashboard",
    "📜 Generation History & Error Logs",
])

# ─── TAB 1: CURRENT EXTRACTION DASHBOARD ───────────────────────────────────────
with tab_main_dashboard:
    # Upload Section
    st.markdown("<div class='section-header'>📂 Document Upload & Extraction Trigger</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        uploaded_drawing = st.file_uploader(
            "Upload Engineering Drawing (PDF, PNG, JPG)",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Upload any engineering drawing — P&ID, Electrical Layout, Earthing, SLD, HVAC, Structural, etc.",
        )

    with col2:
        uploaded_refs = st.file_uploader(
            "Upload Legend Sheets or Reference Documents (Optional)",
            type=["pdf", "png", "jpg"],
            accept_multiple_files=True,
            help="Provide symbol legends, client coding standards, or specification sheets.",
        )

    run_pipeline = st.button(
        "🚀 Run Extraction Pipeline",
        type="primary",
        disabled=(uploaded_drawing is None),
    )

    if run_pipeline and uploaded_drawing:
        temp_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(temp_dir, exist_ok=True)

        drawing_path = os.path.join(temp_dir, uploaded_drawing.name)
        with open(drawing_path, "wb") as f:
            f.write(uploaded_drawing.read())

        ref_paths = []
        for ref in uploaded_refs:
            ref_path = os.path.join(temp_dir, ref.name)
            with open(ref_path, "wb") as f:
                f.write(ref.read())
            ref_paths.append(ref_path)

        raw_docs = [drawing_path] + ref_paths

        new_thread_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        initial_state: GraphState = {
            "raw_documents": raw_docs,
            "metadata": {},
            "engineering_context": {},
            "extracted_entities": {
                "text_elements": [],
                "symbols": [],
                "relations": [],
                "geometry": {},
            },
            "engineering_graph": None,
            "validation_reports": [],
            "missing_entities": [],
            "revision_history": [],
            "deliverables": {},
            "re_extraction_count": 0,
            "max_re_extractions": max_retries,
            "ocr_engine": ocr_engine,
            "reasoning_engine": reasoning_engine,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_api_key": llm_api_key,
            "llm_base_url": llm_base_url,
            "use_mocks": use_mocks,
            "local_mode": local_mode or (reasoning_engine == "rule_based" and ocr_engine in ("paddle", "pdf_text")),
            "re_extracted_targets": [],
        }

        # Start asynchronous background thread
        start_extraction_thread(
            thread_id=new_thread_id,
            initial_state=initial_state,
            filename=uploaded_drawing.name,
        )
        st.session_state["active_thread_id"] = new_thread_id
        st.rerun()

    # Render selected thread dashboard
    active_id = st.session_state.get("active_thread_id")
    if active_id:
        active_thread = get_thread(active_id)
        if active_thread:
            status = active_thread.get("status")
            progress = active_thread.get("progress", 0.0)
            current_step = active_thread.get("current_step", "")
            fname = active_thread.get("filename", "")

            # ── Active Process & Progress Bar ─────────────────────────────────
            if status == "RUNNING" or status == "QUEUED":
                st.markdown("<div class='section-header'>⚡ Active Subprocess Progress</div>", unsafe_allow_html=True)
                
                # Compute live duration
                elapsed_sec = active_thread.get("duration_sec", 0.0) or 0.0
                try:
                    c_time = datetime.fromisoformat(active_thread.get("created_at"))
                    elapsed_sec = (datetime.now() - c_time).total_seconds()
                except Exception:
                    pass

                col_p1, col_p2 = st.columns([0.8, 0.2])
                with col_p1:
                    st.progress(progress)
                    st.info(
                        f"⏳ **Active Subprocess:** `{current_step}` ({int(progress*100)}%) — "
                        f"⏱️ **Timer:** `{format_duration(elapsed_sec)}` — File: *{fname}*"
                    )
                with col_p2:
                    if st.button("🛑 Cancel Process", type="secondary", use_container_width=True):
                        cancel_extraction_thread(active_id)
                        st.rerun()

                # Auto refresh UI while processing
                time.sleep(1.5)
                st.rerun()

            elif status == "CANCELLED":
                st.warning(f"⛔ Extraction process for '{fname}' was cancelled by user.")
            elif status == "FAILED":
                st.error(f"❌ Extraction process for '{fname}' failed: {active_thread.get('error_message')}")

            # ── Dashboard Results Rendering ───────────────────────────────────
            result_state = active_thread.get("result")
            if result_state:
                metadata = result_state.get("metadata", {})
                raw_graph_data = result_state.get("engineering_graph")

                graph = None
                if raw_graph_data:
                    if isinstance(raw_graph_data, dict):
                        graph = UniversalEngineeringGraph(**raw_graph_data)
                    else:
                        graph = raw_graph_data

                reports = result_state.get("validation_reports", [])
                deliverables = result_state.get("deliverables", {})
                re_runs = result_state.get("re_extraction_count", 0)
                revision_history = result_state.get("revision_history", [])

                drawing_type = active_thread.get("drawing_type") or metadata.get("drawing_type", "GENERIC")
                discipline = active_thread.get("discipline") or metadata.get("discipline", "Unknown")

                from src.utils.drawing_type_detector import DRAWING_TYPE_LABELS, DrawingType
                try:
                    dtype_enum = DrawingType(drawing_type)
                    dtype_info = DRAWING_TYPE_LABELS.get(dtype_enum, {"label": drawing_type, "icon": "📋", "discipline": discipline})
                except Exception:
                    dtype_info = {"label": drawing_type, "icon": "📋", "discipline": discipline}

                st.markdown(
                    f"<div class='dtype-badge'>{dtype_info['icon']} {dtype_info['label']}"
                    f"<span class='discipline-chip'>{discipline}</span></div>",
                    unsafe_allow_html=True,
                )

                # Metadata Block
                st.markdown("<div class='section-header'>📋 Drawing Metadata</div>", unsafe_allow_html=True)
                col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
                with col_m1:
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Drawing Title</div><div class='metric-val'>{metadata.get('title', 'N/A')}</div></div>", unsafe_allow_html=True)
                with col_m2:
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Drawing Number</div><div class='metric-val'>{metadata.get('drawing_number', 'N/A')}</div></div>", unsafe_allow_html=True)
                with col_m3:
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Revision</div><div class='metric-val'>{metadata.get('revision', 'N/A')}</div></div>", unsafe_allow_html=True)
                with col_m4:
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Discipline</div><div class='metric-val'>{metadata.get('discipline', 'N/A')}</div></div>", unsafe_allow_html=True)
                with col_m5:
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Client</div><div class='metric-val'>{metadata.get('client_name', 'N/A')}</div></div>", unsafe_allow_html=True)
                with col_m6:
                    proc_time = format_duration(active_thread.get("duration_sec"))
                    st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Processing Time</div><div class='metric-val'>{proc_time}</div></div>", unsafe_allow_html=True)

                # Extracted Data Tabs
                if graph:
                    st.markdown("<div class='section-header'>📊 Extracted Data</div>", unsafe_allow_html=True)
                    dt = drawing_type.upper()

                    if dt in ('PID', 'PFD', 'ISOMETRIC'):
                        tab_line, tab_inst, tab_valve, tab_psv, tab_eq = st.tabs([
                            f"📏 Line List ({len(graph.lines)})",
                            f"🔵 Instrument List ({len(graph.instruments)})",
                            f"🔧 Valve List ({len(graph.valves)})",
                            f"🛡️ Safety Relief Valves ({len(graph.safety_relief_valves)})",
                            f"⚙️ Equipment List ({len(graph.equipment)})",
                        ])
                        with tab_line:
                            st.subheader("Line List (Piping Segments)")
                            if graph.lines:
                                df = pd.DataFrame([l.model_dump() for l in graph.lines]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No piping lines detected.")

                        with tab_inst:
                            st.subheader("Instrument List")
                            if graph.instruments:
                                df = pd.DataFrame([i.model_dump() for i in graph.instruments]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No instruments detected.")

                        with tab_valve:
                            st.subheader("Manual Valve List")
                            if graph.valves:
                                df = pd.DataFrame([v.model_dump() for v in graph.valves]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No valves detected.")

                        with tab_psv:
                            st.subheader("Safety Relief Valve List")
                            if graph.safety_relief_valves:
                                df = pd.DataFrame([p.model_dump() for p in graph.safety_relief_valves]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No safety relief valves detected.")

                        with tab_eq:
                            st.subheader("Equipment List")
                            if graph.equipment:
                                df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No equipment detected.")

                    elif dt == 'ELECTRICAL_LAYOUT':
                        tab_lum, tab_panel, tab_cable, tab_eq, tab_ann = st.tabs([
                            f"💡 Luminaires ({len(graph.luminaires)})",
                            f"⚡ Distribution Boards ({len(graph.panels)})",
                            f"🔌 Cables & Circuits ({len(graph.cables)})",
                            f"⚙️ Equipment ({len(graph.equipment)})",
                            f"📝 Annotations ({len(graph.annotations)})",
                        ])
                        with tab_lum:
                            st.subheader("Luminaire / Lighting Fitting List")
                            if graph.luminaires:
                                df = pd.DataFrame([l.model_dump() for l in graph.luminaires]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No luminaires detected.")

                        with tab_panel:
                            st.subheader("Distribution Boards & Panels")
                            if graph.panels:
                                df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No panels/DBs detected.")

                        with tab_cable:
                            st.subheader("Cables & Circuits")
                            if graph.cables:
                                df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No cables/circuits detected.")

                        with tab_eq:
                            st.subheader("Equipment List")
                            if graph.equipment:
                                df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No equipment detected.")

                        with tab_ann:
                            st.subheader("Elevation Labels & Annotations")
                            if graph.annotations:
                                df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No annotations detected.")

                    elif dt == 'EARTHING_LAYOUT':
                        tab_earth, tab_eq, tab_ann = st.tabs([
                            f"⏚ Earthing Components ({len(graph.earthing_components)})",
                            f"⚙️ Equipment / Structures ({len(graph.equipment)})",
                            f"📝 Notes & Elevations ({len(graph.annotations)})",
                        ])
                        with tab_earth:
                            st.subheader("Earthing Components (Bars, Pits, Conductors)")
                            if graph.earthing_components:
                                df = pd.DataFrame([e.model_dump() for e in graph.earthing_components]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No earthing components detected.")

                        with tab_eq:
                            st.subheader("Earthed Equipment & Structures")
                            if graph.equipment:
                                df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No equipment detected.")

                        with tab_ann:
                            st.subheader("Installation Notes & Elevation Labels")
                            if graph.annotations:
                                df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No annotations detected.")

                    elif dt == 'SLD':
                        tab_panel, tab_cable, tab_eq, tab_ann = st.tabs([
                            f"🏗️ Switchgear & Panels ({len(graph.panels)})",
                            f"🔌 Feeders & Breakers ({len(graph.cables)})",
                            f"⚙️ Loads & Equipment ({len(graph.equipment)})",
                            f"📝 Ratings & Notes ({len(graph.annotations)})",
                        ])
                        with tab_panel:
                            st.subheader("Switchgear, Busbars & Panels")
                            if graph.panels:
                                df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No panels detected.")

                        with tab_cable:
                            st.subheader("Feeders & Circuit Breakers")
                            if graph.cables:
                                df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No feeders/breakers detected.")

                        with tab_eq:
                            st.subheader("Loads & Equipment")
                            if graph.equipment:
                                df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No equipment detected.")

                        with tab_ann:
                            st.subheader("Ratings & Notes")
                            if graph.annotations:
                                df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No annotations detected.")

                    elif dt == 'CABLE_SCHEDULE':
                        tab_cable, tab_panel, tab_ann = st.tabs([
                            f"🔌 Cable Schedule ({len(graph.cables)})",
                            f"⚡ Panels ({len(graph.panels)})",
                            f"📝 Notes ({len(graph.annotations)})",
                        ])
                        with tab_cable:
                            if graph.cables:
                                df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No cables detected.")
                        with tab_panel:
                            if graph.panels:
                                df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No panels detected.")
                        with tab_ann:
                            if graph.annotations:
                                df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No annotations detected.")

                    else:
                        tab_eq, tab_generic, tab_ann = st.tabs([
                            f"⚙️ Equipment ({len(graph.equipment)})",
                            f"🔩 Components ({len(graph.generic_components)})",
                            f"📝 Notes & Annotations ({len(graph.annotations)})",
                        ])
                        with tab_eq:
                            st.subheader("Equipment List")
                            if graph.equipment:
                                df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No equipment detected.")

                        with tab_generic:
                            st.subheader("Detected Components")
                            if graph.generic_components:
                                df = pd.DataFrame([g.model_dump() for g in graph.generic_components]).drop(columns=["coordinates"], errors="ignore")
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No components detected.")

                        with tab_ann:
                            st.subheader("Annotations & Notes")
                            if graph.annotations:
                                df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                                st.dataframe(df, use_container_width=True)
                            else:
                                st.info("No annotations detected.")

                    # Relationships
                    if graph.relationships:
                        with st.expander(f"🔗 Engineering Relationships ({len(graph.relationships)})"):
                            df = pd.DataFrame([r.model_dump() for r in graph.relationships])
                            st.dataframe(df, use_container_width=True)

                # Quality Assurance & Process Log
                st.markdown("<div class='section-header'>🔍 Quality Assurance & Process Log</div>", unsafe_allow_html=True)
                col_v1, col_v2 = st.columns(2)

                with col_v1:
                    st.subheader("Consistency Errors & Warnings")
                    if reports:
                        for r in reports:
                            is_err = (r.get("severity") == "ERROR")
                            icon = "❌" if is_err else "⚠️"
                            bg_color = "#FDF2F2" if is_err else "#FEFBF0"
                            border_color = "#F05252" if is_err else "#FACA15"
                            title_color = "#7F1D1D" if is_err else "#713F12"
                            msg_color = "#991B1B" if is_err else "#854D0E"
                            st.markdown(f"""
                            <div style='background-color: {bg_color}; padding: 12px; border-left: 5px solid {border_color}; border-radius: 6px; margin-bottom: 10px; font-family: sans-serif;'>
                                <strong style='color: {title_color}; font-size: 0.95rem;'>{icon} {r.get('rule_id', 'RULE')} (Target: {r.get('target_tag', 'N/A')})</strong><br/>
                                <span style='font-size: 0.9rem; color: {msg_color}; line-height: 1.4; display: block; margin-top: 4px;'>{r.get('message')}</span>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.success("✓ No validation discrepancies identified.")

                with col_v2:
                    st.subheader("Extraction Process History")
                    st.markdown(f"**Re-extraction Loops:** `{re_runs}` / `{max_retries}`")
                    st.markdown("**Revision History:**")
                    for log in revision_history:
                        action = log.get("action", str(log))
                        st.markdown(f"- {action}")

                # Export & Download
                st.markdown("<div class='section-header'>📥 Export & Download</div>", unsafe_allow_html=True)
                st.markdown("Download deliverables formatted for standard engineering platforms:")

                col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns(5)
                if deliverables:
                    if "excel" in deliverables and os.path.exists(deliverables["excel"]):
                        with open(deliverables["excel"], "rb") as f:
                            col_d1.download_button(
                                "📊 Excel Deliverables",
                                data=f.read(),
                                file_name="engineering_deliverables.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                            )
                    if "json_graph" in deliverables and os.path.exists(deliverables["json_graph"]):
                        with open(deliverables["json_graph"], "rb") as f:
                            col_d2.download_button(
                                "🕸️ JSON Graph",
                                data=f.read(),
                                file_name="master_graph.json",
                                mime="application/json",
                                use_container_width=True,
                            )
                    if "aveva_xml" in deliverables and os.path.exists(deliverables["aveva_xml"]):
                        with open(deliverables["aveva_xml"], "rb") as f:
                            col_d3.download_button(
                                "📐 AVEVA XML",
                                data=f.read(),
                                file_name="aveva_diagrams_export.xml",
                                mime="application/xml",
                                use_container_width=True,
                            )
                    if "comos_json" in deliverables and os.path.exists(deliverables["comos_json"]):
                        with open(deliverables["comos_json"], "rb") as f:
                            col_d4.download_button(
                                "🔧 COMOS JSON",
                                data=f.read(),
                                file_name="comos_hierarchy_export.json",
                                mime="application/json",
                                use_container_width=True,
                            )
                    if "sppid_csv" in deliverables and os.path.exists(deliverables["sppid_csv"]):
                        with open(deliverables["sppid_csv"], "rb") as f:
                            col_d5.download_button(
                                "🗃️ SmartPlant CSV",
                                data=f.read(),
                                file_name="sppid_import_tables.csv",
                                mime="text/csv",
                                use_container_width=True,
                            )
                else:
                    st.info("No export files generated yet for this thread.")
    else:
        st.info("No active thread selected. Upload a drawing or select a thread from the sidebar.")

# ─── TAB 2: GENERATION HISTORY & ERROR LOGS ────────────────────────────────────
with tab_main_history:
    st.markdown("<div class='section-header'>📜 Generation History & Execution Logs</div>", unsafe_allow_html=True)

    threads = get_all_threads()
    if not threads:
        st.info("No generation threads recorded in SQLite history.")
    else:
        completed_count = sum(1 for t in threads if t["status"] == "COMPLETED")
        failed_count = sum(1 for t in threads if t["status"] == "FAILED")
        cancelled_count = sum(1 for t in threads if t["status"] == "CANCELLED")

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("Total Executions", len(threads))
        col_s2.metric("Successful", completed_count)
        col_s3.metric("Failed", failed_count)
        col_s4.metric("Cancelled", cancelled_count)

        st.markdown("### Execution Threads Table")
        summary_rows = []
        for t in threads:
            summary_rows.append({
                "Thread ID": t["thread_id"],
                "File": t.get("filename"),
                "Type": t.get("drawing_type"),
                "Status": t.get("status"),
                "Progress": f"{int(t.get('progress', 0)*100)}%",
                "Duration": format_duration(t.get("duration_sec")),
                "Step": t.get("current_step"),
                "Created At": t.get("created_at", "")[:19].replace("T", " "),
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        st.markdown("---")
        st.markdown("### Detailed Thread Logs & Error Tracebacks")

        for t in threads:
            tid = t["thread_id"]
            status = t["status"]
            status_icon = "🟢" if status == "COMPLETED" else "🔵" if status == "RUNNING" else "❌" if status == "FAILED" else "⛔"

            with st.expander(f"{status_icon} Thread: `{tid}` — File: *{t.get('filename')}* ({status})"):
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.write(f"**Drawing Type:** {t.get('drawing_type')}")
                    st.write(f"**Discipline:** {t.get('discipline')}")
                    st.write(f"**Created At:** {t.get('created_at')}")
                with col_info2:
                    st.write(f"**Status:** {t.get('status')}")
                    st.write(f"**Last Step:** {t.get('current_step')}")
                    st.write(f"**Updated At:** {t.get('updated_at')}")

                if t.get("error_message"):
                    st.error(f"**Failure Error Message:** {t.get('error_message')}")
                if t.get("error_traceback"):
                    st.markdown("**Failure Traceback:**")
                    st.code(t.get("error_traceback"))

                # Thread logs
                full_t = get_thread(tid)
                logs = full_t.get("logs", []) if full_t else []
                if logs:
                    st.markdown("**Subprocess Execution Timeline:**")
                    log_df = pd.DataFrame(logs)[["timestamp", "step_name", "log_level", "message"]]
                    st.dataframe(log_df, use_container_width=True)
                else:
                    st.write("No execution logs recorded.")
