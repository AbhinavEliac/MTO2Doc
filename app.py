"""
PID Data Extractor — Piping & Instrumentation Diagram Intelligence Dashboard.

Supports thread persistence in SQLite, background extraction execution,
live progress tracking, cancel functionality, and historical error logs.
"""
import os
import re
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
    get_run_outputs,
)
from src.agents.output_generator import ensure_thread_deliverables_in_db
from src.thread_manager import (
    start_extraction_thread,
    cancel_extraction_thread,
    is_thread_active,
)

logger = logging.getLogger(__name__)

# ─── Environment Sanity Check ─────────────────────────────────────────────────
# Detect if running under system Python (missing pid_env packages).
# If cv2 / fitz / ultralytics are absent, every agent silently returns 0 results.
def _check_env() -> list:
    missing = []
    for pkg, mod in [("opencv-python (cv2)", "cv2"), ("PyMuPDF (fitz)", "fitz"), ("ultralytics (YOLO)", "ultralytics")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    return missing

_MISSING_PKGS = _check_env()

def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "N/A"
    sec = int(seconds)
    if sec < 60:
        return f"{seconds:.1f}s"
    m = sec // 60
    s = sec % 60
    return f"{m:02d}m {s:02d}s"


def _item_to_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    elif isinstance(item, dict):
        return item
    return dict(item)


def render_download_buttons(thread_id: str, filename: str = "drawing", key_prefix: str = "dl"):
    """
    Renders download buttons for all 6 engineering deliverable formats stored in SQLite.
    """
    deliverables = ensure_thread_deliverables_in_db(thread_id)
    if not deliverables:
        st.info("No export deliverables available for this thread.")
        return

    base_name = os.path.splitext(filename or "drawing")[0]
    clean_base = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_name)[:24]

    st.markdown("<div style='margin-bottom: 8px; font-weight: 500;'>📥 Deliverables Persisted in Database (Ready for On-Demand Download):</div>", unsafe_allow_html=True)
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    # 1. Excel
    if "excel" in deliverables:
        item = deliverables["excel"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col1.download_button(
            label=f"📊 Excel{sz}",
            data=item["data"],
            file_name=f"{clean_base}_deliverables.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_excel_{thread_id}",
            use_container_width=True,
            help="Multi-sheet Excel workbook with P&ID line, instrument, valve & equipment schedules",
        )

    # 2. JSON Graph
    if "json_graph" in deliverables:
        item = deliverables["json_graph"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col2.download_button(
            label=f"🕸️ JSON{sz}",
            data=item["data"],
            file_name=f"{clean_base}_master_graph.json",
            mime="application/json",
            key=f"{key_prefix}_json_{thread_id}",
            use_container_width=True,
            help="Master P&ID engineering graph schema in JSON",
        )

    # 3. AVEVA XML
    if "aveva_xml" in deliverables:
        item = deliverables["aveva_xml"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col3.download_button(
            label=f"📐 AVEVA XML{sz}",
            data=item["data"],
            file_name=f"{clean_base}_aveva_diagrams.xml",
            mime="application/xml",
            key=f"{key_prefix}_xml_{thread_id}",
            use_container_width=True,
            help="P&ID XML hierarchy for AVEVA Diagrams & SP3D",
        )

    # 4. COMOS JSON
    if "comos_json" in deliverables:
        item = deliverables["comos_json"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col4.download_button(
            label=f"🔧 COMOS{sz}",
            data=item["data"],
            file_name=f"{clean_base}_comos_hierarchy.json",
            mime="application/json",
            key=f"{key_prefix}_comos_{thread_id}",
            use_container_width=True,
            help="P&ID object taxonomy for Siemens COMOS",
        )

    # 5. SPPID CSV
    if "sppid_csv" in deliverables:
        item = deliverables["sppid_csv"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col5.download_button(
            label=f"🗃️ SmartPlant{sz}",
            data=item["data"],
            file_name=f"{clean_base}_sppid_tables.csv",
            mime="text/csv",
            key=f"{key_prefix}_sppid_{thread_id}",
            use_container_width=True,
            help="Relational CSV tables for SmartPlant P&ID (SPPID) import",
        )

    # 6. Relationships CSV
    if "relationships_csv" in deliverables:
        item = deliverables["relationships_csv"]
        sz = f" ({item['file_size']/1024:.1f} KB)" if item.get("file_size") else ""
        col6.download_button(
            label=f"🔗 Relations{sz}",
            data=item["data"],
            file_name=f"{clean_base}_relationships.csv",
            mime="text/csv",
            key=f"{key_prefix}_rel_{thread_id}",
            use_container_width=True,
            help="P&ID topological relationships with confidence and evidence vectors",
        )


def render_graph_output_tables(graph, drawing_type: str = "PID"):
    """
    Renders extracted P&ID entities in tabbed pandas DataFrames with on-screen inspection.
    """
    if not graph:
        st.info("No P&ID engineering graph data available to display.")
        return

    lines = getattr(graph, 'lines', []) or []
    instruments = getattr(graph, 'instruments', []) or []
    valves = getattr(graph, 'valves', []) or []
    safety_relief_valves = getattr(graph, 'safety_relief_valves', []) or []
    equipment = getattr(graph, 'equipment', []) or []
    relationships = getattr(graph, 'relationships', []) or []
    annotations = getattr(graph, 'annotations', []) or []

    tab_line, tab_inst, tab_valve, tab_psv, tab_eq = st.tabs([
        f"📏 Line List ({len(lines)})",
        f"🔵 Instrument List ({len(instruments)})",
        f"🔧 Valve List ({len(valves)})",
        f"🛡️ Safety Relief Valves ({len(safety_relief_valves)})",
        f"⚙️ Equipment List ({len(equipment)})",
    ])
    with tab_line:
        st.subheader("Line List (Piping Segments & Specs)")
        if lines:
            df = pd.DataFrame([_item_to_dict(l) for l in lines]).drop(columns=["coordinates"], errors="ignore")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No piping lines detected.")

    with tab_inst:
        st.subheader("Instrument List (Field, Panel & DCS Loops)")
        if instruments:
            df = pd.DataFrame([_item_to_dict(i) for i in instruments]).drop(columns=["coordinates"], errors="ignore")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No instruments detected.")

    with tab_valve:
        st.subheader("Manual & Inline Valve List")
        if valves:
            df = pd.DataFrame([_item_to_dict(v) for v in valves]).drop(columns=["coordinates"], errors="ignore")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No valves detected.")

    with tab_psv:
        st.subheader("Safety Relief Valve List (PSV / PRV)")
        if safety_relief_valves:
            df = pd.DataFrame([_item_to_dict(p) for p in safety_relief_valves]).drop(columns=["coordinates"], errors="ignore")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No safety relief valves detected.")

    with tab_eq:
        st.subheader("Equipment List (Vessels, Pumps, Compressors, Tanks)")
        if equipment:
            df = pd.DataFrame([_item_to_dict(e) for e in equipment]).drop(columns=["coordinates"], errors="ignore")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No equipment detected.")

    # Relationships
    if relationships:
        with st.expander(f"🔗 Engineering Topology & Linkages ({len(relationships)})", expanded=False):
            df = pd.DataFrame([_item_to_dict(r) for r in relationships])
            st.dataframe(df, use_container_width=True)

    if annotations:
        with st.expander(f"📝 Drawing Notes & Elevation Labels ({len(annotations)})", expanded=False):
            df = pd.DataFrame([_item_to_dict(a) for a in annotations])
            st.dataframe(df, use_container_width=True)


# Initialize SQLite Database on app load
init_db()

# ─── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PID Data Extractor",
    page_icon="📐",
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
st.markdown("<div class='main-title'>📐 PID Data Extractor</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Intelligent Piping & Instrumentation Diagram (P&ID) Data Extraction & Digital Twin Engine</div>",
    unsafe_allow_html=True,
)

# ─── Environment Warning Banner ───────────────────────────────────────────────
if _MISSING_PKGS:
    st.error(
        f"⛔ **Wrong Python Environment Detected!**\n\n"
        f"Critical packages are missing: **{', '.join(_MISSING_PKGS)}**\n\n"
        f"You are running Streamlit from **system Python** (not the `pid_env` virtual environment). "
        f"Every extraction will complete in <1 second with **0 results** because OCR, YOLO, and CV imports silently fail.\n\n"
        f"**Fix: Stop this Streamlit instance and run:**\n"
        f"```\n.\\pid_env\\Scripts\\python.exe -m streamlit run app.py\n```"
    )
    st.stop()

# Fetch all saved threads from SQLite
all_threads = get_all_threads()

# Initialize session state for selected thread
if "active_thread_id" not in st.session_state and all_threads:
    st.session_state["active_thread_id"] = all_threads[0]["thread_id"]

# ─── Sidebar ───────────────────────────────────────────────────────────────────
speed_preset = st.sidebar.selectbox(
    "⚡ Pipeline Speed Preset",
    options=[
        "⚡ Balanced Hybrid (30–60 sec, Recommended)",
        "🚀 Ultra-Fast Offline (10–20 sec, Zero APIs)",
        "🔬 Deep Inspection (2–4 min)",
    ],
    index=0,
    help="Select speed preset. Ultra-Fast runs local PaddleOCR + OpenCV Line Tracer with zero API delays.",
)

default_retries = 0 if "Ultra-Fast" in speed_preset else (3 if "Deep" in speed_preset else 1)

max_retries = st.sidebar.slider(
    "Maximum Re-Extraction Cycles",
    min_value=0, max_value=5, value=default_retries,
    help="Number of times the supervisor crops and re-scans suspect areas. Set 1 for fast processing, 0 to disable retry loops.",
)

st.sidebar.markdown("### 🔤 Layer 1: OCR Reading Layer")
ocr_option = st.sidebar.selectbox(
    "1st Layer: OCR Text Engine",
    options=[
        "EasyOCR (Local / Offline — Images & PDFs)",
        "PyMuPDF Vector Text (Local / Offline)",
        "PaddleOCR (Local / Offline)",
        "Pathnovo ISA 5.1 Extraction Engine (High Accuracy)",
        "PaddleOCR-VL (0.9B Layout Model)",
        "LlamaParse / Vision Layout Agent",
        "Gemini Vision OCR (Online API)",
        "Qwen 2.5-VL / Vision API (Online)",
        "Qwen 3.7-VL / OpenRouter (Online)",
    ],
    index=0,
    help="Select the 1st layer OCR engine. EasyOCR works reliably offline on GPU/CPU for both raster images (PNG/JPG) and PDFs.",
)
ocr_engine_map = {
    "EasyOCR (Local / Offline — Images & PDFs)": "easyocr",
    "PyMuPDF Vector Text (Local / Offline)": "pdf_text",
    "PaddleOCR (Local / Offline)": "paddle",
    "Pathnovo ISA 5.1 Extraction Engine (High Accuracy)": "pathnovo_api",
    "PaddleOCR-VL (0.9B Layout Model)": "paddle_vl",
    "LlamaParse / Vision Layout Agent": "llamaparse",
    "Gemini Vision OCR (Online API)": "gemini_ocr",
    "Qwen 2.5-VL / Vision API (Online)": "qwen_ocr",
    "Qwen 3.7-VL / OpenRouter (Online)": "qwen_37_ocr",
}
ocr_engine = ocr_engine_map.get(ocr_option, "easyocr")

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
    index=0,
    help="Select the 2nd layer reasoning engine. Rule-Based Classifier runs 100% offline with zero API cost.",
)
reasoning_engine_map = {
    "Rule-Based Regex Classifier (Local / Offline)": "rule_based",
    "Qwen 2.5 Reasoning Engine (OpenRouter / API)": "qwen",
    "Qwen 3.7 Reasoning Engine (OpenRouter / API)": "qwen_37",
    "Gemini 2.0 Flash Engine (Online / API)": "gemini",
    "OpenAI GPT-4o Engine (Online / API)": "openai",
}
reasoning_engine = reasoning_engine_map.get(reasoning_option, "rule_based")

st.sidebar.markdown("### 🎯 Symbol Recognition Agent Engine")
symbol_option = st.sidebar.selectbox(
    "Symbol Detection Engine",
    options=[
        "🏋️ Trained YOLOv8 Symbol Detector (Local / Offline)",
        "Pathnovo ISA 5.1 Instrument & Symbol Engine",
        "ISA-5.1 VLM Symbol Detector (Multimodal VLM)",
        "GLM-OCR / RF-DETR Object Pipeline (Local / API)",
        "Heuristic Bounding Box Harvester (Local / Offline)",
    ],
    index=0,
    help="Select symbol detector. 'Trained YOLOv8' uses your custom best.pt trained on the P&ID dataset on CUDA GPU.",
)
symbol_engine_map = {
    "🏋️ Trained YOLOv8 Symbol Detector (Local / Offline)": "yolo_trained",
    "Pathnovo ISA 5.1 Instrument & Symbol Engine": "pathnovo_isa51",
    "ISA-5.1 VLM Symbol Detector (Multimodal VLM)": "vlm",
    "GLM-OCR / RF-DETR Object Pipeline (Local / API)": "glm_rfdetr",
    "Heuristic Bounding Box Harvester (Local / Offline)": "local",
}
symbol_engine = symbol_engine_map.get(symbol_option, "yolo_trained")

# ── Trained YOLO settings panel (only shown when yolo_trained is selected) ──
yolo_weights_path = None
_default_yolo_path = os.getenv(
    "DEFAULT_YOLO_WEIGHTS",
    os.path.join(os.getcwd(), "training", "outputs", "yolo_runs",
                 "pid_symbol_detector", "weights", "best.pt")
)
_yolo_weights_exist = os.path.exists(_default_yolo_path)

if symbol_engine == "yolo_trained":
    with st.sidebar.expander("⚙️ Trained YOLOv8 Settings", expanded=True):
        if _yolo_weights_exist:
            st.success(f"✅ Weights found: `.../{'/'.join(_default_yolo_path.replace(os.sep, '/').split('/')[-3:])}`")
        else:
            st.warning(
                "⚠️ No trained weights found at the default path. "
                "Run `python training/train.py yolo` first, or paste a custom path below."
            )

        yolo_weights_path = st.text_input(
            "Weights Path (best.pt)",
            value=_default_yolo_path,
            help="Absolute path to your trained YOLOv8 best.pt weights file.",
            key="yolo_weights_path_input",
        )

        yolo_conf = st.slider(
            "Detection Confidence Threshold",
            min_value=0.10, max_value=0.90, value=0.15, step=0.05,
            help="Lower → more detections (recommended 0.15 for tiled P&ID inference).",
            key="yolo_conf_slider",
        )

        yolo_iou = st.slider(
            "NMS IoU Threshold",
            min_value=0.30, max_value=0.80, value=0.45, step=0.05,
            help="Controls how aggressively overlapping boxes are suppressed.",
            key="yolo_iou_slider",
        )

        st.caption(
            "🖥️ Will run on **CUDA GPU (RTX 3050)** if available, otherwise CPU. "
            "Model class vocab: 26 ISA-5.1 symbol classes."
        )

# Defaults when yolo_trained is not selected
if symbol_engine != "yolo_trained":
    yolo_weights_path = _default_yolo_path
    yolo_conf = 0.15
    yolo_iou  = 0.45


pipeline_option = st.sidebar.selectbox(
    "Pipeline & Line Tracing Engine",
    options=[
        "Computer Vision Line Tracer + VLM Connectivity (Hybrid CV + VLM)",
        "Pathnovo ISA 5.1 Line & Loop Spec Tracer",
        "Full Multimodal VLM Polyline Tracer (Online API)",
        "Proximity & System Topological Tracer (Local / Offline)",
    ],
    index=0,
    help="Select line tracer. CV Line Tracer combines OpenCV line filtering with visual connectivity extraction.",
)
pipeline_engine_map = {
    "Computer Vision Line Tracer + VLM Connectivity (Hybrid CV + VLM)": "cv_vlm_tracer",
    "Pathnovo ISA 5.1 Line & Loop Spec Tracer": "pathnovo_pipeline",
    "Full Multimodal VLM Polyline Tracer (Online API)": "vlm_tracer",
    "Proximity & System Topological Tracer (Local / Offline)": "proximity_tracer",
}
pipeline_engine = pipeline_engine_map.get(pipeline_option, "cv_vlm_tracer")

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
            fname = t.get("filename", "P&ID Drawing")
            dt_label = "P&ID"
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
    st.markdown("<div class='section-header'>📂 P&ID Document Upload & Extraction Trigger</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        uploaded_drawing = st.file_uploader(
            "Upload P&ID Drawing (PDF, PNG, JPG)",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Upload Piping & Instrumentation Diagram (P&ID or PFD) drawing.",
        )

    with col2:
        uploaded_refs = st.file_uploader(
            "Upload Legend Sheets or Reference Documents (Optional)",
            type=["pdf", "png", "jpg"],
            accept_multiple_files=True,
            help="Provide P&ID symbol legends, client piping specs, or instrument tagging standards.",
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
            "metadata": {"drawing_type": "PID", "discipline": "Piping & Instrumentation"},
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
            "symbol_engine": symbol_engine,
            "pipeline_engine": pipeline_engine,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_api_key": llm_api_key,
            "llm_base_url": llm_base_url,
            "use_mocks": use_mocks,
            "local_mode": local_mode or (reasoning_engine == "rule_based" and ocr_engine in ("paddle", "pdf_text", "easyocr")),
            "re_extracted_targets": [],
            "yolo_weights_path": yolo_weights_path,
            "yolo_conf": yolo_conf,
            "yolo_iou": yolo_iou,

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

                drawing_type = active_thread.get("drawing_type") or metadata.get("drawing_type", "PID")
                discipline = active_thread.get("discipline") or metadata.get("discipline", "Piping & Instrumentation")
                if discipline in ("Unknown", None, "GENERIC"):
                    discipline = "Piping & Instrumentation"

                dt_label = "P&ID (Piping & Instrumentation Diagram)"
                if drawing_type and drawing_type.upper() in ("PFD", "PROCESS FLOW DIAGRAM"):
                    dt_label = "PFD (Process Flow Diagram)"

                st.markdown(
                    f"<div class='dtype-badge'>📐 {dt_label}"
                    f"<span class='discipline-chip'>{discipline}</span></div>",
                    unsafe_allow_html=True,
                )

                # Metadata Block
                st.markdown("<div class='section-header'>📋 P&ID Drawing Metadata</div>", unsafe_allow_html=True)
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
                    st.markdown("<div class='section-header'>📊 P&ID Extracted Data</div>", unsafe_allow_html=True)
                    render_graph_output_tables(graph, drawing_type)

                # Quality Assurance & Process Log (Consistency Errors & Warnings commented out)
                # col_v1, col_v2 = st.columns(2)
                # with col_v1:
                #     st.subheader("Consistency Errors & Warnings")
                #     if reports:
                #         for r in reports:
                #             is_err = (r.get("severity") == "ERROR")
                #             icon = "❌" if is_err else "⚠️"
                #             bg_color = "#FDF2F2" if is_err else "#FEFBF0"
                #             border_color = "#F05252" if is_err else "#FACA15"
                #             title_color = "#7F1D1D" if is_err else "#713F12"
                #             msg_color = "#991B1B" if is_err else "#854D0E"
                #             st.markdown(f"""
                #             <div style='background-color: {bg_color}; padding: 12px; border-left: 5px solid {border_color}; border-radius: 6px; margin-bottom: 10px; font-family: sans-serif;'>
                #                 <strong style='color: {title_color}; font-size: 0.95rem;'>{icon} {r.get('rule_id', 'RULE')} (Target: {r.get('target_tag', 'N/A')})</strong><br/>
                #                 <span style='font-size: 0.9rem; color: {msg_color}; line-height: 1.4; display: block; margin-top: 4px;'>{r.get('message')}</span>
                #             </div>
                #             """, unsafe_allow_html=True)
                #     else:
                #         st.success("✓ No validation discrepancies identified.")

                st.markdown("<div class='section-header'>🔍 Extraction Process Log</div>", unsafe_allow_html=True)
                st.subheader("Extraction Process History")
                st.markdown(f"**Re-extraction Loops:** `{re_runs}` / `{max_retries}`")
                st.markdown("**Revision History:**")
                for log in revision_history:
                    action = log.get("action", str(log))
                    st.markdown(f"- {action}")

                # Export & Download
                st.markdown("<div class='section-header'>📥 Export & Download</div>", unsafe_allow_html=True)
                render_download_buttons(active_id, active_thread.get("filename", "drawing"), key_prefix=f"dash_dl_{active_id}")
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
                "Type": "P&ID",
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
                col_info1, col_info2, col_info3 = st.columns([0.35, 0.35, 0.30])
                with col_info1:
                    st.write(f"**Diagram Type:** P&ID")
                    st.write(f"**Discipline:** {t.get('discipline') if t.get('discipline') not in ('Unknown', None, 'GENERIC') else 'Piping & Instrumentation'}")
                    st.write(f"**Created At:** {t.get('created_at', '')[:19].replace('T', ' ')}")
                with col_info2:
                    st.write(f"**Status:** {t.get('status')}")
                    st.write(f"**Duration:** {format_duration(t.get('duration_sec'))}")
                    st.write(f"**Last Step:** {t.get('current_step')}")
                with col_info3:
                    if st.button("📂 Open in Main Dashboard", key=f"hist_open_{tid}", use_container_width=True):
                        st.session_state["active_thread_id"] = tid
                        st.rerun()

                if t.get("error_message"):
                    st.error(f"**Failure Error Message:** {t.get('error_message')}")
                if t.get("error_traceback"):
                    st.markdown("**Failure Traceback:**")
                    st.code(t.get("error_traceback"))

                # Thread outputs and results from SQLite
                full_t = get_thread(tid)
                if status == "COMPLETED" and full_t and full_t.get("result"):
                    result_state = full_t["result"]
                    raw_graph_data = result_state.get("engineering_graph")
                    hist_graph = None
                    if raw_graph_data:
                        if isinstance(raw_graph_data, dict):
                            hist_graph = UniversalEngineeringGraph(**raw_graph_data)
                        else:
                            hist_graph = raw_graph_data

                    # Deliverable Download Section
                    st.markdown("---")
                    st.markdown("#### 📥 Download Deliverables (Stored in Database)")
                    render_download_buttons(tid, t.get("filename", "drawing"), key_prefix=f"hist_dl_{tid}")

                    # On-Screen Entity & Topology View
                    if hist_graph:
                        st.markdown("#### 📊 Extracted Output & Relationships (On-Screen View)")
                        render_graph_output_tables(hist_graph, "PID")

                # Thread logs
                logs = full_t.get("logs", []) if full_t else []
                if logs:
                    st.markdown("---")
                    with st.expander("📜 Subprocess Execution Timeline Logs", expanded=False):
                        log_df = pd.DataFrame(logs)[["timestamp", "step_name", "log_level", "message"]]
                        st.dataframe(log_df, use_container_width=True)
                else:
                    st.write("No execution logs recorded.")
